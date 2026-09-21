"""Execution and preservation tests for the Metadata-MP3 adapter."""

from pathlib import Path

import pytest
from mutagen.id3 import ID3, TALB
from PIL import Image

from config_prototype.core.configurable import (
    ApicImageRequest,
    MP3ComplexFrameInstanceRequest,
    MP3ComplexFrameRequest,
    MP3MetadataRunPayload,
    MP3SimpleFrameRequest,
    MetadataRunInputs,
    PipelineRunRequest,
    RunArtifact,
    RunStepRequest,
    RunWorkspace,
    StepOutput,
    compile_pipeline,
    resolve_source,
)
from config_prototype.core.configurable.adapters import execute_metadata_mp3
from src.core.stego.metadata import MetadataEmbedder


MPEG_FRAME_HEADER = bytes.fromhex("fffb9064")
MPEG_AUDIO = (MPEG_FRAME_HEADER + bytes(413)) * 4


def _mp3_cover(tmp_path: Path, name: str = "cover.mp3") -> Path:
    path = tmp_path / name
    path.write_bytes(MPEG_AUDIO)
    tag = ID3()
    tag.add(TALB(encoding=3, text=["Existing album"]))
    tag.save(path, v2_version=3)
    return path


def _image(
    tmp_path: Path,
    name: str = "cover-art.png",
    *,
    color: tuple[int, int, int] = (32, 120, 220),
) -> Path:
    path = tmp_path / name
    Image.new("RGB", (48, 36), color).save(path, format="PNG")
    return path


def _inputs(
    *,
    cover: str,
    frames: tuple[
        MP3SimpleFrameRequest | MP3ComplexFrameRequest,
        ...,
    ] = (),
    apic_images: tuple[ApicImageRequest, ...] = (),
) -> MetadataRunInputs:
    return MetadataRunInputs(
        cover=cover,
        media_type="mp3",
        payload=MP3MetadataRunPayload(
            frames=frames,
            apic_images=apic_images,
        ),
    )


def _audio_payload(path: Path) -> bytes:
    data = path.read_bytes()
    offset = data.find(MPEG_FRAME_HEADER)
    assert offset >= 0
    return data[offset:]


def test_text_only_supports_simple_and_complex_frames_in_staging(
    tmp_path: Path,
) -> None:
    cover = _mp3_cover(tmp_path)
    inputs = _inputs(
        cover=str(cover),
        frames=(
            MP3SimpleFrameRequest("TIT2", "Hidden title"),
            MP3SimpleFrameRequest(
                "WOAR",
                "https://example.test/artist",
            ),
            MP3ComplexFrameRequest(
                "COMM",
                (
                    MP3ComplexFrameInstanceRequest(
                        lang="eng",
                        desc="Pipeline note",
                        text="Secret comment",
                    ),
                ),
            ),
            MP3ComplexFrameRequest(
                "TXXX",
                (
                    MP3ComplexFrameInstanceRequest(
                        desc="Private field",
                        text="Secret value",
                    ),
                ),
            ),
        ),
    )
    compiled = compile_pipeline(
        PipelineRunRequest(
            steps=(
                RunStepRequest(
                    "step_metadata_mp3",
                    "metadata",
                    "Metadata MP3",
                    "",
                    inputs,
                ),
            )
        )
    )
    workspace = RunWorkspace.create(tmp_path / "runs")
    artifact = RunArtifact(compiled, workspace)
    step = compiled.steps[0]
    staged = artifact.staging_paths(step)
    reference = StepOutput("step_metadata_mp3", "result")
    progress: list[int] = []

    metadata = execute_metadata_mp3(
        inputs,
        cover_path=cover,
        result_path=staged[reference],
        progress_callback=lambda percent, _message: progress.append(percent),
    )

    extracted = MetadataEmbedder().extract(str(staged[reference]))
    assert extracted["TIT2"] == "Hidden title"
    assert extracted["WOAR"] == "https://example.test/artist"
    assert extracted["COMM"] == [
        {
            "lang": "eng",
            "desc": "Pipeline note",
            "text": "Secret comment",
        }
    ]
    assert extracted["TXXX"] == [
        {"desc": "Private field", "text": "Secret value"}
    ]
    assert metadata["output_key"] == "result"
    assert metadata["frame_count"] == 4
    assert metadata["apic_count"] == 0
    assert progress == [10, 100]

    committed = artifact.commit_step_outputs(
        step,
        staged,
        metadata=metadata,
    )
    assert tuple(committed) == (reference,)
    artifact.cleanup()


