"""Focused tests for the L8.2B pipeline compiler."""

from pathlib import Path

import pytest

from config_prototype.core.configurable import (
    ApicImageRequest,
    EncryptionRequest,
    LSBRunInputs,
    LocomotiveRunCover,
    LocomotiveRunInputs,
    MP3MetadataRunPayload,
    MP3SimpleFrameRequest,
    MetadataRunInputs,
    PNGMetadataRunPayload,
    PipelineRunRequest,
    PipelineValidationError,
    RunStepRequest,
    StepOutput,
    compile_pipeline,
)


def _file(tmp_path: Path, name: str) -> str:
    path = tmp_path / name
    path.write_bytes(b"test input")
    return str(path)


def _lsb_step(
    step_key: str,
    cover: str | StepOutput,
    *,
    payload: str = "secret",
    encryption: EncryptionRequest | None = None,
) -> RunStepRequest:
    return RunStepRequest(
        step_key=step_key,
        technique="lsbpp",
        description="LSB++",
        guidenote="",
        inputs=LSBRunInputs(
            cover=cover,
            payload_text=payload,
            encryption=encryption or EncryptionRequest(),
        ),
    )


def _png_metadata_step(
    step_key: str,
    cover: str | StepOutput,
) -> RunStepRequest:
    return RunStepRequest(
        step_key=step_key,
        technique="metadata",
        description="PNG Metadata",
        guidenote="",
        inputs=MetadataRunInputs(
            cover=cover,
            media_type="png",
            payload=PNGMetadataRunPayload(
                entries=(("Comment", "message"),),
            ),
        ),
    )


def _mp3_metadata_step(
    step_key: str,
    cover: str | StepOutput,
    *,
    apic_images: tuple[ApicImageRequest, ...] = (),
) -> RunStepRequest:
    return RunStepRequest(
        step_key=step_key,
        technique="metadata",
        description="MP3 Metadata",
        guidenote="",
        inputs=MetadataRunInputs(
            cover=cover,
            media_type="mp3",
            payload=MP3MetadataRunPayload(
                frames=(MP3SimpleFrameRequest("TIT2", "Title"),),
                apic_images=apic_images,
            ),
        ),
    )


def _issue_codes(error: PipelineValidationError) -> list[str]:
    return [issue.code for issue in error.issues]


def test_compile_valid_three_step_acceptance_pipeline(
    tmp_path: Path,
) -> None:
    first_output = StepOutput("step_loco", "output_a4f91c2e")
    second_output = StepOutput("step_loco", "output_12bd770a")
    locomotive = RunStepRequest(
        step_key="step_loco",
        technique="locomotive",
        description="Locomotive",
        guidenote="",
        inputs=LocomotiveRunInputs(
            covers=(
                LocomotiveRunCover(
                    _file(tmp_path, "carrier-a.png"),
                    first_output.output_key,
                ),
                LocomotiveRunCover(
                    _file(tmp_path, "carrier-b.png"),
                    second_output.output_key,
                ),
            ),
            payload_mode="files",
            payload_files=(_file(tmp_path, "secret.pdf"),),
        ),
    )
    request = PipelineRunRequest(
        steps=(
            locomotive,
            _lsb_step("step_lsb", first_output, payload="123"),
            _png_metadata_step("step_meta", second_output),
        )
    )

    compiled = compile_pipeline(request)

    assert [step.position for step in compiled.steps] == [1, 2, 3]
    assert [step.request.step_key for step in compiled.steps] == [
        "step_loco",
        "step_lsb",
        "step_meta",
    ]
    assert compiled.steps[0].dependencies == ()
    assert compiled.steps[1].dependencies == ("step_loco",)
    assert compiled.steps[2].dependencies == ("step_loco",)
    assert [output.reference for output in compiled.steps[0].outputs] == [
        first_output,
        second_output,
    ]
    assert compiled.deliverables == (
        StepOutput("step_lsb", "result"),
        StepOutput("step_meta", "result"),
    )


def test_compile_rejects_empty_and_unconfigured_pipeline() -> None:
    with pytest.raises(PipelineValidationError) as empty:
        compile_pipeline(PipelineRunRequest())
    assert _issue_codes(empty.value) == ["empty_pipeline"]

    request = PipelineRunRequest(
        steps=(RunStepRequest("step_lsb", "lsbpp", "LSB++", ""),)
    )
    with pytest.raises(PipelineValidationError) as unconfigured:
        compile_pipeline(request)
    assert "unconfigured_step" in _issue_codes(unconfigured.value)


