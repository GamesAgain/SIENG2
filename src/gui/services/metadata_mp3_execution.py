"""Save MP3 metadata as compatible ID3v2.3 while protecting frames and audio."""

from copy import deepcopy
import hashlib
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from mutagen.id3 import APIC, Encoding, ID3, ID3NoHeaderError, ID3Tags, ID3TimeStamp, TIME

from src.core.stego.metadata_handlers.mp3_handler import get_frame_class
from src.gui.features.embed.forms.metadata.file_info import get_mp3_file_info
from src.gui.features.embed.forms.metadata.mp3_draft import (
    COMPLEX_FIELDS, MP3MetadataDraft, MP3SimpleFrameDraft, validate_text_frames, validate_attached_pictures,
)


def _audio_digest(path: str) -> str:
    """Hash the untouched payload between the leading ID3v2 and trailing ID3v1."""
    try:
        offset = ID3(path).size
    except ID3NoHeaderError:
        offset = 0
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        stream.seek(0, 2)
        end = stream.tell()
        if end >= 128:
            stream.seek(end - 128)
            if stream.read(3) == b"TAG":
                end -= 128
        stream.seek(offset)
        remaining = end - offset
        while remaining > 0:
            data = stream.read(min(1024 * 1024, remaining))
            if not data:
                raise ValueError("MP3 file changed while reading its audio data.")
            digest.update(data)
            remaining -= len(data)
    return digest.hexdigest()


def _semantic_value(value):
    if isinstance(value, ID3Tags):
        return _frame_snapshot(value)
    if isinstance(value, ID3TimeStamp):
        text = str(value)
        # A v2.3 TIME frame has minute precision; Mutagen reconstructs :00.
        return text + ":00" if value.minute is not None and value.second is None else text
    if isinstance(value, (list, tuple)):
        return tuple(_semantic_value(item) for item in value)
    return value


def _frame_snapshot(tags: ID3) -> dict:
    # v2.3 may convert UTF-8 encoding to UTF-16; compare content, not encoding.
    return {key: {name: _semantic_value(value) for name, value in vars(frame).items()
                  if name != "encoding" and not name.startswith("_")}
            for key, frame in tags.items()}


def _add_text_frames(tags: ID3, draft: MP3MetadataDraft) -> None:
    for frame in draft.text_frames.frames:
        cls = get_frame_class(frame.frame_id)
        if isinstance(frame, MP3SimpleFrameDraft):
            if frame.frame_id.startswith("W"):
                if len(frame.values) != 1:
                    raise ValueError(f"'{frame.frame_id}' must have exactly one URL.")
                tags.add(cls(url=frame.values[0]))
            else:
                tags.add(cls(encoding=Encoding.UTF16, text=list(frame.values)))
        else:
            for instance in frame.instances:
                values = {name: deepcopy(getattr(instance, name)) for name in COMPLEX_FIELDS[frame.frame_id]}
                if "desc" in values:
                    values["desc"] = values["desc"] or ""
                if frame.frame_id in {"COMM", "TXXX"}:
                    text = values["text"]
                    values["text"] = text if isinstance(text, list) else [text]
                elif frame.frame_id in {"USLT", "USER"} and not isinstance(values["text"], str):
                    raise ValueError(f"'{frame.frame_id}' requires a single text value.")
                tags.add(cls(encoding=Encoding.UTF16, **values))


def _normalize_v23_values(tags: ID3Tags, time_frames: list) -> None:
    recording_date = tags.get("TDRC")
    if recording_date is not None and len(recording_date.text) == 1:
        timestamp = recording_date.text[0]
        if timestamp.hour is not None and timestamp.minute is not None:
            time_frames.append((tags, f"{timestamp.hour:02d}{timestamp.minute:02d}"))
    for frame in tags.values():
        if hasattr(frame, "encoding"):
            frame.encoding = Encoding.UTF16
        text = getattr(frame, "text", None)
        if isinstance(text, list) and len(text) > 1 and all(isinstance(value, str) for value in text):
            frame.text = ["/".join(text)]
        if hasattr(frame, "sub_frames"):
            _normalize_v23_values(frame.sub_frames, time_frames)