def test_apic_only_embeds_a_resolved_manual_image(tmp_path: Path) -> None:
    cover = _mp3_cover(tmp_path)
    image = _image(tmp_path)
    inputs = _inputs(
        cover=str(cover),
        apic_images=(
            ApicImageRequest(
                image=str(image),
                picture_type=3,
                description="Front cover",
            ),
        ),
    )
    result = tmp_path / "manual-apic-result.mp3"

    metadata = execute_metadata_mp3(
        inputs,
        cover_path=cover,
        apic_paths=(image,),
        result_path=result,
    )

    extracted = MetadataEmbedder().extract(str(result))
    assert extracted["APIC"] == [
        {
            "mime": "image/png",
            "type": 3,
            "desc": "Front cover",
            "data": image.read_bytes(),
        }
    ]
    assert metadata["frame_count"] == 0
    assert metadata["apic_count"] == 1


def test_text_and_apic_preserve_audio_cover_and_unrelated_frames(
    tmp_path: Path,
) -> None:
    cover = _mp3_cover(tmp_path)
    original_cover = cover.read_bytes()
    original_audio = _audio_payload(cover)
    image = _image(tmp_path, "back-cover.png", color=(180, 70, 30))
    inputs = _inputs(
        cover=str(cover),
        frames=(MP3SimpleFrameRequest("TIT2", "Stacked payload"),),
        apic_images=(
            ApicImageRequest(
                image=str(image),
                picture_type=4,
                description="Back cover",
            ),
        ),
    )
    result = tmp_path / "text-apic-result.mp3"

    execute_metadata_mp3(
        inputs,
        cover_path=cover,
        apic_paths=(image,),
        result_path=result,
    )

    assert cover.read_bytes() == original_cover
    assert _audio_payload(result) == original_audio
    result_tag = ID3(result)
    assert result_tag.getall("TALB")[0].text == ["Existing album"]
    extracted = MetadataEmbedder().extract(str(result))
    assert extracted["TIT2"] == "Stacked payload"
    assert extracted["APIC"][0]["data"] == image.read_bytes()


def test_linked_apic_is_resolved_before_adapter_and_uses_same_path_flow(
    tmp_path: Path,
) -> None:
    cover = _mp3_cover(tmp_path)
    linked_image = _image(tmp_path, "linked-output.png")
    reference = StepOutput("step_lsb", "result")
    inputs = _inputs(
        cover=str(cover),
        apic_images=(
            ApicImageRequest(
                image=reference,
                picture_type=6,
                description="Media label",
            ),
        ),
    )
    resolved = resolve_source(reference, {reference: linked_image})
    result = tmp_path / "linked-apic-result.mp3"

    execute_metadata_mp3(
        inputs,
        cover_path=cover,
        apic_paths=(resolved,),
        result_path=result,
    )

    extracted = MetadataEmbedder().extract(str(result))
    assert extracted["APIC"][0] == {
        "mime": "image/png",
        "type": 6,
        "desc": "Media label",
        "data": linked_image.read_bytes(),
    }


def test_rejects_cover_overwrite_or_unresolved_apic_path(
    tmp_path: Path,
) -> None:
    cover = _mp3_cover(tmp_path)
    image = _image(tmp_path)
    inputs = _inputs(
        cover=str(cover),
        apic_images=(ApicImageRequest(str(image), 3, "Front cover"),),
    )

    with pytest.raises(ValueError, match="cannot overwrite"):
        execute_metadata_mp3(
            inputs,
            cover_path=cover,
            apic_paths=(image,),
            result_path=cover,
        )
    with pytest.raises(TypeError, match="concrete Paths"):
        execute_metadata_mp3(
            inputs,
            cover_path=cover,
            apic_paths=(str(image),),  # type: ignore[arg-type]
            result_path=tmp_path / "invalid-apic-result.mp3",
        )


def test_rejects_duplicate_apic_contract_values(tmp_path: Path) -> None:
    cover = _mp3_cover(tmp_path)
    first = _image(tmp_path, "first.png")
    second = _image(tmp_path, "second.png")
    duplicate_type = _inputs(
        cover=str(cover),
        apic_images=(
            ApicImageRequest(str(first), 3, "First"),
            ApicImageRequest(str(second), 3, "Second"),
        ),
    )
    duplicate_description = _inputs(
        cover=str(cover),
        apic_images=(
            ApicImageRequest(str(first), 3, "Cover"),
            ApicImageRequest(str(second), 4, "cover"),
        ),
    )

    with pytest.raises(ValueError, match="picture type"):
        execute_metadata_mp3(
            duplicate_type,
            cover_path=cover,
            apic_paths=(first, second),
            result_path=tmp_path / "duplicate-type.mp3",
        )
    with pytest.raises(ValueError, match="descriptions"):
        execute_metadata_mp3(
            duplicate_description,
            cover_path=cover,
            apic_paths=(first, second),
            result_path=tmp_path / "duplicate-description.mp3",
        )
