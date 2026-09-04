"""Technique-specific input forms used by the prototype step config shell."""

from config_prototype.gui.components.technique_forms.lsb_embed_inputs import (
    LSBEmbedInputs,
    LSBInputsDraft,
)
from config_prototype.gui.components.technique_forms.loco_embed_inputs import (
    LocomotiveEmbedInputs,
    LocomotiveInputsDraft,
)
from config_prototype.gui.components.technique_forms.metadata_embed_inputs import (
    MetadataEmbedInputs,
    MetadataInputsDraft,
    MetadataPayloadDraft,
)
from config_prototype.gui.components.technique_forms.metadata.mp3_form import (
    APIC_IMAGE_EXTENSIONS,
    MP3_COMPLEX_FRAME_CONTRACTS,
    ApicImageCard,
    ApicImageDraft,
    MP3ApicImagesForm,
    MP3ComplexFieldName,
    MP3ComplexFrameContract,
    MP3ComplexFrameDraft,
    MP3ComplexFrameInstanceDraft,
    MP3FrameDraft,
    MP3MetadataDraft,
    MP3MetadataForm,
    MP3SimpleFrameDraft,
)
from config_prototype.gui.components.technique_forms.metadata.png_form import (
    PNGMetadataDraft,
)

__all__ = [
    "APIC_IMAGE_EXTENSIONS",
    "LSBEmbedInputs",
    "LSBInputsDraft",
    "LocomotiveEmbedInputs",
    "LocomotiveInputsDraft",
    "MP3_COMPLEX_FRAME_CONTRACTS",
    "ApicImageCard",
    "ApicImageDraft",
    "MetadataEmbedInputs",
    "MetadataInputsDraft",
    "MetadataPayloadDraft",
    "MP3ApicImagesForm",
    "MP3ComplexFieldName",
    "MP3ComplexFrameContract",
    "MP3ComplexFrameDraft",
    "MP3ComplexFrameInstanceDraft",
    "MP3FrameDraft",
    "MP3MetadataDraft",
    "MP3MetadataForm",
    "MP3SimpleFrameDraft",
    "PNGMetadataDraft",
]
