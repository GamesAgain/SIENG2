"""Lossless ID3 input snapshots and text-frame validation."""

from copy import deepcopy
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TextFrame, UrlFrame
from PIL import Image

from src.core.configurable.step_output import StepOutput
from src.core.stego.metadata_handlers.mp3_handler import APIC_TYPES, FRAME_INFO, STANDARD_FRAMES, get_frame_class


COMPLEX_FIELDS = {
    "COMM": ("lang", "desc", "text"),
    "USLT": ("lang", "desc", "text"),
    "USER": ("lang", "text"),
    "TXXX": ("desc", "text"),
    "WXXX": ("desc", "url"),
}
IDENTITY_FIELDS = {"COMM": ("lang", "desc"), "USLT": ("lang", "desc"),
                   "USER": ("lang",), "TXXX": ("desc",), "WXXX": ("desc",)}


def is_simple_frame(frame_id: str) -> bool:
    frame_class = get_frame_class(frame_id)
    return (frame_id in FRAME_INFO and frame_id not in COMPLEX_FIELDS
            and isinstance(frame_class, type) and issubclass(frame_class, (TextFrame, UrlFrame)))


@dataclass
class MP3SimpleFrameDraft:
    frame_id: str
    values: list[str] = field(default_factory=list)


@dataclass
class MP3FrameInstanceDraft:
    lang: str | None = None
    desc: str | None = None
    text: str | list[str] | None = None
    url: str | None = None


@dataclass
class MP3ComplexFrameDraft:
    frame_id: str
    instances: list[MP3FrameInstanceDraft] = field(default_factory=list)


@dataclass
class MP3TextFramesDraft:
    frames: list[MP3SimpleFrameDraft | MP3ComplexFrameDraft] = field(default_factory=list)


@dataclass
class MP3AttachedPictureDraft:
    picture_type: int = 3
    description: str = ""
    mime: str = "image/png"
    data: bytes = field(default=b"", repr=False)
    source_name: str | None = None
    # Preserve undecodable/externally linked pictures loaded from ID3 unchanged.
    original_data: bytes | None = field(default=None, repr=False, compare=False)
    original_mime: str | None = field(default=None, repr=False, compare=False)
    # Manual pictures keep their bytes; linked pictures wait for a pipeline output.
    source: StepOutput | None = None


def read_attached_picture(file_path: str) -> MP3AttachedPictureDraft:
    path = Path(file_path)
    data = path.read_bytes()
    with Image.open(BytesIO(data)) as image:
        if image.format not in {"PNG", "JPEG"}:
            raise ValueError("Select a PNG or JPEG image.")
        mime = Image.MIME[image.format]
        image.verify()
    return MP3AttachedPictureDraft(mime=mime, data=data, source_name=path.name)


def validate_attached_pictures(pictures: list[MP3AttachedPictureDraft], *, allow_linked: bool = False) -> None:
    descriptions = set()
    icon_types = set()
    for picture in pictures:
        unchanged_image = (picture.original_data is not None and picture.data == picture.original_data
                           and picture.mime == picture.original_mime)
        if picture.picture_type not in APIC_TYPES and not (unchanged_image and 0 <= picture.picture_type <= 255):
            raise ValueError("Select a valid picture type.")
        if "\x00" in picture.description:
            raise ValueError("Picture descriptions cannot contain null characters.")
        if picture.description in descriptions:
            raise ValueError(f"Picture description '{picture.description}' is used more than once.")
        descriptions.add(picture.description)
        if picture.picture_type in {1, 2}:
            if picture.picture_type in icon_types:
                raise ValueError(f"Only one picture of type {picture.picture_type} is allowed.")
            icon_types.add(picture.picture_type)
        if picture.source is not None:
            if not allow_linked or not isinstance(picture.source, StepOutput):
                raise ValueError("Resolve the linked picture output before saving an MP3 file.")
            # Dimensions (including type 1's 32×32 rule) need the actual output at run time.
            continue
        if unchanged_image and picture.picture_type != 1:
            continue
        try:
            with Image.open(BytesIO(picture.data)) as image:
                if not unchanged_image and (image.format not in {"PNG", "JPEG"} or Image.MIME[image.format] != picture.mime):
                    raise ValueError("New pictures must contain valid PNG or JPEG data with matching MIME.")
                if picture.picture_type == 1 and (image.format != "PNG" or image.size != (32, 32)):
                    raise ValueError("Picture type 1 requires a 32×32 PNG image.")
                image.verify()
        except OSError as error:
            raise ValueError("Cannot read the attached picture. Select a valid PNG or JPEG image.") from error


