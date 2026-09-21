"""Technique adapters for the configurable pipeline runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping, TypeAlias

from mutagen.id3 import TextFrame, UrlFrame
from mutagen.mp3 import MP3
from PIL import Image

from src.core.stego.locomotive import Locomotive
from src.core.stego.lsb_pp import LSBPP
from src.core.stego.metadata import MetadataEmbedder
from src.core.stego.metadata_handlers.mp3_handler import (
    APIC_TYPES,
    get_frame_class,
)
from src.core.stego.png_container import parse_png

from .run_request import (
    ApicImageRequest,
    EncryptionRequest,
    LSBRunInputs,
    LocomotiveRunInputs,
    MP3ComplexFrameInstanceRequest,
    MP3ComplexFrameRequest,
    MP3MetadataRunPayload,
    MP3SimpleFrameRequest,
    MetadataRunInputs,
    PNGMetadataRunPayload,
)


ProgressCallback: TypeAlias = Callable[[int, str], None]
AdapterMetadata: TypeAlias = dict[str, object]


_MP3_COMPLEX_FIELDS: dict[
    str,
    tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
] = {
    "COMM": (("lang", "desc", "text"), ("lang", "text"), ("lang", "desc")),
    "USLT": (("lang", "desc", "text"), ("lang", "text"), ("lang", "desc")),
    "USER": (("lang", "text"), ("lang", "text"), ("lang",)),
    "TXXX": (("desc", "text"), ("text",), ("desc",)),
    "WXXX": (("desc", "url"), ("url",), ("desc",)),
}


def _update_progress(
    callback: ProgressCallback | None,
    percent: int,
    message: str,
) -> None:
    if callback is not None:
        callback(percent, message)


def _encryption_kwargs(
    encryption: EncryptionRequest,
    technique: str,
) -> dict[str, str]:
    if encryption.mode is None:
        return {}
    if encryption.mode == "password":
        if not encryption.password:
            raise ValueError(
                f"{technique} password encryption requires a password."
            )
        return {"password": encryption.password}
    if encryption.mode == "public_key":
        public_key_path = encryption.public_key_path
        if not public_key_path:
            raise ValueError(
                f"{technique} public-key encryption requires a public key file."
            )
        path = Path(public_key_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(
                f"The {technique} public key file is unavailable."
            )
        return {"public_key_path": str(path)}
    raise ValueError(f"The {technique} encryption mode is unsupported.")


def execute_lsbpp(
    inputs: LSBRunInputs,
    *,
    cover_path: Path,
    result_path: Path,
    progress_callback: ProgressCallback | None = None,
) -> AdapterMetadata:
    """Run LSB++ against a resolved cover and write one staged PNG."""

    if not isinstance(inputs, LSBRunInputs):
        raise TypeError("LSB++ adapter requires LSBRunInputs.")

    cover = Path(cover_path).resolve()
    result = Path(result_path).resolve()
    if not cover.is_file():
        raise FileNotFoundError("The resolved LSB++ cover is unavailable.")
    if cover.suffix.lower() != ".png":
        raise ValueError("LSB++ requires a PNG cover.")
    if result == cover:
        raise ValueError("LSB++ output cannot overwrite its cover.")
    if result.suffix.lower() != ".png":
        raise ValueError("LSB++ output must use a .png path.")
    if not result.parent.is_dir():
        raise FileNotFoundError("The LSB++ staging directory is unavailable.")
    if result.exists():
        raise FileExistsError("The LSB++ staging output already exists.")

    encryption_kwargs = _encryption_kwargs(inputs.encryption, "LSB++")
    png_bytes, suggested_filename = LSBPP().embed(
        cover_image_path=str(cover),
        message=inputs.payload_text,
        progress_callback=progress_callback,
        **encryption_kwargs,
    )
    if not isinstance(png_bytes, bytes):
        raise TypeError("LSB++ core must return PNG bytes.")

    parse_png(png_bytes)
    result.write_bytes(png_bytes)
    if not result.is_file():
        raise RuntimeError("LSB++ did not create its staged output.")
    parse_png(result.read_bytes())

    safe_suggested_name = Path(str(suggested_filename)).name
    return {
        "media_type": "png",
        "suggested_filename": safe_suggested_name,
        "size_bytes": result.stat().st_size,
        "encryption_mode": inputs.encryption.mode or "none",
    }


def execute_locomotive(
    inputs: LocomotiveRunInputs,
    *,
    cover_paths: tuple[Path, ...],
    payload_paths: tuple[Path, ...] = (),
    result_paths: Mapping[str, Path],
    progress_callback: ProgressCallback | None = None,
) -> AdapterMetadata:
    """Run Locomotive and write every stable output into staging."""

    if not isinstance(inputs, LocomotiveRunInputs):
        raise TypeError("Locomotive adapter requires LocomotiveRunInputs.")
    if len(cover_paths) != len(inputs.covers):
        raise ValueError(
            "Resolved Locomotive covers must match the request covers."
        )

    output_keys = tuple(cover.output_key for cover in inputs.covers)
    if len(set(output_keys)) != len(output_keys):
        raise ValueError("Locomotive output keys must be unique.")
    if set(result_paths) != set(output_keys):
        raise ValueError(
            "Locomotive staging outputs must match the stable output keys."
        )

    covers = tuple(Path(path).resolve() for path in cover_paths)
    payloads = tuple(Path(path).resolve() for path in payload_paths)
    results = {
        key: Path(result_paths[key]).resolve()
        for key in output_keys
    }
    if len(set(results.values())) != len(results):
        raise ValueError("Locomotive staging output paths must be unique.")

    for cover in covers:
        if not cover.is_file():
            raise FileNotFoundError(
                "A resolved Locomotive cover is unavailable."
            )
        if cover.suffix.lower() != ".png":
            raise ValueError("Locomotive requires PNG covers.")
        parse_png(cover.read_bytes())

    if inputs.payload_mode == "text":
        if payloads:
            raise ValueError(
                "Locomotive text mode cannot receive file payload paths."
            )
        file_paths: list[str] | None = None
        raw_text: str | None = inputs.payload_text
    elif inputs.payload_mode == "files":
        if len(payloads) != len(inputs.payload_files) or not payloads:
            raise ValueError(
                "Resolved Locomotive payload files must match the request."
            )
        for payload in payloads:
            if not payload.is_file():
                raise FileNotFoundError(
                    "A resolved Locomotive payload file is unavailable."
                )
        file_paths = [str(path) for path in payloads]
        raw_text = None
    else:
        raise ValueError("The Locomotive payload mode is unsupported.")

    encryption_kwargs = _encryption_kwargs(
        inputs.encryption,
        "Locomotive",
    )
    input_paths = set(covers) | set(payloads)
    public_key_path = encryption_kwargs.get("public_key_path")
    if public_key_path is not None:
        input_paths.add(Path(public_key_path).resolve())

    for result in results.values():
        if result in input_paths:
            raise ValueError("Locomotive output cannot overwrite an input.")
        if result.suffix.lower() != ".png":
            raise ValueError("Locomotive outputs must use .png paths.")
        if not result.parent.is_dir():
            raise FileNotFoundError(
                "A Locomotive staging directory is unavailable."
            )
        if result.exists():
            raise FileExistsError(
                "A Locomotive staging output already exists."
            )

    locomotive = Locomotive()
    core_outputs = locomotive.embed(
        cover_image_paths=[str(path) for path in covers],
        file_paths=file_paths,
        raw_text=raw_text,
        progress_callback=progress_callback,
        **encryption_kwargs,
    )
    if len(core_outputs) != len(covers):
        raise ValueError(
            "Locomotive output count does not match the cover count."
        )
    session_id = locomotive.last_session_id
    if not isinstance(session_id, int):
        raise RuntimeError("Locomotive did not report a session ID.")

    prepared: list[tuple[str, Path, str, bytes]] = []
    for output_key, core_output in zip(output_keys, core_outputs):
        if not isinstance(core_output, tuple) or len(core_output) != 2:
            raise TypeError(
                "Locomotive core outputs must be filename/bytes pairs."
            )
        suggested_filename, png_bytes = core_output
        if not isinstance(png_bytes, bytes):
            raise TypeError("Locomotive core must return PNG bytes.")
        parse_png(png_bytes)
        prepared.append(
            (
                output_key,
                results[output_key],
                Path(str(suggested_filename)).name,
                png_bytes,
            )
        )

    attempted: list[Path] = []
    try:
        for _key, result, _suggested, png_bytes in prepared:
            attempted.append(result)
            result.write_bytes(png_bytes)
            if not result.is_file():
                raise RuntimeError(
                    "Locomotive did not create a staged output."
                )
            parse_png(result.read_bytes())
    except Exception:
        for result in attempted:
            try:
                result.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    return {
        "media_type": "png",
        "output_count": len(prepared),
        "session_id": session_id,
        "encryption_mode": inputs.encryption.mode or "none",
        "outputs": tuple(
            {
                "output_key": output_key,
                "suggested_filename": suggested_filename,
                "size_bytes": result.stat().st_size,
            }
            for output_key, result, suggested_filename, _data in prepared
        ),
    }


def execute_metadata_png(
    inputs: MetadataRunInputs,
    *,
    cover_path: Path,
    result_path: Path,
    progress_callback: ProgressCallback | None = None,
) -> AdapterMetadata:
    """Write normalized PNG metadata into a new staged PNG."""

    if not isinstance(inputs, MetadataRunInputs):
        raise TypeError("Metadata-PNG adapter requires MetadataRunInputs.")
    if inputs.media_type != "png":
        raise ValueError("Metadata-PNG adapter requires PNG media.")
    if not isinstance(inputs.payload, PNGMetadataRunPayload):
        raise TypeError(
            "Metadata-PNG adapter requires PNGMetadataRunPayload."
        )

    entries: list[tuple[str, str]] = []
    keywords: set[str] = set()
    for entry in inputs.payload.entries:
        if (
            not isinstance(entry, tuple)
            or len(entry) != 2
            or not all(isinstance(value, str) for value in entry)
        ):
            raise TypeError(
                "PNG metadata entries must be keyword/value text pairs."
            )
        keyword, value = entry
        if not keyword or not value:
            raise ValueError("PNG metadata entries cannot be empty.")
        if keyword in keywords:
            raise ValueError("PNG metadata keywords must be unique.")
        keywords.add(keyword)
        entries.append((keyword, value))
    if not entries:
        raise ValueError("Metadata-PNG requires at least one entry.")

    cover = Path(cover_path).resolve()
    result = Path(result_path).resolve()
    if not cover.is_file():
        raise FileNotFoundError(
            "The resolved Metadata-PNG cover is unavailable."
        )
    if cover.suffix.lower() != ".png":
        raise ValueError("Metadata-PNG requires a PNG cover.")
    parse_png(cover.read_bytes())
    if result == cover:
        raise ValueError("Metadata-PNG output cannot overwrite its cover.")
    if result.suffix.lower() != ".png":
        raise ValueError("Metadata-PNG output must use a .png path.")
    if not result.parent.is_dir():
        raise FileNotFoundError(
            "The Metadata-PNG staging directory is unavailable."
        )
    if result.exists():
        raise FileExistsError(
            "The Metadata-PNG staging output already exists."
        )

    _update_progress(progress_callback, 10, "Preparing PNG metadata...")
    saved_path = MetadataEmbedder().embed(
        file_path=str(cover),
        data=dict(entries),
        save_path=str(result),
    )
    if Path(saved_path).resolve() != result:
        raise RuntimeError(
            "Metadata-PNG core returned an unexpected output path."
        )
    if not result.is_file():
        raise RuntimeError("Metadata-PNG did not create its staged output.")
    parse_png(result.read_bytes())
    _update_progress(progress_callback, 100, "PNG metadata written.")

    return {
        "media_type": "png",
        "output_key": "result",
        "entry_count": len(entries),
        "keywords": tuple(keyword for keyword, _value in entries),
        "size_bytes": result.stat().st_size,
    }


def _is_simple_mp3_frame(frame_id: str) -> bool:
    if frame_id in _MP3_COMPLEX_FIELDS or len(frame_id) != 4:
        return False
    frame_class = get_frame_class(frame_id)
    return (
        isinstance(frame_class, type)
        and issubclass(frame_class, (TextFrame, UrlFrame))
    )


def _normalize_complex_mp3_frame(
    frame: MP3ComplexFrameRequest,
) -> list[dict[str, str]]:
    try:
        fields, required_fields, identity_fields = _MP3_COMPLEX_FIELDS[
            frame.frame_id
        ]
    except KeyError as error:
        raise ValueError(
            f"Unsupported complex MP3 frame: {frame.frame_id}."
        ) from error
    if not frame.instances:
        raise ValueError(
            f"Complex MP3 frame {frame.frame_id} requires an instance."
        )

    normalized: list[dict[str, str]] = []
    identities: set[tuple[str, ...]] = set()
    for instance in frame.instances:
        if not isinstance(instance, MP3ComplexFrameInstanceRequest):
            raise TypeError("Complex MP3 frame instances are invalid.")
        values: dict[str, str] = {}
        for field_name in fields:
            value = getattr(instance, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError("Complex MP3 frame values must be text.")
            values[field_name] = value or ""
        if any(not values[name].strip() for name in required_fields):
            raise ValueError(
                f"Complex MP3 frame {frame.frame_id} is incomplete."
            )
        identity = tuple(values[name] for name in identity_fields)
        if identity in identities:
            raise ValueError(
                f"Complex MP3 frame {frame.frame_id} has a duplicate identity."
            )
        identities.add(identity)
        normalized.append(values)
    return normalized


def _normalize_mp3_frames(
    payload: MP3MetadataRunPayload,
) -> dict[str, object]:
    data: dict[str, object] = {}
    for frame in payload.frames:
        if isinstance(frame, MP3SimpleFrameRequest):
            if not _is_simple_mp3_frame(frame.frame_id):
                raise ValueError(
                    f"Unsupported simple MP3 frame: {frame.frame_id}."
                )
            if not isinstance(frame.value, str) or not frame.value.strip():
                raise ValueError(
                    f"MP3 frame {frame.frame_id} requires a value."
                )
            value: object = frame.value
        elif isinstance(frame, MP3ComplexFrameRequest):
            value = _normalize_complex_mp3_frame(frame)
        else:
            raise TypeError("The MP3 frame request is unsupported.")

        if frame.frame_id in data:
            raise ValueError(
                f"MP3 frame {frame.frame_id} is declared more than once."
            )
        data[frame.frame_id] = value
    return data


def _validated_apic_item(
    request: ApicImageRequest,
    image_path: Path,
) -> dict[str, object]:
    if not isinstance(request, ApicImageRequest):
        raise TypeError("The APIC image request is unsupported.")
    if not isinstance(image_path, Path):
        raise TypeError("APIC images must be resolved to concrete Paths.")

    path = image_path.resolve()
    if not path.is_file():
        raise FileNotFoundError("A resolved APIC image is unavailable.")
    if path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        raise ValueError("APIC images must use JPEG or PNG format.")
    try:
        with Image.open(path) as image:
            image_format = image.format
            image_size = image.size
            image.verify()
    except (OSError, ValueError) as error:
        raise ValueError("The resolved APIC source is not a valid image.") from error
    expected_format = "PNG" if path.suffix.lower() == ".png" else "JPEG"
    if image_format != expected_format:
        raise ValueError("The APIC image content does not match its extension.")

    picture_type = request.picture_type
    if (
        not isinstance(picture_type, int)
        or isinstance(picture_type, bool)
        or picture_type not in APIC_TYPES
    ):
        raise ValueError("APIC picture type must be an integer from 0 to 20.")
    if picture_type == 1 and (
        image_format != "PNG" or image_size != (32, 32)
    ):
        raise ValueError("APIC type 1 must be a 32 x 32 PNG image.")

    description = request.description
    if not isinstance(description, str):
        raise TypeError("APIC descriptions must be text.")
    description = description.strip()
    if len(description) > 64:
        raise ValueError("APIC descriptions cannot exceed 64 characters.")
    return {
        "path": str(path),
        "type": picture_type,
        "desc": description,
    }


def execute_metadata_mp3(
    inputs: MetadataRunInputs,
    *,
    cover_path: Path,
    apic_paths: tuple[Path, ...] = (),
    result_path: Path,
    progress_callback: ProgressCallback | None = None,
) -> AdapterMetadata:
    """Write normalized MP3 frames and resolved APIC images to staging."""

    if not isinstance(inputs, MetadataRunInputs):
        raise TypeError("Metadata-MP3 adapter requires MetadataRunInputs.")
    if inputs.media_type != "mp3":
        raise ValueError("Metadata-MP3 adapter requires MP3 media.")
    if not isinstance(inputs.payload, MP3MetadataRunPayload):
        raise TypeError(
            "Metadata-MP3 adapter requires MP3MetadataRunPayload."
        )

    cover = Path(cover_path).resolve()
    result = Path(result_path).resolve()
    if not cover.is_file():
        raise FileNotFoundError(
            "The resolved Metadata-MP3 cover is unavailable."
        )
    if cover.suffix.lower() != ".mp3":
        raise ValueError("Metadata-MP3 requires an MP3 cover.")
    try:
        MP3(cover)
    except Exception as error:
        raise ValueError("The resolved Metadata-MP3 cover is invalid.") from error
    if result == cover:
        raise ValueError("Metadata-MP3 output cannot overwrite its cover.")
    if result.suffix.lower() != ".mp3":
        raise ValueError("Metadata-MP3 output must use a .mp3 path.")
    if not result.parent.is_dir():
        raise FileNotFoundError(
            "The Metadata-MP3 staging directory is unavailable."
        )
    if result.exists():
        raise FileExistsError(
            "The Metadata-MP3 staging output already exists."
        )

    payload = inputs.payload
    if len(apic_paths) != len(payload.apic_images):
        raise ValueError(
            "Resolved APIC paths must match the APIC image requests."
        )
    data = _normalize_mp3_frames(payload)
    apic_items = tuple(
        _validated_apic_item(request, path)
        for request, path in zip(payload.apic_images, apic_paths)
    )
    picture_types = [item["type"] for item in apic_items]
    if len(set(picture_types)) != len(picture_types):
        raise ValueError("Each APIC picture type can be used only once.")
    descriptions = [str(item["desc"]).casefold() for item in apic_items]
    if len(set(descriptions)) != len(descriptions):
        raise ValueError(
            "APIC descriptions must be unique, ignoring letter case."
        )
    if apic_items:
        data["APIC"] = list(apic_items)
    if not data:
        raise ValueError(
            "Metadata-MP3 requires at least one frame or APIC image."
        )

    _update_progress(progress_callback, 10, "Preparing MP3 metadata...")
    saved_path = MetadataEmbedder().embed(
        file_path=str(cover),
        data=data,
        save_path=str(result),
    )
    if Path(saved_path).resolve() != result:
        raise RuntimeError(
            "Metadata-MP3 core returned an unexpected output path."
        )
    if not result.is_file():
        raise RuntimeError("Metadata-MP3 did not create its staged output.")
    try:
        MP3(result)
    except Exception as error:
        result.unlink(missing_ok=True)
        raise RuntimeError(
            "Metadata-MP3 core did not create a valid MP3 output."
        ) from error
    _update_progress(progress_callback, 100, "MP3 metadata written.")

    return {
        "media_type": "mp3",
        "output_key": "result",
        "frame_ids": tuple(
            frame_id for frame_id in data if frame_id != "APIC"
        ),
        "frame_count": len(payload.frames),
        "apic_count": len(apic_items),
        "size_bytes": result.stat().st_size,
    }
