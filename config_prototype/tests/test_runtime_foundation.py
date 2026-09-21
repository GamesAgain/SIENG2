"""Focused tests for the L8.3 runtime foundation."""

import subprocess
import sys
from pathlib import Path

import pytest

from config_prototype.core.configurable import (
    CompiledPipeline,
    CompiledStep,
    DeclaredOutput,
    LSBRunInputs,
    LocomotiveRunCover,
    LocomotiveRunInputs,
    MissingRuntimeOutputError,
    PipelineRunRequest,
    RunArtifact,
    RunStatus,
    RunStepRequest,
    RunWorkspace,
    StepCommitError,
    StepOutput,
    compile_pipeline,
    resolve_source,
)
from config_prototype.core.configurable.runtime import WORKSPACE_MARKER


def _file(tmp_path: Path, name: str, data: bytes = b"input") -> str:
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def _compiled_lsb(tmp_path: Path) -> CompiledPipeline:
    request = PipelineRunRequest(
        steps=(
            RunStepRequest(
                step_key="step_lsb",
                technique="lsbpp",
                description="LSB++",
                guidenote="",
                inputs=LSBRunInputs(
                    cover=_file(tmp_path, "cover.png"),
                    payload_text="secret",
                ),
            ),
        )
    )
    return compile_pipeline(request)


def _compiled_locomotive(tmp_path: Path) -> CompiledPipeline:
    request = PipelineRunRequest(
        steps=(
            RunStepRequest(
                step_key="step_loco",
                technique="locomotive",
                description="Locomotive",
                guidenote="",
                inputs=LocomotiveRunInputs(
                    covers=(
                        LocomotiveRunCover(
                            _file(tmp_path, "carrier-a.png"),
                            "output_first",
                        ),
                        LocomotiveRunCover(
                            _file(tmp_path, "carrier-b.png"),
                            "output_second",
                        ),
                    ),
                    payload_mode="text",
                    payload_text="secret",
                ),
            ),
        )
    )
    return compile_pipeline(request)


def _fake_adapter_write(
    staged_paths: dict[StepOutput, Path],
    *,
    skip: StepOutput | None = None,
) -> None:
    for reference, path in staged_paths.items():
        if reference != skip:
            path.write_bytes(reference.output_key.encode("utf-8"))


def test_workspace_is_unique_and_isolated_under_configured_base(
    tmp_path: Path,
) -> None:
    base = tmp_path / "runs"
    first = RunWorkspace.create(base)
    second = RunWorkspace.create(base)

    assert first.run_id != second.run_id
    assert first.root != second.root
    assert first.root.parent == base.resolve()
    assert second.root.parent == base.resolve()
    assert (first.root / WORKSPACE_MARKER).read_text(
        encoding="utf-8"
    ) == first.run_id
    assert (second.root / WORKSPACE_MARKER).is_file()

    first.cleanup()
    second.cleanup()
    assert not first.root.exists()
    assert not second.root.exists()


def test_workspace_rejects_unsafe_run_id(tmp_path: Path) -> None:
    base = tmp_path / "runs"

    with pytest.raises(ValueError, match="run_id"):
        RunWorkspace.create(base, run_id="../outside")

    assert not (tmp_path / "outside").exists()


def test_staging_paths_follow_step_layout_and_sanitize_components(
    tmp_path: Path,
) -> None:
    compiled = _compiled_lsb(tmp_path)
    workspace = RunWorkspace.create(tmp_path / "runs")

    paths = workspace.staging_paths(compiled.steps[0])
    path = paths[StepOutput("step_lsb", "result")]

    assert path.relative_to(workspace.root).parts == (
        "steps",
        "001_step_lsb",
        ".staging",
        "result.png",
    )

    unsafe_reference = StepOutput("../unsafe-step", "../../escape")
    unsafe_step = CompiledStep(
        position=2,
        request=RunStepRequest(
            "../unsafe-step",
            "lsbpp",
            "Unsafe identity",
            "",
            LSBRunInputs(),
        ),
        outputs=(DeclaredOutput(unsafe_reference, "png"),),
    )
    unsafe_path = workspace.staging_paths(unsafe_step)[unsafe_reference]

    unsafe_path.relative_to(workspace.root)
    assert ".." not in unsafe_path.relative_to(workspace.root).parts
    assert not (tmp_path / "escape.png").exists()
    workspace.cleanup()


def test_resolver_uses_manual_path_or_current_run_mapping_only(
    tmp_path: Path,
) -> None:
    manual = Path(_file(tmp_path, "manual.png", b"manual"))
    reference = StepOutput("step_lsb", "result")
    committed = Path(_file(tmp_path, "runtime.png", b"runtime"))

    assert resolve_source(str(manual), {}) == manual.resolve()
    assert resolve_source(reference, {reference: committed}) == (
        committed.resolve()
    )

    with pytest.raises(MissingRuntimeOutputError) as missing:
        resolve_source(reference, {})
    assert missing.value.reference == reference

    committed.unlink()
    with pytest.raises(MissingRuntimeOutputError):
        resolve_source(reference, {reference: committed})


