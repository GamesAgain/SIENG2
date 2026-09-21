"""Immutable contracts used by the configurable pipeline compiler."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .run_request import (
    EncryptionRequest,
    LSBRunInputs,
    LocomotiveRunInputs,
    MP3ComplexFrameInstanceRequest,
    MP3ComplexFrameRequest,
    MP3MetadataRunPayload,
    MP3SimpleFrameRequest,
    MetadataRunInputs,
    PNGMetadataRunPayload,
    PipelineRunRequest,
    RunStepRequest,
)
from .step_output import FileSource, StepOutput


RESULT_OUTPUT_KEY = "result"
SUPPORTED_MEDIA_TYPES = frozenset({"png", "mp3"})


@dataclass(frozen=True, slots=True)
class DeclaredOutput:
    """One output a compiled step promises to create."""

    reference: StepOutput
    media_type: str


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One compiler issue with optional step and field context."""

    code: str
    message: str
    step_key: str | None = None
    field: str | None = None


@dataclass(frozen=True, slots=True)
class PipelineValidationError(ValueError):
    """Aggregate validation failure returned before execution starts."""

    issues: tuple[ValidationIssue, ...]

    def __post_init__(self) -> None:
        count = len(self.issues)
        suffix = "issue" if count == 1 else "issues"
        ValueError.__init__(
            self,
            f"Pipeline validation failed with {count} {suffix}.",
        )


@dataclass(frozen=True, slots=True)
class CompiledStep:
    """One validated step in deterministic Canvas order."""

    position: int
    request: RunStepRequest
    dependencies: tuple[str, ...] = ()
    outputs: tuple[DeclaredOutput, ...] = ()


@dataclass(frozen=True, slots=True)
class CompiledPipeline:
    """Immutable execution plan produced by the compiler."""

    steps: tuple[CompiledStep, ...] = ()
    deliverables: tuple[StepOutput, ...] = ()


def declare_step_outputs(
    step: RunStepRequest,
) -> tuple[DeclaredOutput, ...]:
    """Describe output identities without validating the whole pipeline."""

    if step.technique == "lsbpp":
        return (
            DeclaredOutput(
                reference=StepOutput(step.step_key, RESULT_OUTPUT_KEY),
                media_type="png",
            ),
        )

    if step.technique == "locomotive" and isinstance(
        step.inputs,
        LocomotiveRunInputs,
    ):
        return tuple(
            DeclaredOutput(
                reference=StepOutput(step.step_key, cover.output_key),
                media_type="png",
            )
            for cover in step.inputs.covers
        )

    if step.technique == "metadata" and isinstance(
        step.inputs,
        MetadataRunInputs,
    ):
        media_type = step.inputs.media_type
        if media_type in SUPPORTED_MEDIA_TYPES:
            return (
                DeclaredOutput(
                    reference=StepOutput(step.step_key, RESULT_OUTPUT_KEY),
                    media_type=media_type,
                ),
            )

    return ()


@dataclass(frozen=True, slots=True)
class _SourceUse:
    """One linked source and the media accepted by its input role."""

    reference: StepOutput
    field: str
    accepted_media: tuple[str, ...]


def _add_issue(
    issues: list[ValidationIssue],
    code: str,
    message: str,
    *,
    step_key: str | None = None,
    field: str | None = None,
) -> None:
    issues.append(
        ValidationIssue(
            code=code,
            message=message,
            step_key=step_key,
            field=field,
        )
    )


def _available_file(path: str) -> bool:
    try:
        return Path(path).is_file()
    except OSError:
        return False


def _validate_manual_file(
    path: str,
    *,
    issues: list[ValidationIssue],
    step_key: str,
    field: str,
    allowed_extensions: frozenset[str] | None = None,
) -> None:
    if not path.strip():
        _add_issue(
            issues,
            "missing_file",
            "A file is required.",
            step_key=step_key,
            field=field,
        )
        return

    if allowed_extensions is not None:
        suffix = Path(path).suffix.lower()
        if suffix not in allowed_extensions:
            expected = ", ".join(sorted(allowed_extensions))
            _add_issue(
                issues,
                "incompatible_manual_media",
                f"The file must use one of these formats: {expected}.",
                step_key=step_key,
                field=field,
            )

    if not _available_file(path):
        _add_issue(
            issues,
            "file_unavailable",
            "The selected file is unavailable.",
            step_key=step_key,
            field=field,
        )


