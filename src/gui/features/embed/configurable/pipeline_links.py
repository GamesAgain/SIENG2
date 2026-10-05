"""Output declarations and linked-input lifecycle for saved pipeline drafts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from src.core.configurable.step_output import StepOutput, StepOutputInfo
from src.gui.features.embed.forms.lsb_form import LSBInputsDraft
from src.gui.features.embed.forms.locomotive_form import LocomotiveInputsDraft
from src.gui.features.embed.forms.metadata_form import MetadataInputsDraft
from src.gui.features.embed.forms.metadata.mp3_draft import MP3MetadataDraft, validate_attached_pictures
from src.gui.features.embed.forms.metadata.png_form import PNGMetadataDraft

if TYPE_CHECKING:
    from src.gui.features.embed.configurable.pipeline_draft import PipelineStepDraft


def declared_step_outputs(step: PipelineStepDraft, step_number: int) -> list[StepOutputInfo]:
    """Describe expected outputs; producer readiness is checked separately."""
    draft = step.technique_inputs
    if step.technique == "lsbpp" and isinstance(draft, LSBInputsDraft):
        outputs = [("result", "png", draft.cover, None)]
    elif step.technique == "locomotive" and isinstance(draft, LocomotiveInputsDraft):
        outputs = []
        for number, cover in enumerate(draft.covers, start=1):
            outputs.append((cover.output_key, "png", cover.source, f"Output {number}"))
    elif step.technique == "metadata" and isinstance(draft, MetadataInputsDraft):
        if isinstance(draft.payload, PNGMetadataDraft):
            media_type = "png"
        elif isinstance(draft.payload, MP3MetadataDraft):
            media_type = "mp3"
        else:
            return []  # A payload without a known format cannot declare its media.
        outputs = [("result", media_type, draft.cover, None)]
    else:
        return []

    output_info = []
    for output_key, media_type, source, display_name in outputs:
        preview_path = None
        if isinstance(source, str):
            preview_path = source
        output_info.append(StepOutputInfo(
            reference=StepOutput(step.key, output_key),
            step_number=step_number,
            technique=step.technique,
            media_type=media_type,
            # A manual source is only a preview hint, not the future output file.
            preview_path=preview_path,
            display_name=display_name,
        ))
    return output_info


def build_output_catalog(steps: Iterable[PipelineStepDraft], before_step_key: str) -> list[StepOutputInfo]:
    """Read outputs preceding the consumer in the current pipeline order."""
    catalog = []
    for number, step in enumerate(steps, start=1):
        if step.key == before_step_key:
            return catalog
        # Renumbering changes display numbers, never saved output identities.
        catalog.extend(declared_step_outputs(step, number))
    raise ValueError("Step no longer exists in the pipeline.")


@dataclass(frozen=True, slots=True)
class ClearedLink:
    step_key: str
    role: str
    reference: StepOutput
    reason: str


def build_output_usage(steps: Iterable[PipelineStepDraft]) -> dict[StepOutput, list[tuple[str, str]]]:
    """Read saved owners across all roles; never reserve a user's pending selection."""
    usage = {}
    for step in steps:
        draft = step.technique_inputs
        sources = []
        if isinstance(draft, LSBInputsDraft):
            sources.append((draft.cover, "cover"))
        elif isinstance(draft, LocomotiveInputsDraft):
            for cover in draft.covers:
                sources.append((cover.source, "covers"))
            for source in draft.payload_files:
                sources.append((source, "payload_files"))
        elif isinstance(draft, MetadataInputsDraft):
            sources.append((draft.cover, "target"))
            if isinstance(draft.payload, MP3MetadataDraft):
                for picture in draft.payload.attached_pictures:
                    sources.append((picture.source, "apic"))
        for source, role in sources:
            if isinstance(source, StepOutput):
                usage.setdefault(source, []).append((step.key, role))
    return usage


def validate_output_usage(steps: Iterable[PipelineStepDraft]) -> None:
    steps = list(steps)
    usage = build_output_usage(steps)
    numbers = {step.key: number for number, step in enumerate(steps, start=1)}
    for owners in usage.values():
        if len(owners) > 1:
            first_key, first_role = owners[0]
            second_key, second_role = owners[1]
            raise ValueError(
                f"Step {numbers[second_key]} ({second_role}): output is already used by "
                f"Step {numbers[first_key]} ({first_role}). Select another output."
            )


