"""Draft models for the prototype Metadata technique form."""

from config_prototype.gui.components.technique_forms.metadata.metadata_embed_inputs import (
    ApicImageDraft,
    MetadataEmbedInputs,
    MetadataInputsDraft,
    MetadataPayloadDraft,
    MP3MetadataDraft,
    PNGMetadataDraft,
)
from config_prototype.gui.components.technique_forms.metadata.png_metadata_fields import (
    PNGCustomRow,
    PNGStandardField,
)
from config_prototype.gui.components.technique_forms.metadata.png_metadata_form import (
    PNGMetadataForm,
)

__all__ = [
    "ApicImageDraft",
    "MetadataEmbedInputs",
    "MetadataInputsDraft",
    "MetadataPayloadDraft",
    "MP3MetadataDraft",
    "PNGCustomRow",
    "PNGMetadataDraft",
    "PNGMetadataForm",
    "PNGStandardField",
]