def _validate_source(
    source: FileSource | None,
    *,
    issues: list[ValidationIssue],
    step_key: str,
    field: str,
    allowed_extensions: frozenset[str] | None = None,
) -> None:
    if source is None:
        _add_issue(
            issues,
            "missing_source",
            "An input source is required.",
            step_key=step_key,
            field=field,
        )
    elif isinstance(source, str):
        _validate_manual_file(
            source,
            issues=issues,
            step_key=step_key,
            field=field,
            allowed_extensions=allowed_extensions,
        )
    elif not isinstance(source, StepOutput):
        _add_issue(
            issues,
            "invalid_source_type",
            "The source must be a file path or a previous output.",
            step_key=step_key,
            field=field,
        )


def _validate_encryption(
    encryption: EncryptionRequest,
    *,
    issues: list[ValidationIssue],
    step_key: str,
) -> None:
    if not isinstance(encryption, EncryptionRequest):
        _add_issue(
            issues,
            "invalid_encryption",
            "Encryption settings are invalid.",
            step_key=step_key,
            field="encryption",
        )
        return

    if encryption.mode is None:
        return
    if encryption.mode == "password":
        if (
            not isinstance(encryption.password, str)
            or not encryption.password
        ):
            _add_issue(
                issues,
                "missing_password",
                "A password is required for password encryption.",
                step_key=step_key,
                field="encryption.password",
            )
        return
    if encryption.mode == "public_key":
        public_key_path = encryption.public_key_path
        if (
            not isinstance(public_key_path, str)
            or not public_key_path.strip()
        ):
            _add_issue(
                issues,
                "missing_public_key",
                "A public key file is required for public-key encryption.",
                step_key=step_key,
                field="encryption.public_key_path",
            )
        elif not _available_file(public_key_path):
            _add_issue(
                issues,
                "public_key_unavailable",
                "The selected public key file is unavailable.",
                step_key=step_key,
                field="encryption.public_key_path",
            )
        return

    _add_issue(
        issues,
        "unsupported_encryption_mode",
        "The encryption mode is unsupported.",
        step_key=step_key,
        field="encryption.mode",
    )


def _validate_lsb_inputs(
    inputs: LSBRunInputs,
    *,
    issues: list[ValidationIssue],
    step_key: str,
) -> None:
    _validate_source(
        inputs.cover,
        issues=issues,
        step_key=step_key,
        field="cover",
        allowed_extensions=frozenset({".png"}),
    )
    if not isinstance(inputs.payload_text, str) or not inputs.payload_text.strip():
        _add_issue(
            issues,
            "missing_payload",
            "LSB++ requires a text payload.",
            step_key=step_key,
            field="payload_text",
        )
    _validate_encryption(
        inputs.encryption,
        issues=issues,
        step_key=step_key,
    )


def _validate_locomotive_inputs(
    inputs: LocomotiveRunInputs,
    *,
    issues: list[ValidationIssue],
    step_key: str,
) -> None:
    if not inputs.covers:
        _add_issue(
            issues,
            "missing_cover",
            "Locomotive requires at least one PNG cover.",
            step_key=step_key,
            field="covers",
        )

    for index, cover in enumerate(inputs.covers):
        source_field = f"covers[{index}].source"
        _validate_source(
            cover.source,
            issues=issues,
            step_key=step_key,
            field=source_field,
            allowed_extensions=frozenset({".png"}),
        )

    if inputs.payload_mode == "files":
        if not inputs.payload_files:
            _add_issue(
                issues,
                "missing_payload",
                "Locomotive requires at least one payload file.",
                step_key=step_key,
                field="payload_files",
            )
        for index, source in enumerate(inputs.payload_files):
            _validate_source(
                source,
                issues=issues,
                step_key=step_key,
                field=f"payload_files[{index}]",
            )
    elif inputs.payload_mode == "text":
        if (
            not isinstance(inputs.payload_text, str)
            or not inputs.payload_text.strip()
        ):
            _add_issue(
                issues,
                "missing_payload",
                "Locomotive requires a text payload in text mode.",
                step_key=step_key,
                field="payload_text",
            )
    else:
        _add_issue(
            issues,
            "unsupported_payload_mode",
            "The Locomotive payload mode is unsupported.",
            step_key=step_key,
            field="payload_mode",
        )

    _validate_encryption(
        inputs.encryption,
        issues=issues,
        step_key=step_key,
    )