def test_compile_rejects_duplicate_step_and_output_keys(
    tmp_path: Path,
) -> None:
    duplicate_steps = PipelineRunRequest(
        steps=(
            _lsb_step("step_same", _file(tmp_path, "one.png")),
            _lsb_step("step_same", _file(tmp_path, "two.png")),
        )
    )
    with pytest.raises(PipelineValidationError) as duplicate_step_error:
        compile_pipeline(duplicate_steps)
    assert _issue_codes(duplicate_step_error.value).count(
        "duplicate_step_key"
    ) == 2

    duplicate_outputs = PipelineRunRequest(
        steps=(
            RunStepRequest(
                "step_loco",
                "locomotive",
                "Locomotive",
                "",
                LocomotiveRunInputs(
                    covers=(
                        LocomotiveRunCover(
                            _file(tmp_path, "cover-a.png"),
                            "output_same",
                        ),
                        LocomotiveRunCover(
                            _file(tmp_path, "cover-b.png"),
                            "output_same",
                        ),
                    ),
                    payload_mode="files",
                    payload_files=(_file(tmp_path, "payload.bin"),),
                ),
            ),
        )
    )
    with pytest.raises(PipelineValidationError) as duplicate_output_error:
        compile_pipeline(duplicate_outputs)
    assert _issue_codes(duplicate_output_error.value).count(
        "duplicate_output_key"
    ) == 1


def test_compile_reports_missing_self_and_forward_references(
    tmp_path: Path,
) -> None:
    request = PipelineRunRequest(
        steps=(
            _lsb_step(
                "step_missing_consumer",
                StepOutput("step_missing", "result"),
            ),
            _lsb_step(
                "step_forward_consumer",
                StepOutput("step_later", "result"),
            ),
            _lsb_step("step_later", _file(tmp_path, "later.png")),
            _lsb_step(
                "step_missing_output",
                StepOutput("step_later", "not_declared"),
            ),
            _lsb_step(
                "step_self",
                StepOutput("step_self", "result"),
            ),
        )
    )

    with pytest.raises(PipelineValidationError) as captured:
        compile_pipeline(request)

    codes = _issue_codes(captured.value)
    assert "missing_step_reference" in codes
    assert "forward_reference" in codes
    assert "missing_output_reference" in codes
    assert "self_reference" in codes


def test_compile_rejects_incompatible_linked_media(
    tmp_path: Path,
) -> None:
    request = PipelineRunRequest(
        steps=(
            _mp3_metadata_step(
                "step_mp3",
                _file(tmp_path, "carrier.mp3"),
            ),
            _lsb_step(
                "step_lsb",
                StepOutput("step_mp3", "result"),
            ),
        )
    )

    with pytest.raises(PipelineValidationError) as captured:
        compile_pipeline(request)

    assert "incompatible_output_media" in _issue_codes(captured.value)


def test_compile_enforces_single_consumer_across_input_roles(
    tmp_path: Path,
) -> None:
    shared_output = StepOutput("step_source", "result")
    request = PipelineRunRequest(
        steps=(
            _lsb_step("step_source", _file(tmp_path, "source.png")),
            _lsb_step("step_first", shared_output),
            _png_metadata_step("step_second", shared_output),
        )
    )

    with pytest.raises(PipelineValidationError) as captured:
        compile_pipeline(request)

    consumed_issues = [
        issue
        for issue in captured.value.issues
        if issue.code == "output_already_consumed"
    ]
    assert len(consumed_issues) == 1
    assert consumed_issues[0].step_key == "step_second"
    assert consumed_issues[0].field == "cover"


def test_compile_collects_locomotive_payload_and_metadata_apic_links(
    tmp_path: Path,
) -> None:
    mp3_output = StepOutput("step_mp3", "result")
    png_output = StepOutput("step_png", "result")
    request = PipelineRunRequest(
        steps=(
            _mp3_metadata_step(
                "step_mp3",
                _file(tmp_path, "source.mp3"),
            ),
            _lsb_step("step_png", _file(tmp_path, "source.png")),
            RunStepRequest(
                "step_loco",
                "locomotive",
                "Locomotive",
                "",
                LocomotiveRunInputs(
                    covers=(
                        LocomotiveRunCover(
                            _file(tmp_path, "loco-cover.png"),
                            "output_loco",
                        ),
                    ),
                    payload_mode="files",
                    payload_files=(mp3_output,),
                ),
            ),
            _mp3_metadata_step(
                "step_apic",
                _file(tmp_path, "apic-cover.mp3"),
                apic_images=(
                    ApicImageRequest(
                        image=png_output,
                        picture_type=3,
                        description="Front cover",
                    ),
                ),
            ),
        )
    )

    compiled = compile_pipeline(request)

    assert compiled.steps[2].dependencies == ("step_mp3",)
    assert compiled.steps[3].dependencies == ("step_png",)
    assert compiled.deliverables == (
        StepOutput("step_loco", "output_loco"),
        StepOutput("step_apic", "result"),
    )


