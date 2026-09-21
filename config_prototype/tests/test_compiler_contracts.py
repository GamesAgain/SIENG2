"""Focused tests for the L8.2A compiler contracts."""

import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from config_prototype.core.configurable import (
    CompiledPipeline,
    CompiledStep,
    DeclaredOutput,
    LSBRunInputs,
    LocomotiveRunCover,
    LocomotiveRunInputs,
    MetadataRunInputs,
    PipelineValidationError,
    RunStepRequest,
    StepOutput,
    ValidationIssue,
    declare_step_outputs,
)


def test_compiler_contracts_are_immutable_and_use_tuples() -> None:
    request = RunStepRequest("step_lsb", "lsbpp", "LSB++", "")
    output = DeclaredOutput(StepOutput("step_lsb", "result"), "png")
    step = CompiledStep(
        position=1,
        request=request,
        dependencies=("step_source",),
        outputs=(output,),
    )
    pipeline = CompiledPipeline(
        steps=(step,),
        deliverables=(output.reference,),
    )

    assert isinstance(step.dependencies, tuple)
    assert isinstance(step.outputs, tuple)
    assert isinstance(pipeline.steps, tuple)
    assert isinstance(pipeline.deliverables, tuple)
    with pytest.raises(FrozenInstanceError):
        pipeline.steps = ()


def test_validation_error_preserves_structured_issues() -> None:
    issue = ValidationIssue(
        code="missing_input",
        message="Cover is required.",
        step_key="step_lsb",
        field="cover",
    )
    error = PipelineValidationError((issue,))

    assert error.issues == (issue,)
    assert str(error) == "Pipeline validation failed with 1 issue."
    with pytest.raises(PipelineValidationError) as captured:
        raise error
    assert captured.value.issues == (issue,)
    with pytest.raises(FrozenInstanceError):
        error.issues = ()


def test_lsb_declares_one_png_result_without_validating_inputs() -> None:
    step = RunStepRequest(
        step_key="step_lsb",
        technique="lsbpp",
        description="LSB++",
        guidenote="",
        inputs=LSBRunInputs(),
    )

    assert declare_step_outputs(step) == (
        DeclaredOutput(StepOutput("step_lsb", "result"), "png"),
    )


def test_locomotive_declares_stable_output_keys_in_cover_order() -> None:
    step = RunStepRequest(
        step_key="step_loco",
        technique="locomotive",
        description="Locomotive",
        guidenote="",
        inputs=LocomotiveRunInputs(
            covers=(
                LocomotiveRunCover(
                    source="D:/demo/a.png",
                    output_key="output_a4f91c2e",
                ),
                LocomotiveRunCover(
                    source="D:/demo/b.png",
                    output_key="output_12bd770a",
                ),
            ),
        ),
    )

    assert declare_step_outputs(step) == (
        DeclaredOutput(
            StepOutput("step_loco", "output_a4f91c2e"),
            "png",
        ),
        DeclaredOutput(
            StepOutput("step_loco", "output_12bd770a"),
            "png",
        ),
    )


@pytest.mark.parametrize("media_type", ["png", "mp3"])
def test_metadata_declares_result_using_saved_media_type(
    media_type: str,
) -> None:
    step = RunStepRequest(
        step_key="step_meta",
        technique="metadata",
        description="Metadata",
        guidenote="",
        inputs=MetadataRunInputs(media_type=media_type),
    )

    assert declare_step_outputs(step) == (
        DeclaredOutput(
            StepOutput("step_meta", "result"),
            media_type,
        ),
    )


@pytest.mark.parametrize(
    "step",
    [
        RunStepRequest("step_loco", "locomotive", "Locomotive", ""),
        RunStepRequest("step_meta", "metadata", "Metadata", ""),
        RunStepRequest(
            "step_meta",
            "metadata",
            "Metadata",
            "",
            MetadataRunInputs(media_type="unknown"),
        ),
        RunStepRequest("step_unknown", "unknown", "Unknown", ""),
    ],
)
def test_incomplete_or_unsupported_declarations_are_empty(
    step: RunStepRequest,
) -> None:
    assert declare_step_outputs(step) == ()


def test_compiler_contracts_import_without_pyqt() -> None:
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import config_prototype.core.configurable.compiler; "
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