def test_artifact_commits_multi_output_step_and_metadata_together(
    tmp_path: Path,
) -> None:
    compiled = _compiled_locomotive(tmp_path)
    workspace = RunWorkspace.create(tmp_path / "runs")
    artifact = RunArtifact(compiled, workspace)
    step = compiled.steps[0]

    staged = artifact.staging_paths(step)
    _fake_adapter_write(staged)
    committed = artifact.commit_step_outputs(
        step,
        staged,
        metadata={"session_id": "session-test"},
    )

    assert artifact.outputs == committed
    assert artifact.step_metadata == {
        "step_loco": {"session_id": "session-test"}
    }
    assert all(path.is_file() for path in committed.values())
    assert all(".staging" not in path.parts for path in committed.values())
    assert {path.name for path in committed.values()} == {
        "output_first.png",
        "output_second.png",
    }

    artifact.succeed()
    assert artifact.status is RunStatus.SUCCEEDED
    artifact.cleanup()
    assert artifact.workspace_cleaned is True
    assert not workspace.root.exists()


def test_missing_staged_output_commits_nothing(
    tmp_path: Path,
) -> None:
    compiled = _compiled_locomotive(tmp_path)
    workspace = RunWorkspace.create(tmp_path / "runs")
    artifact = RunArtifact(compiled, workspace)
    step = compiled.steps[0]
    staged = artifact.staging_paths(step)
    missing_reference = step.outputs[1].reference
    _fake_adapter_write(staged, skip=missing_reference)

    with pytest.raises(StepCommitError, match="Every declared output"):
        artifact.commit_step_outputs(step, staged)

    assert artifact.outputs == {}
    assert artifact.step_metadata == {}
    assert staged[step.outputs[0].reference].is_file()
    assert not staged[missing_reference].exists()
    assert not any(
        path.is_file()
        for path in staged[step.outputs[0].reference].parent.parent.iterdir()
    )
    workspace.cleanup()


def test_partial_move_failure_rolls_every_output_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiled = _compiled_locomotive(tmp_path)
    workspace = RunWorkspace.create(tmp_path / "runs")
    artifact = RunArtifact(compiled, workspace)
    step = compiled.steps[0]
    staged = artifact.staging_paths(step)
    _fake_adapter_write(staged)
    original_replace = Path.replace
    failure_injected = False

    def fail_second_final_move(source: Path, target: Path) -> Path:
        nonlocal failure_injected
        destination = Path(target)
        if (
            not failure_injected
            and destination.name == "output_second.png"
            and destination.parent.name != ".staging"
        ):
            failure_injected = True
            raise OSError("injected move failure")
        return original_replace(source, destination)

    monkeypatch.setattr(Path, "replace", fail_second_final_move)

    with pytest.raises(StepCommitError, match="commit failed"):
        artifact.commit_step_outputs(step, staged)

    assert artifact.outputs == {}
    assert all(path.is_file() for path in staged.values())
    assert not (staged[next(iter(staged))].parent.parent / "output_first.png").exists()
    assert not (staged[next(iter(staged))].parent.parent / "output_second.png").exists()
    workspace.cleanup()


def test_commit_rejects_a_foreign_staging_path(tmp_path: Path) -> None:
    compiled = _compiled_lsb(tmp_path)
    workspace = RunWorkspace.create(tmp_path / "runs")
    artifact = RunArtifact(compiled, workspace)
    step = compiled.steps[0]
    staged = artifact.staging_paths(step)
    reference = step.outputs[0].reference
    external = Path(_file(tmp_path, "foreign.png", b"foreign"))

    with pytest.raises(StepCommitError, match="assigned location"):
        artifact.commit_step_outputs(step, {reference: external})

    assert artifact.outputs == {}
    assert external.read_bytes() == b"foreign"
    workspace.cleanup()


def test_run_artifact_failed_and_cancelled_states(tmp_path: Path) -> None:
    compiled = _compiled_lsb(tmp_path)

    failed_workspace = RunWorkspace.create(tmp_path / "failed-runs")
    failed = RunArtifact(compiled, failed_workspace)
    failed.fail("step_lsb")
    assert failed.status is RunStatus.FAILED
    assert failed.failed_step_key == "step_lsb"
    assert failed_workspace.root.exists()
    with pytest.raises(RuntimeError, match="no longer accepting"):
        failed.staging_paths(compiled.steps[0])
    failed.cleanup()

    cancelled_workspace = RunWorkspace.create(tmp_path / "cancelled-runs")
    cancelled = RunArtifact(compiled, cancelled_workspace)
    cancelled.cancel()
    assert cancelled.status is RunStatus.CANCELLED
    assert cancelled.workspace_cleaned is True
    assert not cancelled_workspace.root.exists()


def test_cleanup_refuses_missing_marker_or_outside_root(
    tmp_path: Path,
) -> None:
    workspace = RunWorkspace.create(tmp_path / "runs")
    sentinel = workspace.root / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    (workspace.root / WORKSPACE_MARKER).unlink()

    with pytest.raises(ValueError, match="Refusing to clean"):
        workspace.cleanup()
    assert sentinel.is_file()

    base = (tmp_path / "safe-base").resolve()
    base.mkdir()
    outside = (tmp_path / "outside").resolve()
    outside.mkdir()
    (outside / WORKSPACE_MARKER).write_text("forged", encoding="utf-8")
    forged = RunWorkspace(base, outside, "forged")

    with pytest.raises(ValueError, match="Refusing to clean"):
        forged.cleanup()
    assert outside.is_dir()


def test_runtime_foundation_imports_without_pyqt() -> None:
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import config_prototype.core.configurable.runtime; "
                "assert not any(name.startswith('PyQt6') "
                "for name in sys.modules)"
            ),
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
