"""Declare step outputs from saved drafts without modifying pipeline state."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from src.core.configurable.step_output import StepOutput, StepOutputInfo
from src.gui.features.embed.forms.lsb_form import LSBInputsDraft
from src.gui.features.embed.forms.locomotive_form import LocomotiveInputsDraft
from src.gui.features.embed.forms.metadata_form import MetadataInputsDraft
from src.gui.features.embed.forms.metadata.mp3_draft import MP3MetadataDraft
from src.gui.features.embed.forms.metadata.png_form import PNGMetadataDraft

if TYPE_CHECKING:
    from src.gui.features.embed.configurable.configurable_page import PipelineStepDraft


def declared_step_outputs(step: PipelineStepDraft, step_number: int) -> list[StepOutputInfo]:
    """Describe expected outputs; producer readiness is checked separately."""
    draft = step.technique_inputs
    if step.technique == "lsbpp" and isinstance(draft, LSBInputsDraft):
        outputs = [("result", "png", draft.cover, None)]
    elif step.technique == "locomotive" and isinstance(draft, LocomotiveInputsDraft):
        outputs = [
            (cover.output_key, "png", cover.source, f"Output {number}")
            for number, cover in enumerate(draft.covers, start=1)
        ]
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

    return [
        StepOutputInfo(
            reference=StepOutput(step.key, output_key),
            step_number=step_number,
            technique=step.technique,
            media_type=media_type,
            # A manual source is only a preview hint, not the future output file.
            preview_path=source if isinstance(source, str) else None,
            display_name=display_name,
        )
        for output_key, media_type, source, display_name in outputs
    ]


def build_output_catalog(steps: Iterable[PipelineStepDraft], before_step_key: str) -> list[StepOutputInfo]:
    """Read outputs preceding the consumer in the current pipeline order."""
    catalog = []
    for number, step in enumerate(steps, start=1):
        if step.key == before_step_key:
            return catalog
        # Renumbering changes display numbers, never saved output identities.
        catalog.extend(declared_step_outputs(step, number))
    raise ValueError("Step no longer exists in the pipeline.")