def _prepare_v23(tags: ID3Tags) -> dict:
    """Normalize supported values and reject lossy v2.4-only conversions."""
    time_frames = []
    _normalize_v23_values(tags, time_frames)
    before = _frame_snapshot(tags)
    tags.update_to_v23()
    # Mutagen's converter treats zero hours/minutes as absent. Preserve valid
    # midnight and exact-hour values explicitly in the standard TIME frame.
    for container, value in time_frames:
        container.add(TIME(encoding=Encoding.UTF16, text=[value]))
    # Readers expose v2.3 dates as TDRC again. Compare this canonical form so
    # valid date mappings pass, but deleted frames or lost precision do not.
    canonical = deepcopy(tags)
    canonical.update_to_v24()
    after = _frame_snapshot(canonical)
    changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
    if changed:
        raise ValueError("Cannot preserve these frames when saving ID3v2.3: "
                         + ", ".join(changed) + ". Remove or adjust them first; no file was replaced.")
    return after


def save_mp3_metadata(source: str, destination: str, draft: MP3MetadataDraft, progress_callback=None) -> str:
    def report(percent: int, message: str) -> None:
        if progress_callback:
            progress_callback(percent, message)

    draft = deepcopy(draft)
    validate_text_frames(draft.text_frames)
    validate_attached_pictures(draft.attached_pictures)
    if draft.id3_version and draft.id3_version[:2] not in {(2, 3), (2, 4)}:
        raise ValueError("Reading currently supports ID3v2.3/v2.4; output is always ID3v2.3.")
    if draft.preserved_unknown_frames and (not draft.id3_version or draft.id3_version[:2] != (2, 3)):
        raise ValueError("Unknown ID3v2.4 frames cannot be safely converted to v2.3; no file was replaced.")
    target = Path(destination)
    report(10, "Preparing MP3 metadata…")
    with TemporaryDirectory(prefix=".sieng-metadata-", dir=target.parent) as directory:
        staged = Path(directory) / "metadata.mp3"
        shutil.copy2(source, staged)
        before_audio = _audio_digest(str(staged))
        try:
            tags = ID3(staged)
        except ID3NoHeaderError:
            tags = ID3()
        if draft.preserved_unknown_frames and tags.version != draft.id3_version:
            raise ValueError("The source ID3 version changed. Reload the file before saving unknown frames.")
        tags.clear()
        tags.unknown_frames = deepcopy(draft.preserved_unknown_frames)
        for frame in draft.preserved_frames:
            tags.add(deepcopy(frame))
        _add_text_frames(tags, draft)
        for picture in draft.attached_pictures:
            tags.add(APIC(encoding=Encoding.UTF16, type=picture.picture_type, desc=picture.description,
                          mime=picture.mime, data=picture.data))
        expected = _prepare_v23(tags)
        report(40, "Writing MP3 metadata…")
        tags.save(staged, v2_version=3, v23_sep='/')
        report(75, "Verifying frames and audio…")
        saved = ID3(staged)
        if saved.version[:2] != (2, 3) or _frame_snapshot(saved) != expected:
            raise ValueError("Saved ID3 frames do not match the draft; the destination was not replaced.")
        if sorted(saved.unknown_frames) != sorted(draft.preserved_unknown_frames):
            raise ValueError("Unknown ID3 frames changed; the destination was not replaced.")
        if _audio_digest(str(staged)) != before_audio:
            raise ValueError("MP3 audio data changed; the destination was not replaced.")
        get_mp3_file_info(str(staged))
        os.replace(staged, target)
    report(100, "MP3 metadata saved and verified.")
    return str(target)