def _validate_png_payload(
    payload: PNGMetadataRunPayload,
    *,
    issues: list[ValidationIssue],
    step_key: str,
) -> None:
    if not payload.entries:
        _add_issue(
            issues,
            "missing_payload",
            "PNG Metadata requires at least one text entry.",
            step_key=step_key,
            field="payload.entries",
        )

    keywords: set[str] = set()
    for index, entry in enumerate(payload.entries):
        field = f"payload.entries[{index}]"
        if not isinstance(entry, tuple) or len(entry) != 2:
            _add_issue(
                issues,
                "invalid_png_entry",
                "PNG metadata entries must contain a keyword and value.",
                step_key=step_key,
                field=field,
            )
            continue
        keyword, value = entry
        if not isinstance(keyword, str) or not keyword.strip():
            _add_issue(
                issues,
                "missing_metadata_keyword",
                "PNG metadata keywords cannot be empty.",
                step_key=step_key,
                field=field,
            )
        elif keyword in keywords:
            _add_issue(
                issues,
                "duplicate_metadata_keyword",
                "PNG metadata keywords must be unique.",
                step_key=step_key,
                field=field,
            )
        else:
            keywords.add(keyword)
        if not isinstance(value, str) or not value.strip():
            _add_issue(
                issues,
                "missing_metadata_value",
                "PNG metadata values cannot be empty.",
                step_key=step_key,
                field=field,
            )


def _validate_mp3_payload(
    payload: MP3MetadataRunPayload,
    *,
    issues: list[ValidationIssue],
    step_key: str,
) -> None:
    if not payload.frames and not payload.apic_images:
        _add_issue(
            issues,
            "missing_payload",
            "MP3 Metadata requires at least one frame or APIC image.",
            step_key=step_key,
            field="payload",
        )

    for index, frame in enumerate(payload.frames):
        field = f"payload.frames[{index}]"
        if isinstance(frame, MP3SimpleFrameRequest):
            if (
                not isinstance(frame.frame_id, str)
                or not frame.frame_id.strip()
                or not isinstance(frame.value, str)
                or not frame.value.strip()
            ):
                _add_issue(
                    issues,
                    "invalid_mp3_frame",
                    "MP3 text frames require an ID and value.",
                    step_key=step_key,
                    field=field,
                )
        elif isinstance(frame, MP3ComplexFrameRequest):
            if (
                not isinstance(frame.frame_id, str)
                or not frame.frame_id.strip()
                or not frame.instances
            ):
                _add_issue(
                    issues,
                    "invalid_mp3_frame",
                    "Complex MP3 frames require an ID and instance.",
                    step_key=step_key,
                    field=field,
                )
            for instance_index, instance in enumerate(frame.instances):
                instance_field = f"{field}.instances[{instance_index}]"
                if not isinstance(instance, MP3ComplexFrameInstanceRequest):
                    _add_issue(
                        issues,
                        "invalid_mp3_frame",
                        "The complex MP3 frame instance is invalid.",
                        step_key=step_key,
                        field=instance_field,
                    )
                    continue
                values = (
                    instance.lang,
                    instance.desc,
                    instance.text,
                    instance.url,
                )
                if any(
                    value is not None and not isinstance(value, str)
                    for value in values
                ) or not any(
                    isinstance(value, str) and value.strip()
                    for value in values
                ):
                    _add_issue(
                        issues,
                        "invalid_mp3_frame",
                        "Complex MP3 frame instances require text values.",
                        step_key=step_key,
                        field=instance_field,
                    )
        else:
            _add_issue(
                issues,
                "invalid_mp3_frame",
                "The MP3 frame type is unsupported.",
                step_key=step_key,
                field=field,
            )

    picture_types: set[int] = set()
    descriptions: set[str] = set()
    for index, image in enumerate(payload.apic_images):
        field = f"payload.apic_images[{index}]"
        _validate_source(
            image.image,
            issues=issues,
            step_key=step_key,
            field=f"{field}.image",
            allowed_extensions=frozenset({".jpg", ".jpeg", ".png"}),
        )
        if (
            not isinstance(image.picture_type, int)
            or isinstance(image.picture_type, bool)
            or not 0 <= image.picture_type <= 20
        ):
            _add_issue(
                issues,
                "invalid_apic_picture_type",
                "APIC picture type must be an integer from 0 to 20.",
                step_key=step_key,
                field=f"{field}.picture_type",
            )
        elif image.picture_type in picture_types:
            _add_issue(
                issues,
                "duplicate_apic_picture_type",
                "Each APIC picture type can be used only once.",
                step_key=step_key,
                field=f"{field}.picture_type",
            )
        else:
            picture_types.add(image.picture_type)

        if not isinstance(image.description, str):
            _add_issue(
                issues,
                "invalid_apic_description",
                "APIC descriptions must be text.",
                step_key=step_key,
                field=f"{field}.description",
            )
            continue
        description = image.description.strip()
        if len(description) > 64:
            _add_issue(
                issues,
                "invalid_apic_description",
                "APIC descriptions cannot exceed 64 characters.",
                step_key=step_key,
                field=f"{field}.description",
            )
        description_key = description.casefold()
        if description_key in descriptions:
            _add_issue(
                issues,
                "duplicate_apic_description",
                "APIC descriptions must be unique, ignoring letter case.",
                step_key=step_key,
                field=f"{field}.description",
            )
        else:
            descriptions.add(description_key)


