"""Focused tests for Qt-independent pipeline models."""

from dataclasses import FrozenInstanceError

import pytest

from config_prototype.core.configurable import (
    FileSource,
    StepOutput,
    StepOutputInfo,
)


def test_step_output_identifies_one_runtime_output() -> None:
    output = StepOutput(step_key="step_a31f8", output_key="result")
    same_output = StepOutput(step_key="step_a31f8", output_key="result")
    other_output = StepOutput(step_key="step_a31f8", output_key="output_2")

    run_outputs = {output: "workspace/result.png"}

    assert run_outputs[same_output] == "workspace/result.png"
    assert output != other_output


def test_step_output_identity_is_immutable() -> None:
    output = StepOutput(step_key="step_a31f8", output_key="result")

    with pytest.raises(FrozenInstanceError):
        output.output_key = "output_2"


def test_file_source_accepts_manual_path_or_step_output() -> None:
    manual_source: FileSource = "D:/demo/cover.png"
    linked_source: FileSource = StepOutput("step_a31f8", "result")

    assert manual_source == "D:/demo/cover.png"
    assert linked_source == StepOutput("step_a31f8", "result")


def test_step_output_info_keeps_identity_separate_from_display_data() -> None:
    reference = StepOutput("step_a31f8", "result")

    info = StepOutputInfo(
        reference=reference,
        step_number=2,
        technique="lsbpp",
        media_type="png",
        preview_path="D:/demo/cover.png",
    )

    assert info.reference == reference
    assert info.step_number == 2
    assert info.technique == "lsbpp"
    assert info.media_type == "png"
    assert info.preview_path == "D:/demo/cover.png"
