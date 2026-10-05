"""Saved configuration for one pipeline step, shared by the page and run code."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.gui.features.embed.forms.lsb_form import LSBInputsDraft
    from src.gui.features.embed.forms.locomotive_form import LocomotiveInputsDraft
    from src.gui.features.embed.forms.metadata_form import MetadataInputsDraft


@dataclass
class PipelineStepDraft:
    key: str
    technique: str
    description: str
    guidenote: str = ""
    technique_inputs: LSBInputsDraft | LocomotiveInputsDraft | MetadataInputsDraft | None = None
