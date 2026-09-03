"""Draft models for the prototype Metadata technique form."""

from config_prototype.gui.components.technique_forms.metadata.metadata_embed_inputs import (
    MetadataEmbedInputs,
    MetadataInputsDraft,
    MetadataPayloadDraft,
    MP3MetadataDraft,
    PNGMetadataDraft,
)
from config_prototype.gui.components.technique_forms.metadata.mp3_apic_drafts import (
    APIC_IMAGE_EXTENSIONS,
    ApicImageDraft,
    apic_draft_structure_error,
)
from config_prototype.gui.components.technique_forms.metadata.mp3_apic_form import (
    ApicImageCard,
    MP3ApicImagesForm,
)
from config_prototype.gui.components.technique_forms.metadata.mp3_frame_drafts import (
    MP3_COMPLEX_FRAME_CONTRACTS,
    MP3ComplexFieldName,
    MP3ComplexFrameContract,
    MP3ComplexFrameDraft,
    MP3ComplexFrameInstanceDraft,
    MP3FrameDraft,
    MP3SimpleFrameDraft,
    is_mp3_simple_frame_id,
)
from config_prototype.gui.components.technique_forms.metadata.mp3_metadata_fields import (
    ComplexFrameField,
    ComplexInstanceRow,
    TextFrameField,
)
from config_prototype.gui.components.technique_forms.metadata.mp3_metadata_form import (
    MP3MetadataForm,
)
from config_prototype.gui.components.technique_forms.metadata.mp3_text_frames_form import (
    MP3TextFramesForm,
)
from config_prototype.gui.components.technique_forms.metadata.png_metadata_fields import (
    PNGCustomRow,
    PNGStandardField,
)
from config_prototype.gui.components.technique_forms.metadata.png_metadata_form import (
    PNGMetadataForm,
)

__all__ = [
    "APIC_IMAGE_EXTENSIONS",
    "ApicImageDraft",
    "ApicImageCard",
    "ComplexFrameField",
    "ComplexInstanceRow",
    "MetadataEmbedInputs",
    "MetadataInputsDraft",
    "MetadataPayloadDraft",
    "MP3_COMPLEX_FRAME_CONTRACTS",
    "MP3ComplexFieldName",
    "MP3ComplexFrameContract",
    "MP3ComplexFrameDraft",
    "MP3ComplexFrameInstanceDraft",
    "MP3FrameDraft",
    "MP3MetadataDraft",
    "MP3MetadataForm",
    "MP3ApicImagesForm",
    "MP3SimpleFrameDraft",
    "MP3TextFramesForm",
    "PNGCustomRow",
    "PNGMetadataDraft",
    "PNGMetadataForm",
    "PNGStandardField",
    "TextFrameField",
    "apic_draft_structure_error",
    "is_mp3_simple_frame_id",
]