def _validate_metadata_inputs(
    inputs: MetadataRunInputs,
    *,
    issues: list[ValidationIssue],
    step_key: str,
) -> None:
    _validate_source(
        inputs.cover,
        issues=issues,
        step_key=step_key,
        field="cover",
        allowed_extensions=frozenset({".png", ".mp3"}),
    )

    media_type = inputs.media_type
    if (
        not isinstance(media_type, str)
        or media_type not in SUPPORTED_MEDIA_TYPES
    ):
        _add_issue(
            issues,
            "unsupported_media_type",
            "Metadata media type must be PNG or MP3.",
            step_key=step_key,
            field="media_type",
        )
    elif isinstance(inputs.cover, str):
        cover_media = Path(inputs.cover).suffix.lower().lstrip(".")
        if cover_media in SUPPORTED_MEDIA_TYPES and cover_media != media_type:
            _add_issue(
                issues,
                "incompatible_manual_media",
                "The Metadata payload type does not match the cover file.",
                step_key=step_key,
                field="cover",
            )

    payload = inputs.payload
    if payload is None:
        _add_issue(
            issues,
            "missing_payload",
            "Metadata requires a payload.",
            step_key=step_key,
            field="payload",
        )
    elif media_type == "png" and isinstance(payload, PNGMetadataRunPayload):
        _validate_png_payload(payload, issues=issues, step_key=step_key)
    elif media_type == "mp3" and isinstance(payload, MP3MetadataRunPayload):
        _validate_mp3_payload(payload, issues=issues, step_key=step_key)
    else:
        _add_issue(
            issues,
            "payload_media_mismatch",
            "The Metadata payload does not match its media type.",
            step_key=step_key,
            field="payload",
        )


