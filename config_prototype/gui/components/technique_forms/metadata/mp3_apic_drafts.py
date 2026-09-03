from dataclasses import dataclass

from src.core.stego.metadata_handlers.mp3_handler import APIC_TYPES


APIC_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})


@dataclass
class ApicImageDraft:
    """One local image that will become an MP3 attached-picture frame."""

    image_path: str
    picture_type: int = 3
    description: str = ""


def apic_draft_structure_error(drafts: object) -> str | None:
    """Return a structural error without requiring referenced files to exist."""
    if not isinstance(drafts, list):
        return "APIC image drafts must be a list."

    for draft in drafts:
        if not isinstance(draft, ApicImageDraft):
            return "APIC image drafts contain an unsupported item."
        if not isinstance(draft.image_path, str):
            return "APIC image paths must be text."
        if not isinstance(draft.picture_type, int) or isinstance(
            draft.picture_type,
            bool,
        ):
            return "APIC picture types must be integer IDs."
        if draft.picture_type not in APIC_TYPES:
            return f"Unsupported APIC picture type: {draft.picture_type}."
        if not isinstance(draft.description, str):
            return "APIC descriptions must be text."

    return None


__all__ = [
    "APIC_IMAGE_EXTENSIONS",
    "ApicImageDraft",
    "apic_draft_structure_error",
]
