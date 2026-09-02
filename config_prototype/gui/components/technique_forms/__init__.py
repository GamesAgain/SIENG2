"""Technique-specific input forms used by the prototype step config shell."""

from config_prototype.gui.components.technique_forms.lsb_embed_inputs import (
    LSBEmbedInputs,
    LSBInputsDraft,
)
from config_prototype.gui.components.technique_forms.loco_embed_inputs import (
    LocomotiveEmbedInputs,
    LocomotiveInputsDraft,
)
from config_prototype.gui.components.technique_forms.metadata import (
    ApicImageDraft,
    MetadataEmbedInputs,
    MetadataInputsDraft,
    MetadataPayloadDraft,
    MP3MetadataDraft,
    PNGMetadataDraft,
)

__all__ = [
    "ApicImageDraft",
    "LSBEmbedInputs",
    "LSBInputsDraft",
    "LocomotiveEmbedInputs",
    "LocomotiveInputsDraft",
    "MetadataEmbedInputs",
    "MetadataInputsDraft",
    "MetadataPayloadDraft",
    "MP3MetadataDraft",
    "PNGMetadataDraft",
]
