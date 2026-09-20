"""Immutable input snapshots for one configurable pipeline run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

from .step_output import FileSource


@dataclass(frozen=True, slots=True)
class EncryptionRequest:
    """Encryption values used by one technique during a run."""

    mode: str | None = None
    password: str = field(default="", repr=False)
    public_key_path: str | None = None


@dataclass(frozen=True, slots=True)
class LSBRunInputs:
    """Snapshot of the effective inputs for one LSB++ step."""

    cover: FileSource | None = None
    payload_text: str = ""
    encryption: EncryptionRequest = field(default_factory=EncryptionRequest)


@dataclass(frozen=True, slots=True)
class LocomotiveRunCover:
    """One Locomotive cover paired with its stable output identity."""

    source: FileSource
    output_key: str


@dataclass(frozen=True, slots=True)
class LocomotiveRunInputs:
    """Snapshot of the effective inputs for one Locomotive step."""

    covers: tuple[LocomotiveRunCover, ...] = ()
    payload_mode: str = "files"
    payload_files: tuple[FileSource, ...] = ()
    payload_text: str = ""
    encryption: EncryptionRequest = field(default_factory=EncryptionRequest)


@dataclass(frozen=True, slots=True)
class PNGMetadataRunPayload:
    """Ordered PNG text entries for a Metadata step."""

    entries: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class MP3SimpleFrameRequest:
    """One scalar MP3 text or URL frame."""

    frame_id: str
    value: str = ""


@dataclass(frozen=True, slots=True)
class MP3ComplexFrameInstanceRequest:
    """One structured value belonging to a complex MP3 frame."""

    lang: str | None = None
    desc: str | None = None
    text: str | None = None
    url: str | None = None


@dataclass(frozen=True, slots=True)
class MP3ComplexFrameRequest:
    """One complex MP3 frame and its ordered instances."""

    frame_id: str
    instances: tuple[MP3ComplexFrameInstanceRequest, ...] = ()


MP3FrameRequest: TypeAlias = (
    MP3SimpleFrameRequest | MP3ComplexFrameRequest
)


@dataclass(frozen=True, slots=True)
class ApicImageRequest:
    """One image source that will become an MP3 APIC frame."""

    image: FileSource
    picture_type: int = 3
    description: str = ""


@dataclass(frozen=True, slots=True)
class MP3MetadataRunPayload:
    """Ordered MP3 text frames and APIC images for a Metadata step."""

    frames: tuple[MP3FrameRequest, ...] = ()
    apic_images: tuple[ApicImageRequest, ...] = ()


MetadataRunPayload: TypeAlias = (
    PNGMetadataRunPayload | MP3MetadataRunPayload
)


@dataclass(frozen=True, slots=True)
class MetadataRunInputs:
    """Snapshot of one PNG or MP3 Metadata step."""

    cover: FileSource | None = None
    media_type: str | None = None
    payload: MetadataRunPayload | None = None


TechniqueRunInputs: TypeAlias = (
    LSBRunInputs | LocomotiveRunInputs | MetadataRunInputs
)


@dataclass(frozen=True, slots=True)
class RunStepRequest:
    """One saved editor step prepared for compiler validation."""

    step_key: str
    technique: str
    description: str
    guidenote: str
    inputs: TechniqueRunInputs | None = None


@dataclass(frozen=True, slots=True)
class PipelineRunRequest:
    """Ordered, immutable snapshot of the saved pipeline editor state."""

    steps: tuple[RunStepRequest, ...] = ()
