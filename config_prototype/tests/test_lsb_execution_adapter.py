"""Direct and round-trip tests for the LSB++ execution adapter."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from config_prototype.core.configurable import (
    EncryptionRequest,
    LSBRunInputs,
    RunArtifact,
    RunWorkspace,
    StepOutput,
    compile_pipeline,
)
from config_prototype.core.configurable.adapters import execute_lsbpp
from config_prototype.core.configurable.run_request import (
    PipelineRunRequest,
    RunStepRequest,
)
from src.core.crypto.asym_encrypt import (
    generate_rsa_keypair,
    serialize_private_key,
    serialize_public_key,
)
from src.core.stego.lsb_pp import LSBPP
from src.core.stego.png_container import PNG_SIGNATURE, parse_png


MESSAGE = "Configurable Pipeline LSB++ adapter"
PASSWORD = "Adapter-Password-2026!"


@pytest.fixture(scope="module")
def textured_cover(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("lsb-adapter-cover")
    path = directory / "cover.png"
    pixels = np.random.default_rng(843).integers(
        0,
        256,
        size=(256, 256, 3),
        dtype=np.uint8,
    )
    Image.fromarray(pixels).save(path, format="PNG")
    return path


@pytest.fixture(scope="module")
def rsa_key_paths(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path]:
    directory = tmp_path_factory.mktemp("lsb-adapter-rsa")
    private_key, public_key = generate_rsa_keypair(2048)
    private_path = directory / "private.pem"
    public_path = directory / "public.pem"
    private_path.write_bytes(serialize_private_key(private_key))
    public_path.write_bytes(serialize_public_key(public_key))
    return private_path, public_path


def _execute(
    tmp_path: Path,
    textured_cover: Path,
    encryption: EncryptionRequest = EncryptionRequest(),
) -> tuple[Path, dict[str, object]]:
    output = tmp_path / "result.png"
    metadata = execute_lsbpp(
        LSBRunInputs(
            cover=str(textured_cover),
            payload_text=MESSAGE,
            encryption=encryption,
        ),
        cover_path=textured_cover,
        result_path=output,
    )
    return output, metadata


def test_no_encryption_writes_valid_png_without_changing_cover(
    tmp_path: Path,
    textured_cover: Path,
) -> None:
    original_cover = textured_cover.read_bytes()
    progress: list[int] = []
    output = tmp_path / "result.png"
    inputs = LSBRunInputs(
        cover=str(textured_cover),
        payload_text=MESSAGE,
    )

    metadata = execute_lsbpp(
        inputs,
        cover_path=textured_cover,
        result_path=output,
        progress_callback=lambda percent, _message: progress.append(percent),
    )

    assert output.is_file()
    assert output.read_bytes().startswith(PNG_SIGNATURE)
    parse_png(output.read_bytes())
    assert textured_cover.read_bytes() == original_cover
    assert LSBPP().extract(str(output)) == MESSAGE
    assert progress[-1] == 100
    assert metadata == {
        "media_type": "png",
        "suggested_filename": "cover_stego.png",
        "size_bytes": output.stat().st_size,
        "encryption_mode": "none",
    }


def test_password_round_trip_has_no_secret_metadata(
    tmp_path: Path,
    textured_cover: Path,
) -> None:
    output, metadata = _execute(
        tmp_path,
        textured_cover,
        EncryptionRequest(mode="password", password=PASSWORD),
    )

    assert LSBPP().extract(str(output), password=PASSWORD) == MESSAGE
    assert metadata["encryption_mode"] == "password"
    assert PASSWORD not in repr(metadata)


def test_public_key_round_trip_has_no_key_material_metadata(
    tmp_path: Path,
    textured_cover: Path,
    rsa_key_paths: tuple[Path, Path],
) -> None:
    private_path, public_path = rsa_key_paths
    output, metadata = _execute(
        tmp_path,
        textured_cover,
        EncryptionRequest(
            mode="public_key",
            public_key_path=str(public_path),
        ),
    )

    assert (
        LSBPP().extract(
            str(output),
            private_key_path=str(private_path),
        )
        == MESSAGE
    )
    assert metadata["encryption_mode"] == "public_key"
    assert str(public_path) not in repr(metadata)
    assert public_path.read_bytes() not in repr(metadata).encode("utf-8")


def test_adapter_only_writes_staging_until_artifact_commits(
    tmp_path: Path,
    textured_cover: Path,
) -> None:
    request = PipelineRunRequest(
        steps=(
            RunStepRequest(
                step_key="step_lsb",
                technique="lsbpp",
                description="LSB++",
                guidenote="",
                inputs=LSBRunInputs(
                    cover=str(textured_cover),
                    payload_text=MESSAGE,
                ),
            ),
        )
    )
    compiled = compile_pipeline(request)
    workspace = RunWorkspace.create(tmp_path / "runs")
    artifact = RunArtifact(compiled, workspace)
    step = compiled.steps[0]
    staged = artifact.staging_paths(step)
    reference = StepOutput("step_lsb", "result")

    metadata = execute_lsbpp(
        step.request.inputs,
        cover_path=textured_cover,
        result_path=staged[reference],
    )

    assert artifact.outputs == {}
    assert staged[reference].is_file()
    committed = artifact.commit_step_outputs(
        step,
        staged,
        metadata=metadata,
    )
    assert artifact.outputs == committed
    assert artifact.step_metadata["step_lsb"] == metadata
    artifact.cleanup()


def test_adapter_rejects_cover_overwrite(
    textured_cover: Path,
) -> None:
    original = textured_cover.read_bytes()

    with pytest.raises(ValueError, match="cannot overwrite"):
        execute_lsbpp(
            LSBRunInputs(payload_text=MESSAGE),
            cover_path=textured_cover,
            result_path=textured_cover,
        )

    assert textured_cover.read_bytes() == original


def test_adapter_rejects_invalid_core_output_before_writing(
    tmp_path: Path,
    textured_cover: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "result.png"
    monkeypatch.setattr(
        LSBPP,
        "embed",
        lambda *_args, **_kwargs: (b"not a png", "invalid.png"),
    )

    with pytest.raises(ValueError, match="Invalid PNG signature"):
        execute_lsbpp(
            LSBRunInputs(payload_text=MESSAGE),
            cover_path=textured_cover,
            result_path=output,
        )

    assert not output.exists()


def test_adapter_preserves_png_metadata_and_trailing_bytes(
    tmp_path: Path,
    textured_cover: Path,
) -> None:
    cover = tmp_path / "metadata-cover.png"
    png_info = PngInfo()
    png_info.add_text("Comment", "keep this metadata")
    with Image.open(textured_cover) as image:
        image.save(cover, format="PNG", pnginfo=png_info)
    trailer = b"SIENG2-LOCOMOTIVE-TRAILER"
    cover.write_bytes(cover.read_bytes() + trailer)
    original = parse_png(cover.read_bytes())

    output, _metadata = _execute(tmp_path, cover)
    result = parse_png(output.read_bytes())

    original_text_chunks = tuple(
        chunk.raw for chunk in original.chunks if chunk.chunk_type == b"tEXt"
    )
    result_text_chunks = tuple(
        chunk.raw for chunk in result.chunks if chunk.chunk_type == b"tEXt"
    )
    assert result_text_chunks == original_text_chunks
    assert result.trailing == trailer
    assert LSBPP().extract(str(output)) == MESSAGE