def test_compile_deduplicates_dependencies_from_same_producer(
    tmp_path: Path,
) -> None:
    first_output = StepOutput("step_source", "output_first")
    second_output = StepOutput("step_source", "output_second")
    request = PipelineRunRequest(
        steps=(
            RunStepRequest(
                "step_source",
                "locomotive",
                "Source",
                "",
                LocomotiveRunInputs(
                    covers=(
                        LocomotiveRunCover(
                            _file(tmp_path, "source-a.png"),
                            first_output.output_key,
                        ),
                        LocomotiveRunCover(
                            _file(tmp_path, "source-b.png"),
                            second_output.output_key,
                        ),
                    ),
                    payload_mode="text",
                    payload_text="payload",
                ),
            ),
            RunStepRequest(
                "step_consumer",
                "locomotive",
                "Consumer",
                "",
                LocomotiveRunInputs(
                    covers=(
                        LocomotiveRunCover(first_output, "output_result"),
                    ),
                    payload_mode="files",
                    payload_files=(second_output,),
                ),
            ),
        )
    )

    compiled = compile_pipeline(request)

    assert compiled.steps[1].dependencies == ("step_source",)
    assert compiled.deliverables == (
        StepOutput("step_consumer", "output_result"),
    )


def test_compile_validates_manual_files_and_encryption_without_secrets(
    tmp_path: Path,
) -> None:
    secret = "never-show-this-password"
    request = PipelineRunRequest(
        steps=(
            _lsb_step(
                "step_lsb",
                str(tmp_path / "missing.png"),
                payload="",
                encryption=EncryptionRequest(
                    mode="password",
                    password="",
                ),
            ),
            _lsb_step(
                "step_key",
                _file(tmp_path, "key-cover.png"),
                encryption=EncryptionRequest(
                    mode="public_key",
                    password=secret,
                    public_key_path=str(tmp_path / "missing.pem"),
                ),
            ),
            _lsb_step(
                "step_media",
                _file(tmp_path, "not-an-image.txt"),
            ),
        )
    )

    with pytest.raises(PipelineValidationError) as captured:
        compile_pipeline(request)

    codes = _issue_codes(captured.value)
    assert "file_unavailable" in codes
    assert "missing_payload" in codes
    assert "missing_password" in codes
    assert "public_key_unavailable" in codes
    assert "incompatible_manual_media" in codes
    assert secret not in str(captured.value)
    assert secret not in repr(captured.value)


def test_compile_rejects_input_type_mismatch(tmp_path: Path) -> None:
    request = PipelineRunRequest(
        steps=(
            RunStepRequest(
                "step_lsb",
                "lsbpp",
                "Wrong inputs",
                "",
                MetadataRunInputs(
                    cover=_file(tmp_path, "cover.png"),
                    media_type="png",
                    payload=PNGMetadataRunPayload(
                        entries=(("Comment", "value"),),
                    ),
                ),
            ),
        )
    )

    with pytest.raises(PipelineValidationError) as captured:
        compile_pipeline(request)

    assert _issue_codes(captured.value) == ["input_type_mismatch"]


def test_compile_aggregates_multiple_issues() -> None:
    request = PipelineRunRequest(
        steps=(
            RunStepRequest(
                "",
                "lsbpp",
                "Broken LSB++",
                "",
                LSBRunInputs(
                    cover=None,
                    payload_text="",
                    encryption=EncryptionRequest(mode="unsupported"),
                ),
            ),
            RunStepRequest(
                "step_unknown",
                "unknown",
                "Unknown",
                "",
            ),
        )
    )

    with pytest.raises(PipelineValidationError) as captured:
        compile_pipeline(request)

    codes = set(_issue_codes(captured.value))
    assert {
        "empty_step_key",
        "missing_source",
        "missing_payload",
        "unsupported_encryption_mode",
        "unsupported_technique",
    } <= codes
    assert len(captured.value.issues) >= 5