@dataclass
class MP3MetadataDraft:
    text_frames: MP3TextFramesDraft = field(default_factory=MP3TextFramesDraft)
    preserved_frames: list[Any] = field(default_factory=list, repr=False)
    preserved_unknown_frames: list[bytes] = field(default_factory=list, repr=False)
    id3_version: tuple[int, int, int] | None = None
    attached_pictures: list[MP3AttachedPictureDraft] = field(default_factory=list)


def read_mp3_draft(file_path: str) -> MP3MetadataDraft:
    try:
        tags = ID3(file_path)
    except ID3NoHeaderError:
        return MP3MetadataDraft()
    draft = MP3MetadataDraft(id3_version=tags.version,
                             preserved_unknown_frames=deepcopy(tags.unknown_frames))
    complex_frames = {}
    for frame in tags.values():
        frame_id = frame.FrameID
        if isinstance(frame, APIC):
            draft.attached_pictures.append(MP3AttachedPictureDraft(
                picture_type=int(frame.type), description=frame.desc, mime=frame.mime,
                data=frame.data, original_data=frame.data, original_mime=frame.mime,
            ))
        elif frame_id in COMPLEX_FIELDS:
            values = {name: deepcopy(getattr(frame, name)) for name in COMPLEX_FIELDS[frame_id]}
            if isinstance(values.get("text"), list):
                values["text"] = [str(value) for value in values["text"]]
            instance = MP3FrameInstanceDraft(**values)
            if frame_id not in complex_frames:
                complex_frames[frame_id] = MP3ComplexFrameDraft(frame_id)
                draft.text_frames.frames.append(complex_frames[frame_id])
            complex_frames[frame_id].instances.append(instance)
        elif is_simple_frame(frame_id):
            values = ([str(value) for value in frame.text] if isinstance(frame, TextFrame)
                      else [frame.url])
            draft.text_frames.frames.append(MP3SimpleFrameDraft(frame_id, values))
        else:
            draft.preserved_frames.append(deepcopy(frame))
    return draft


def validate_text_frames(draft: MP3TextFramesDraft) -> None:
    seen = set()
    for frame in draft.frames:
        frame_id = frame.frame_id
        if frame_id in seen:
            raise ValueError(f"Frame '{frame_id}' appears more than once. Use its instances instead.")
        seen.add(frame_id)
        if isinstance(frame, MP3SimpleFrameDraft):
            if not is_simple_frame(frame_id):
                raise ValueError(f"Unsupported simple frame: {frame_id}")
            if not frame.values or not any(value.strip() for value in frame.values):
                raise ValueError(f"Enter a value for '{frame_id}'.")
            if frame_id.startswith("W"):
                try:
                    for value in frame.values:
                        value.encode("latin-1")
                except UnicodeEncodeError:
                    raise ValueError(f"'{frame_id}' URLs must use Latin-1; encode international URLs first.") from None
        elif isinstance(frame, MP3ComplexFrameDraft):
            if frame_id not in COMPLEX_FIELDS or not frame.instances:
                raise ValueError(f"Enter an instance for '{frame_id}'.")
            identities = set()
            for instance in frame.instances:
                if "lang" in COMPLEX_FIELDS[frame_id]:
                    lang = instance.lang or ""
                    if len(lang) != 3 or not lang.isascii() or not lang.isalpha():
                        raise ValueError(f"'{frame_id}' language must be a three-letter code.")
                value = instance.url if frame_id == "WXXX" else instance.text
                values = value if isinstance(value, list) else [value or ""]
                if not any(item.strip() for item in values):
                    raise ValueError(f"Enter {'a URL' if frame_id == 'WXXX' else 'text'} for '{frame_id}'.")
                if frame_id == "WXXX":
                    try:
                        (instance.url or "").encode("latin-1")
                    except UnicodeEncodeError:
                        raise ValueError("WXXX URLs must use Latin-1; encode international URLs first.") from None
                identity = tuple(getattr(instance, name) or "" for name in IDENTITY_FIELDS[frame_id])
                if identity in identities:
                    raise ValueError(f"'{frame_id}' has duplicate instance identity: {identity}.")
                identities.add(identity)
        else:
            raise ValueError(f"Unsupported frame draft: {frame_id}")