def _validate_step_inputs(
    step: RunStepRequest,
    issues: list[ValidationIssue],
) -> None:
    step_key = step.step_key if isinstance(step.step_key, str) else None
    expected_type = (
        {
            "lsbpp": LSBRunInputs,
            "locomotive": LocomotiveRunInputs,
            "metadata": MetadataRunInputs,
        }.get(step.technique)
        if isinstance(step.technique, str)
        else None
    )

    if expected_type is None:
        _add_issue(
            issues,
            "unsupported_technique",
            "The step technique is unsupported.",
            step_key=step_key,
            field="technique",
        )
        return
    if step.inputs is None:
        _add_issue(
            issues,
            "unconfigured_step",
            "The step has no saved technique inputs.",
            step_key=step_key,
            field="inputs",
        )
        return
    if not isinstance(step.inputs, expected_type):
        _add_issue(
            issues,
            "input_type_mismatch",
            "The saved inputs do not match the step technique.",
            step_key=step_key,
            field="inputs",
        )
        return

    if isinstance(step.inputs, LSBRunInputs):
        _validate_lsb_inputs(step.inputs, issues=issues, step_key=step.step_key)
    elif isinstance(step.inputs, LocomotiveRunInputs):
        _validate_locomotive_inputs(
            step.inputs,
            issues=issues,
            step_key=step.step_key,
        )
    else:
        _validate_metadata_inputs(
            step.inputs,
            issues=issues,
            step_key=step.step_key,
        )


def _source_uses(step: RunStepRequest) -> tuple[_SourceUse, ...]:
    inputs = step.inputs
    uses: list[_SourceUse] = []

    if isinstance(inputs, LSBRunInputs):
        if isinstance(inputs.cover, StepOutput):
            uses.append(_SourceUse(inputs.cover, "cover", ("png",)))
    elif isinstance(inputs, LocomotiveRunInputs):
        uses.extend(
            _SourceUse(cover.source, f"covers[{index}].source", ("png",))
            for index, cover in enumerate(inputs.covers)
            if isinstance(cover.source, StepOutput)
        )
        if inputs.payload_mode == "files":
            uses.extend(
                _SourceUse(
                    source,
                    f"payload_files[{index}]",
                    ("png", "mp3"),
                )
                for index, source in enumerate(inputs.payload_files)
                if isinstance(source, StepOutput)
            )
    elif isinstance(inputs, MetadataRunInputs):
        accepted_cover_media = (
            (inputs.media_type,)
            if isinstance(inputs.media_type, str)
            and inputs.media_type in SUPPORTED_MEDIA_TYPES
            else ()
        )
        if isinstance(inputs.cover, StepOutput):
            uses.append(
                _SourceUse(inputs.cover, "cover", accepted_cover_media)
            )
        if isinstance(inputs.payload, MP3MetadataRunPayload):
            uses.extend(
                _SourceUse(
                    image.image,
                    f"payload.apic_images[{index}].image",
                    ("png",),
                )
                for index, image in enumerate(inputs.payload.apic_images)
                if isinstance(image.image, StepOutput)
            )

    return tuple(uses)


def _valid_reference_identity(reference: StepOutput) -> bool:
    return (
        isinstance(reference.step_key, str)
        and bool(reference.step_key.strip())
        and isinstance(reference.output_key, str)
        and bool(reference.output_key.strip())
    )