def reconcile_links(steps: Iterable[PipelineStepDraft]) -> list[ClearedLink]:
    """Clear invalid linked inputs once, in current order; never restore old links."""
    available_outputs = {}
    cleared_links = []
    for number, step in enumerate(steps, start=1):
        draft = step.technique_inputs

        if isinstance(draft, LSBInputsDraft):
            source = draft.cover
            if isinstance(source, StepOutput):
                output = available_outputs.get(source)
                reason = None
                if output is None:
                    reason = "Source output is unavailable or no longer precedes this step."
                elif output.media_type != "png":
                    reason = "Source output format is incompatible with this input."
                if reason:
                    cleared_links.append(ClearedLink(step.key, "cover", source, reason))
                    draft.cover = None

        elif isinstance(draft, LocomotiveInputsDraft):
            # Keep the same cover objects and output keys for surviving inputs.
            remaining_covers = []
            for cover in draft.covers:
                reason = None
                if isinstance(cover.source, StepOutput):
                    output = available_outputs.get(cover.source)
                    if output is None:
                        reason = "Source output is unavailable or no longer precedes this step."
                    elif output.media_type != "png":
                        reason = "Source output format is incompatible with this input."
                if reason:
                    cleared_links.append(ClearedLink(step.key, "covers", cover.source, reason))
                else:
                    remaining_covers.append(cover)
            draft.covers[:] = remaining_covers

            # File payload accepts both PNG and MP3, even when Text mode is active.
            remaining_files = []
            for source in draft.payload_files:
                if isinstance(source, StepOutput) and source not in available_outputs:
                    reason = "Source output is unavailable or no longer precedes this step."
                    cleared_links.append(ClearedLink(step.key, "payload_files", source, reason))
                else:
                    remaining_files.append(source)
            draft.payload_files[:] = remaining_files

        elif isinstance(draft, MetadataInputsDraft):
            target = draft.cover
            if isinstance(target, StepOutput):
                output = available_outputs.get(target)
                reason = None
                if output is None:
                    reason = "Source output is unavailable or no longer precedes this step."
                else:
                    accepted_media = {"png", "mp3"}
                    if isinstance(draft.payload, PNGMetadataDraft):
                        accepted_media = {"png"}
                    elif isinstance(draft.payload, MP3MetadataDraft):
                        accepted_media = {"mp3"}
                    if output.media_type not in accepted_media:
                        reason = "Source output format is incompatible with this input."
                if reason:
                    cleared_links.append(ClearedLink(step.key, "target", target, reason))
                    # All PNG/MP3 edits belong to the target that was removed.
                    draft.cover = None
                    draft.payload = None

            if isinstance(draft.payload, MP3MetadataDraft):
                remaining_pictures = []
                for picture in draft.payload.attached_pictures:
                    reason = None
                    if isinstance(picture.source, StepOutput):
                        output = available_outputs.get(picture.source)
                        if output is None:
                            reason = "Source output is unavailable or no longer precedes this step."
                        elif output.media_type != "png":
                            reason = "Attached pictures require a PNG output."
                    if reason:
                        cleared_links.append(ClearedLink(step.key, "apic", picture.source, reason))
                    else:
                        remaining_pictures.append(picture)
                draft.payload.attached_pictures[:] = remaining_pictures

        # Register after cleanup so lost covers also invalidate downstream links.
        if isinstance(draft, LocomotiveInputsDraft):
            has_cover = bool(draft.covers)
        elif isinstance(draft, (LSBInputsDraft, MetadataInputsDraft)):
            has_cover = bool(draft.cover)
        else:
            has_cover = False
        if has_cover:
            for output in declared_step_outputs(step, number):
                available_outputs[output.reference] = output

    return cleared_links


