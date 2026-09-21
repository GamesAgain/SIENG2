"""Direct and runtime-boundary tests for the Locomotive adapter."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from config_prototype.core.configurable import (
    EncryptionRequest,
    LocomotiveRunCover,
    LocomotiveRunInputs,
    PipelineRunRequest,
    RunArtifact,
    RunStepRequest,
    RunWorkspace,
    StepOutput,
    compile_pipeline,
    resolve_source,
)
from config_prototype.core.configurable.adapters import execute_locomotive
from src.core.crypto.asym_encrypt import (
    generate_rsa_keypair,
    serialize_private_key,
    serialize_public_key,
)
from src.core.stego.locomotive import Locomotive
from src.core.stego.png_container import parse_png


MESSAGE = "Configurable Pipeline Locomotive adapter"
PASSWORD = "Locomotive-Adapter-Password-2026!"


@pytest.fixture(scope="module")
def textured_cover(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("locomotive-adapter-cover")
    path = directory / "cover.png"
    pixels = np.random.default_rng(844).integers(
        0,
        256,
        size=(128, 128, 3),
        dtype=np.uint8,
    )
    Image.fromarray(pixels).save(path, format="PNG")
    return path


@pytest.fixture(scope="module")
def rsa_key_paths(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path]:
    directory = tmp_path_factory.mktemp("locomotive-adapter-rsa")
    private_key, public_key = generate_rsa_keypair(2048)
    private_path = directory / "private.pem"
    public_path = directory / "public.pem"
    private_path.write_bytes(serialize_private_key(private_key))
    public_path.write_bytes(serialize_public_key(public_key))
    return private_path, public_path


def _covers(
    tmp_path: Path,
    source: Path,
    count: int,
) -> tuple[Path, ...]:
    result = []
    source_bytes = source.read_bytes()
    for index in range(count):
        path = tmp_path / f"cover-{index + 1}.png"
        path.write_bytes(source_bytes)
        result.append(path)
    return tuple(result)


def _text_inputs(
    sources: tuple[str | StepOutput, ...],
    output_keys: tuple[str, ...],
    *,
    encryption: EncryptionRequest = EncryptionRequest(),
) -> LocomotiveRunInputs:
    return LocomotiveRunInputs(
        covers=tuple(
            LocomotiveRunCover(source, output_key)
            for source, output_key in zip(sources, output_keys)
        ),
        payload_mode="text",
        payload_text=MESSAGE,
        encryption=encryption,
    )


def _staging_paths(
    tmp_path: Path,
    output_keys: tuple[str, ...],
) -> dict[str, Path]:
    return {
        output_key: tmp_path / f"{output_key}.png"
        for output_key in reversed(output_keys)
    }


def test_single_cover_text_round_trip_does_not_change_input(
    tmp_path: Path,
    textured_cover: Path,
) -> None:
    cover = _covers(tmp_path, textured_cover, 1)[0]
    original = cover.read_bytes()
    output_key = "output_single"
    result = tmp_path / "staged-single.png"

    metadata = execute_locomotive(
        _text_inputs((str(cover),), (output_key,)),
        cover_paths=(cover,),
        result_paths={output_key: result},
    )

    extracted_name, extracted_data = Locomotive().extract((str(result),))
    assert extracted_name == "secret_message.txt"
    assert extracted_data.decode("utf-8") == MESSAGE
    assert cover.read_bytes() == original
    assert result.read_bytes().startswith(original)
    assert parse_png(result.read_bytes()).core == parse_png(original).core
    assert metadata["session_id"] is not None
    assert metadata["output_count"] == 1
    assert metadata["encryption_mode"] == "none"


def test_multiple_covers_map_stable_keys_and_commit_together(
    tmp_path: Path,
    textured_cover: Path,
) -> None:
    covers = _covers(tmp_path, textured_cover, 3)
    output_keys = ("output_zeta", "output_alpha", "output_middle")
    payload = tmp_path / "payload.bin"
    payload_bytes = bytes(range(256)) + b"SIENG2-locomotive"
    payload.write_bytes(payload_bytes)
    inputs = LocomotiveRunInputs(
        covers=tuple(
            LocomotiveRunCover(str(cover), output_key)
            for cover, output_key in zip(covers, output_keys)
        ),
        payload_mode="files",
        payload_files=(str(payload),),
        encryption=EncryptionRequest(
            mode="password",
            password=PASSWORD,
        ),
    )
    compiled = compile_pipeline(
        PipelineRunRequest(
            steps=(
                RunStepRequest(
                    "step_loco",
                    "locomotive",
                    "Locomotive",
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
    by_output_key = {
        reference.output_key: path
        for reference, path in reversed(tuple(staged.items()))
    }

    metadata = execute_locomotive(
        inputs,
        cover_paths=covers,
        payload_paths=(payload,),
        result_paths=by_output_key,
    )

    assert artifact.outputs == {}
    assert tuple(
        output["output_key"] for output in metadata["outputs"]
    ) == output_keys
    committed = artifact.commit_step_outputs(
        step,
        staged,
        metadata=metadata,
    )
    assert tuple(committed) == tuple(
        StepOutput("step_loco", key) for key in output_keys
    )
    extracted_name, extracted_data = Locomotive().extract(
        tuple(str(committed[StepOutput("step_loco", key)]) for key in output_keys),
        password=PASSWORD,
        session_id=metadata["session_id"],
    )
    assert extracted_name == payload.name
    assert extracted_data == payload_bytes
    assert PASSWORD not in repr(metadata)
    artifact.cleanup()


def test_linked_cover_is_resolved_before_adapter(
    tmp_path: Path,
    textured_cover: Path,
) -> None:
    reference = StepOutput("step_image", "result")
    linked_cover = _covers(tmp_path, textured_cover, 1)[0]
    resolved_cover = resolve_source(reference, {reference: linked_cover})
    output_key = "output_linked_cover"
    result = tmp_path / "linked-cover-result.png"
    inputs = _text_inputs((reference,), (output_key,))

    execute_locomotive(
        inputs,
        cover_paths=(resolved_cover,),
        result_paths={output_key: result},
    )

    assert Locomotive().extract((str(result),))[1].decode("utf-8") == MESSAGE


def test_linked_file_payload_public_key_round_trip(
    tmp_path: Path,
    textured_cover: Path,
    rsa_key_paths: tuple[Path, Path],
) -> None:
    private_path, public_path = rsa_key_paths
    cover = _covers(tmp_path, textured_cover, 1)[0]
    payload_reference = StepOutput("step_payload", "result")
    payload = tmp_path / "linked-payload.png"
    payload.write_bytes(textured_cover.read_bytes())
    resolved_payload = resolve_source(
        payload_reference,
        {payload_reference: payload},
    )
    output_key = "output_linked_payload"
    result = tmp_path / "linked-payload-result.png"
    inputs = LocomotiveRunInputs(
        covers=(LocomotiveRunCover(str(cover), output_key),),
        payload_mode="files",
        payload_files=(payload_reference,),
        encryption=EncryptionRequest(
            mode="public_key",
            public_key_path=str(public_path),
        ),
    )

    metadata = execute_locomotive(
        inputs,
        cover_paths=(cover,),
        payload_paths=(resolved_payload,),
        result_paths={output_key: result},
    )

    extracted_name, extracted_data = Locomotive().extract(
        (str(result),),
        private_key_path=str(private_path),
        session_id=metadata["session_id"],
    )
    assert extracted_name == payload.name
    assert extracted_data == payload.read_bytes()
    assert str(public_path) not in repr(metadata)


def test_output_count_mismatch_writes_nothing(
    tmp_path: Path,
    textured_cover: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    covers = _covers(tmp_path, textured_cover, 2)
    output_keys = ("output_first", "output_second")
    results = _staging_paths(tmp_path, output_keys)
    monkeypatch.setattr(
        Locomotive,
        "embed",
        lambda *_args, **_kwargs: [
            ("not-an-identity.png", covers[0].read_bytes())
        ],
    )

    with pytest.raises(ValueError, match="count does not match"):
        execute_locomotive(
            _text_inputs(tuple(map(str, covers)), output_keys),
            cover_paths=covers,
            result_paths=results,
        )

    assert not any(path.exists() for path in results.values())


def test_failure_in_middle_of_output_set_does_not_commit_mapping(
    tmp_path: Path,
    textured_cover: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    covers = _covers(tmp_path, textured_cover, 2)
    output_keys = ("output_first", "output_second")
    inputs = _text_inputs(tuple(map(str, covers)), output_keys)
    compiled = compile_pipeline(
        PipelineRunRequest(
            steps=(
                RunStepRequest(
                    "step_loco",
                    "locomotive",
                    "Locomotive",
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
    by_output_key = {
        reference.output_key: path for reference, path in staged.items()
    }
    failed_path = by_output_key["output_second"]
    original_write_bytes = Path.write_bytes

    def fail_second_output(path: Path, data: bytes) -> int:
        if path.resolve() == failed_path.resolve():
            raise OSError("injected staging write failure")
        return original_write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_second_output)

    with pytest.raises(OSError, match="injected staging"):
        execute_locomotive(
            inputs,
            cover_paths=covers,
            result_paths=by_output_key,
        )

    assert artifact.outputs == {}
    assert not any(path.exists() for path in by_output_key.values())
    artifact.cleanup()