def compile_pipeline(request: PipelineRunRequest) -> CompiledPipeline:
    """Validate a Run Request and build an immutable ordered plan."""

    issues: list[ValidationIssue] = []
    if not request.steps:
        raise PipelineValidationError(
            (
                ValidationIssue(
                    code="empty_pipeline",
                    message="The pipeline must contain at least one step.",
                    field="steps",
                ),
            )
        )

    step_indices: dict[str, list[int]] = {}
    declared_by_index: list[tuple[DeclaredOutput, ...]] = []

    for index, step in enumerate(request.steps):
        step_key = step.step_key
        issue_step_key = step_key if isinstance(step_key, str) else None
        if not isinstance(step_key, str) or not step_key.strip():
            _add_issue(
                issues,
                "empty_step_key",
                "Every step requires a stable key.",
                field="step_key",
            )
        else:
            step_indices.setdefault(step_key, []).append(index)

        _validate_step_inputs(step, issues)
        outputs = declare_step_outputs(step)
        declared_by_index.append(outputs)

        seen_output_keys: set[str] = set()
        for output_index, output in enumerate(outputs):
            output_key = output.reference.output_key
            field = f"outputs[{output_index}].output_key"
            if not isinstance(output_key, str) or not output_key.strip():
                _add_issue(
                    issues,
                    "empty_output_key",
                    "Every declared output requires a stable key.",
                    step_key=issue_step_key,
                    field=field,
                )
            elif output_key in seen_output_keys:
                _add_issue(
                    issues,
                    "duplicate_output_key",
                    "Output keys must be unique within a step.",
                    step_key=issue_step_key,
                    field=field,
                )
            else:
                seen_output_keys.add(output_key)

    for step_key, indices in step_indices.items():
        if len(indices) > 1:
            for index in indices:
                _add_issue(
                    issues,
                    "duplicate_step_key",
                    "Step keys must be unique within the pipeline.",
                    step_key=step_key,
                    field="step_key",
                )

    dependencies_by_index: list[list[str]] = [
        [] for _step in request.steps
    ]
    consumed_outputs: set[StepOutput] = set()
    claimed_outputs: dict[StepOutput, tuple[int, str]] = {}

    for consumer_index, step in enumerate(request.steps):
        issue_step_key = (
            step.step_key if isinstance(step.step_key, str) else None
        )
        for use in _source_uses(step):
            reference = use.reference
            if not _valid_reference_identity(reference):
                _add_issue(
                    issues,
                    "invalid_output_reference",
                    "Previous-output references require stable step and output keys.",
                    step_key=issue_step_key,
                    field=use.field,
                )
                continue

            producer_indices = step_indices.get(reference.step_key, [])
            if not producer_indices:
                _add_issue(
                    issues,
                    "missing_step_reference",
                    "The referenced producer step does not exist.",
                    step_key=issue_step_key,
                    field=use.field,
                )
                continue
            if len(producer_indices) > 1:
                _add_issue(
                    issues,
                    "ambiguous_step_reference",
                    "The referenced producer key is not unique.",
                    step_key=issue_step_key,
                    field=use.field,
                )
                continue

            producer_index = producer_indices[0]
            if producer_index == consumer_index:
                _add_issue(
                    issues,
                    "self_reference",
                    "A step cannot consume its own output.",
                    step_key=issue_step_key,
                    field=use.field,
                )
                continue
            if producer_index > consumer_index:
                _add_issue(
                    issues,
                    "forward_reference",
                    "A step cannot consume output from a later step.",
                    step_key=issue_step_key,
                    field=use.field,
                )
                continue

            declared_output = next(
                (
                    output
                    for output in declared_by_index[producer_index]
                    if output.reference.output_key == reference.output_key
                ),
                None,
            )
            if declared_output is None:
                _add_issue(
                    issues,
                    "missing_output_reference",
                    "The referenced output is not declared by its producer.",
                    step_key=issue_step_key,
                    field=use.field,
                )
                continue

            if (
                use.accepted_media
                and declared_output.media_type not in use.accepted_media
            ):
                expected = ", ".join(
                    media.upper() for media in use.accepted_media
                )
                _add_issue(
                    issues,
                    "incompatible_output_media",
                    f"The linked output must use one of these media types: {expected}.",
                    step_key=issue_step_key,
                    field=use.field,
                )

            previous_claim = claimed_outputs.get(reference)
            if previous_claim is not None:
                _add_issue(
                    issues,
                    "output_already_consumed",
                    "A previous output can be consumed by only one input role.",
                    step_key=issue_step_key,
                    field=use.field,
                )
            else:
                claimed_outputs[reference] = (consumer_index, use.field)

            consumed_outputs.add(reference)
            dependencies = dependencies_by_index[consumer_index]
            if reference.step_key not in dependencies:
                dependencies.append(reference.step_key)

    if issues:
        raise PipelineValidationError(tuple(issues))

    compiled_steps = tuple(
        CompiledStep(
            position=index + 1,
            request=step,
            dependencies=tuple(dependencies_by_index[index]),
            outputs=declared_by_index[index],
        )
        for index, step in enumerate(request.steps)
    )
    deliverables = tuple(
        output.reference
        for outputs in declared_by_index
        for output in outputs
        if output.reference not in consumed_outputs
    )
    return CompiledPipeline(
        steps=compiled_steps,
        deliverables=deliverables,
    )
