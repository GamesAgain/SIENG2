"""Typed draft contracts for editable MP3 ID3 frames."""

from dataclasses import dataclass, field
from typing import Literal, TypeAlias


MP3ComplexFieldName: TypeAlias = Literal["lang", "desc", "text", "url"]


@dataclass(frozen=True)
class MP3ComplexFrameContract:
    """Fields and UI behavior required by one editable complex frame type."""

    fields: tuple[MP3ComplexFieldName, ...]
    required_fields: tuple[MP3ComplexFieldName, ...] = ()
    identity_fields: tuple[MP3ComplexFieldName, ...] = ()
    multiline: bool = False
    allows_multiple: bool = True


MP3_COMPLEX_FRAME_CONTRACTS: dict[str, MP3ComplexFrameContract] = {
    "COMM": MP3ComplexFrameContract(
        ("lang", "desc", "text"),
        required_fields=("lang", "text"),
        identity_fields=("lang", "desc"),
    ),
    "USLT": MP3ComplexFrameContract(
        ("lang", "desc", "text"),
        required_fields=("lang", "text"),
        identity_fields=("lang", "desc"),
        multiline=True,
    ),
    "USER": MP3ComplexFrameContract(
        ("lang", "text"),
        required_fields=("lang", "text"),
        identity_fields=("lang",),
    ),
    "TXXX": MP3ComplexFrameContract(
        ("desc", "text"),
        required_fields=("text",),
        identity_fields=("desc",),
    ),
    "WXXX": MP3ComplexFrameContract(
        ("desc", "url"),
        required_fields=("url",),
        identity_fields=("desc",),
    ),
}


def is_mp3_simple_frame_id(frame_id: str) -> bool:
    """Return whether an ID can use a scalar text/URL draft value."""

    return (
        len(frame_id) == 4
        and frame_id.startswith(("T", "W"))
        and frame_id not in MP3_COMPLEX_FRAME_CONTRACTS
    )


@dataclass
class MP3SimpleFrameDraft:
    """One editable ID3 text or URL frame with a scalar string value."""

    frame_id: str
    value: str = ""


@dataclass
class MP3ComplexFrameInstanceDraft:
    """One structured value belonging to a complex ID3 frame."""

    lang: str | None = None
    desc: str | None = None
    text: str | None = None
    url: str | None = None


@dataclass
class MP3ComplexFrameDraft:
    """One complex frame type and its ordered user-configured instances."""

    frame_id: str
    instances: list[MP3ComplexFrameInstanceDraft] = field(
        default_factory=list
    )


MP3FrameDraft: TypeAlias = MP3SimpleFrameDraft | MP3ComplexFrameDraft


__all__ = [
    "MP3_COMPLEX_FRAME_CONTRACTS",
    "MP3ComplexFieldName",
    "MP3ComplexFrameContract",
    "MP3ComplexFrameDraft",
    "MP3ComplexFrameInstanceDraft",
    "MP3FrameDraft",
    "MP3SimpleFrameDraft",
    "is_mp3_simple_frame_id",
]
