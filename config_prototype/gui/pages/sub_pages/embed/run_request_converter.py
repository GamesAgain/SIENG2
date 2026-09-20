"""Convert saved GUI Draft values into immutable core run requests."""

from __future__ import annotations

from typing import TypeAlias

from config_prototype.core.configurable import (
    ApicImageRequest,
    EncryptionRequest,
    LSBRunInputs,
    LocomotiveRunCover,
    LocomotiveRunInputs,
    MP3ComplexFrameInstanceRequest,
    MP3ComplexFrameRequest,
    MP3FrameRequest,
    MP3MetadataRunPayload,
    MP3SimpleFrameRequest,
    MetadataRunInputs,
    PNGMetadataRunPayload,
    RunStepRequest,
)
from config_prototype.gui.components.technique_forms import (
    LSBInputsDraft,
    LocomotiveInputsDraft,
    MP3ComplexFrameDraft,
    MP3ComplexFrameInstanceDraft,
    MP3MetadataDraft,
    MP3SimpleFrameDraft,
    MetadataInputsDraft,
    PNGMetadataDraft,
)


TechniqueInputsDraft: TypeAlias = (
    LSBInputsDraft | LocomotiveInputsDraft | MetadataInputsDraft
)
SUPPORTED_TECHNIQUES = frozenset({"lsbpp", "locomotive", "metadata"})


def _build_encryption_request(
    enabled: bool,
    mode: str,
    password: str,
    public_key_path: str | None,
) -> EncryptionRequest:
    """Snapshot only the encryption values active in the saved Draft."""

    if not enabled:
        return EncryptionRequest()
    if mode == "password":
        return EncryptionRequest(mode=mode, password=password)
    if mode == "public_key":
        return EncryptionRequest(
            mode=mode,
            public_key_path=public_key_path,
        )
    return EncryptionRequest(mode=mode)


def _build_lsb_run_inputs(draft: LSBInputsDraft) -> LSBRunInputs:
    return LSBRunInputs(
        cover=draft.cover,
        payload_text=draft.payload_text,
        encryption=_build_encryption_request(
            draft.encryption_enabled,
            draft.encryption_mode,
            draft.password,
            draft.public_key_path,
        ),
    )


def _build_locomotive_run_inputs(
    draft: LocomotiveInputsDraft,
) -> LocomotiveRunInputs:
    return LocomotiveRunInputs(
        covers=tuple(
            LocomotiveRunCover(
                source=cover.source,
                output_key=cover.output_key,
            )
            for cover in draft.covers
        ),
        payload_mode=draft.payload_mode,
        payload_files=tuple(draft.payload_files),
        payload_text=draft.payload_text,
        encryption=_build_encryption_request(
            draft.encryption_enabled,
            draft.encryption_mode,
            draft.password,
            draft.public_key_path,
        ),
    )


def _build_mp3_frame_instance_request(
    draft: MP3ComplexFrameInstanceDraft,
) -> MP3ComplexFrameInstanceRequest:
    return MP3ComplexFrameInstanceRequest(
        lang=draft.lang,
        desc=draft.desc,
        text=draft.text,
        url=draft.url,
    )


def _build_mp3_frame_request(
    draft: MP3SimpleFrameDraft | MP3ComplexFrameDraft,
) -> MP3FrameRequest:
    if isinstance(draft, MP3SimpleFrameDraft):
        return MP3SimpleFrameRequest(
            frame_id=draft.frame_id,
            value=draft.value,
        )
    if isinstance(draft, MP3ComplexFrameDraft):
        return MP3ComplexFrameRequest(
            frame_id=draft.frame_id,
            instances=tuple(
                _build_mp3_frame_instance_request(instance)
                for instance in draft.instances
            ),
        )
    raise TypeError(
        "Unsupported MP3 frame Draft type: "
        f"{type(draft).__name__}."
    )


def _build_metadata_run_inputs(
    draft: MetadataInputsDraft,
) -> MetadataRunInputs:
    payload = draft.payload
    if payload is None:
        return MetadataRunInputs(cover=draft.cover)

    if isinstance(payload, PNGMetadataDraft):
        return MetadataRunInputs(
            cover=draft.cover,
            media_type="png",
            payload=PNGMetadataRunPayload(
                entries=tuple(payload.entries.items()),
            ),
        )

    if isinstance(payload, MP3MetadataDraft):
        return MetadataRunInputs(
            cover=draft.cover,
            media_type="mp3",
            payload=MP3MetadataRunPayload(
                frames=tuple(
                    _build_mp3_frame_request(frame)
                    for frame in payload.frames
                ),
                apic_images=tuple(
                    ApicImageRequest(
                        image=image.image,
                        picture_type=image.picture_type,
                        description=image.description,
                    )
                    for image in payload.apic_images
                ),
            ),
        )

    raise TypeError(
        "Unsupported Metadata payload Draft type: "
        f"{type(payload).__name__}."
    )


def build_run_step_request(
    *,
    step_key: str,
    technique: str,
    description: str,
    guidenote: str,
    draft: TechniqueInputsDraft | None,
) -> RunStepRequest:
    """Convert one saved technique Draft without reading a widget."""

    if technique not in SUPPORTED_TECHNIQUES:
        raise ValueError(
            f"Unsupported technique for step '{step_key}': {technique}."
        )

    if draft is None:
        inputs = None
    elif technique == "lsbpp" and isinstance(draft, LSBInputsDraft):
        inputs = _build_lsb_run_inputs(draft)
    elif technique == "locomotive" and isinstance(
        draft,
        LocomotiveInputsDraft,
    ):
        inputs = _build_locomotive_run_inputs(draft)
    elif technique == "metadata" and isinstance(draft, MetadataInputsDraft):
        inputs = _build_metadata_run_inputs(draft)
    else:
        raise TypeError(
            f"Step '{step_key}' uses technique '{technique}' with "
            f"incompatible Draft type '{type(draft).__name__}'."
        )

    return RunStepRequest(
        step_key=step_key,
        technique=technique,
        description=description,
        guidenote=guidenote,
        inputs=inputs,
    )
