"""Execution and preservation tests for the Metadata-PNG adapter."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from config_prototype.core.configurable import (
    LSBRunInputs,
    LocomotiveRunCover,
    LocomotiveRunInputs,
    MetadataRunInputs,
    PNGMetadataRunPayload,
    PipelineRunRequest,
    RunArtifact,
    RunStepRequest,
    RunWorkspace,
    StepOutput,
    compile_pipeline,
)
from config_prototype.core.configurable.adapters import (
    execute_locomotive,
    execute_lsbpp,
    execute_metadata_png,
)
from src.core.stego.locomotive import Locomotive
from src.core.stego.lsb_pp import LSBPP
from src.core.stego.metadata import MetadataEmbedder
from src.core.stego.png_container import build_png, parse_png


LSB_MESSAGE = "Keep the LSB++ payload"
LOCOMOTIVE_MESSAGE = "Keep the Locomotive payload"
METADATA_ENTRIES = (
    ("Title", "Pipeline output"),
    ("Comment", "Metadata-PNG round trip"),
)


@pytest.fixture(scope="module")
def textured_cover(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("metadata-png-adapter-cover")
    path = directory / "cover.png"
    pixels = np.random.default_rng(845).integers(
        0,
        256,
        size=(256, 256, 3),
        dtype=np.uint8,
    )
    Image.fromarray(pixels).save(path, format="PNG")
    return path


def _copy_cover(tmp_path: Path, source: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(source.read_bytes())
    return path


def _pixels(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(image)


def _inputs(cover: str | StepOutput) -> MetadataRunInputs:
    return MetadataRunInputs(
        cover=cover,
        media_type="png",
        payload=PNGMetadataRunPayload(entries=METADATA_ENTRIES),
    )


def test_metadata_round_trip_uses_result_identity_and_staged_commit(
    tmp_path: Path,
    textured_cover: Path,
) -> None:
    cover = _copy_cover(tmp_path, textured_cover, "manual-cover.png")
    original = cover.read_bytes()
    inputs = _inputs(str(cover))
    compiled = compile_pipeline(
        PipelineRunRequest(
            steps=(
                RunStepRequest(
                    "step_metadata",
                    "metadata",
                    "Metadata PNG",
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
    reference = StepOutput("step_metadata", "result")
    progress: list[int] = []

    metadata = execute_metadata_png(
        inputs,
        cover_path=cover,
        result_path=staged[reference],
        progress_callback=lambda percent, _message: progress.append(percent),
    )

    assert artifact.outputs == {}
    assert MetadataEmbedder().extract(str(staged[reference])) == dict(
        METADATA_ENTRIES
    )
    assert cover.read_bytes() == original
    assert metadata == {
        "media_type": "png",
        "output_key": "result",
        "entry_count": 2,
        "keywords": ("Title", "Comment"),
        "size_bytes": staged[reference].stat().st_size,
    }
    assert progress == [10, 100]

    committed = artifact.commit_step_outputs(
        step,
        staged,
        metadata=metadata,
    )
    assert tuple(committed) == (reference,)
    artifact.cleanup()


def test_preserves_pixels_unrelated_chunks_and_trailing_data(
    tmp_path: Path,
    textured_cover: Path,
) -> None:
    cover = _copy_cover(tmp_path, textured_cover, "structured-cover.png")
    container = parse_png(cover.read_bytes())
    unrelated_type = b"vpAg"
    unrelated_data = b"preserve-unrelated-chunk"
    chunks = list(container.chunks)
    chunks.insert(1, (unrelated_type, unrelated_data))
    trailer = b"existing-trailing-data"
    cover.write_bytes(build_png(chunks, trailing=trailer))
    original_pixels = _pixels(cover)
    result = tmp_path / "structured-result.png"

    execute_metadata_png(
        _inputs(str(cover)),
        cover_path=cover,
        result_path=result,
    )

    output = parse_png(result.read_bytes())
    unrelated_chunks = tuple(
        chunk.data
        for chunk in output.chunks
        if chunk.chunk_type == unrelated_type
    )
    assert np.array_equal(_pixels(result), original_pixels)
    assert unrelated_chunks == (unrelated_data,)
    assert output.trailing == trailer


def test_preserves_existing_lsb_payload(
    tmp_path: Path,
    textured_cover: Path,
) -> None:
    cover = _copy_cover(tmp_path, textured_cover, "lsb-source.png")
    lsb_cover = tmp_path / "lsb-result.png"
    execute_lsbpp(
        LSBRunInputs(cover=str(cover), payload_text=LSB_MESSAGE),
        cover_path=cover,
        result_path=lsb_cover,
    )
    lsb_pixels = _pixels(lsb_cover)
    metadata_result = tmp_path / "lsb-metadata-result.png"

    execute_metadata_png(
        _inputs(str(lsb_cover)),
        cover_path=lsb_cover,
        result_path=metadata_result,
    )

    assert np.array_equal(_pixels(metadata_result), lsb_pixels)
    assert LSBPP().extract(str(metadata_result)) == LSB_MESSAGE
    assert MetadataEmbedder().extract(str(metadata_result)) == dict(
        METADATA_ENTRIES
    )


def test_preserves_existing_locomotive_payload(
    tmp_path: Path,
    textured_cover: Path,
) -> None:
    cover = _copy_cover(tmp_path, textured_cover, "loco-source.png")
    output_key = "output_locomotive"
    loco_cover = tmp_path / "loco-result.png"
    loco_metadata = execute_locomotive(
        LocomotiveRunInputs(
            covers=(LocomotiveRunCover(str(cover), output_key),),
            payload_mode="text",
            payload_text=LOCOMOTIVE_MESSAGE,
        ),
        cover_paths=(cover,),
        result_paths={output_key: loco_cover},
    )
    original_trailing = parse_png(loco_cover.read_bytes()).trailing
    metadata_result = tmp_path / "loco-metadata-result.png"

    execute_metadata_png(
        _inputs(str(loco_cover)),
        cover_path=loco_cover,
        result_path=metadata_result,
    )

    assert parse_png(metadata_result.read_bytes()).trailing == original_trailing
    extracted_name, extracted_data = Locomotive().extract(
        (str(metadata_result),),
        session_id=loco_metadata["session_id"],
    )
    assert extracted_name == "secret_message.txt"
    assert extracted_data.decode("utf-8") == LOCOMOTIVE_MESSAGE


def test_rejects_cover_overwrite(
    tmp_path: Path,
    textured_cover: Path,
) -> None:
    cover = _copy_cover(tmp_path, textured_cover, "keep-cover.png")
    original = cover.read_bytes()

    with pytest.raises(ValueError, match="cannot overwrite"):
        execute_metadata_png(
            _inputs(str(cover)),
            cover_path=cover,
            result_path=cover,
        )

    assert cover.read_bytes() == original


def test_rejects_non_png_core_output_after_write(
    tmp_path: Path,
    textured_cover: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cover = _copy_cover(tmp_path, textured_cover, "invalid-output-cover.png")
    result = tmp_path / "invalid-output-result.png"

    def write_invalid(
        _embedder: MetadataEmbedder,
        file_path: str,
        data: dict,
        save_path: str,
    ) -> str:
        del file_path, data
        Path(save_path).write_bytes(b"not a png")
        return save_path

    monkeypatch.setattr(MetadataEmbedder, "embed", write_invalid)

    with pytest.raises(ValueError, match="Invalid PNG signature"):
        execute_metadata_png(
            _inputs(str(cover)),
            cover_path=cover,
            result_path=result,
        )