def evaluate_pipeline_statuses(steps: Iterable[PipelineStepDraft]) -> dict[str, tuple[str, str]]:
    """Read current status without changing drafts during a UI render."""
    steps = list(steps)
    usage = build_output_usage(steps)
    available_outputs = {}
    statuses = {}
    for number, step in enumerate(steps, start=1):
        draft = step.technique_inputs
        error = None
        sources = []  # Each entry contains an input and its accepted media types.

        # Check required fields and collect only inputs used by the active mode.
        if draft is None:
            error = "Configure this step."
        elif isinstance(draft, LSBInputsDraft):
            if not draft.cover:
                error = "Select a cover image."
            elif not draft.payload_text.strip():
                error = "Enter a payload message."
            sources.append((draft.cover, {"png"}))
        elif isinstance(draft, LocomotiveInputsDraft):
            if not draft.covers:
                error = "Select at least one PNG cover."
            elif draft.payload_mode == "files":
                if not draft.payload_files:
                    error = "Select at least one payload file."
            elif draft.payload_mode == "text":
                if not draft.payload_text.strip():
                    error = "Enter a payload message."
            else:
                error = "Select a valid payload mode."
            for cover in draft.covers:
                sources.append((cover.source, {"png"}))
            if draft.payload_mode == "files":
                for source in draft.payload_files:
                    sources.append((source, None))
        elif isinstance(draft, MetadataInputsDraft):
            accepted_media = {"png", "mp3"}
            if not draft.cover or draft.payload is None:
                error = "Select a metadata target and configure its form."
            elif isinstance(draft.payload, PNGMetadataDraft):
                accepted_media = {"png"}
            elif isinstance(draft.payload, MP3MetadataDraft):
                accepted_media = {"mp3"}
            else:
                error = "Select a valid metadata format."
            if error is None and isinstance(draft.cover, str):
                extension = Path(draft.cover).suffix.lower()[1:]
                if extension not in accepted_media:
                    error = "Metadata payload does not match the target format."
            sources.append((draft.cover, accepted_media))
            if isinstance(draft.payload, MP3MetadataDraft):
                try:
                    validate_attached_pictures(draft.payload.attached_pictures, allow_linked=True)
                except ValueError as picture_error:
                    error = str(picture_error)
                for picture in draft.payload.attached_pictures:
                    if picture.source is not None:
                        sources.append((picture.source, {"png"}))
        else:
            error = "Unsupported step inputs."

        # A missing manual file changes status, but never clears the saved path.
        if error is None:
            for source, accepted_media in sources:
                if not isinstance(source, (str, StepOutput)) or not source:
                    error = "Select an input source."
                    break
                if isinstance(source, str) and not Path(source).is_file():
                    error = "A manual input file is unavailable; select it again."
                    break

        if error is None and isinstance(draft, (LSBInputsDraft, LocomotiveInputsDraft)):
            if draft.encryption_enabled:
                if draft.encryption_mode == "password":
                    if not draft.password:
                        error = "Enter an encryption password."
                elif draft.encryption_mode == "public_key":
                    if not draft.public_key_path or not Path(draft.public_key_path).is_file():
                        error = "Select an available public key."
                else:
                    error = "Select a valid encryption mode."

        state = "ready"
        detail = "Inputs are configured; the pipeline has not run yet."
        if error:
            state = "setup"
            detail = error
        else:
            for source, accepted_media in sources:
                if not isinstance(source, StepOutput):
                    continue
                output = available_outputs.get(source)
                if output is None:
                    state = "setup"
                    detail = "Source output is unavailable or no longer precedes this step."
                    break
                if accepted_media is not None and output.media_type not in accepted_media:
                    state = "setup"
                    detail = "Source output format is incompatible with this input."
                    break
                if statuses[source.step_key][0] != "ready":
                    state = "blocked"
                    detail = "A preceding source step is not ready."
                    break
        if error is None:
            for owners in usage.values():
                own_count = sum(owner_key == step.key for owner_key, role in owners)
                if own_count and (own_count > 1 or owners[0][0] != step.key):
                    state = "blocked"
                    detail = "An output is already used by another input. Select another output."
                    break
        statuses[step.key] = (state, detail)

        # Keep valid references to unready producers; consumers become BLOCKED.
        if isinstance(draft, LocomotiveInputsDraft):
            has_cover = bool(draft.covers)
        elif isinstance(draft, (LSBInputsDraft, MetadataInputsDraft)):
            has_cover = bool(draft.cover)
        else:
            has_cover = False
        if has_cover:
            for output in declared_step_outputs(step, number):
                available_outputs[output.reference] = output

    return statuses
