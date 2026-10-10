"""Read/write embed pipeline YAML. Plain drafts only; no GUI or file writing here."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import yaml
from mutagen import MutagenError
from PIL import Image

from src.core.configurable.drafts import (
    TECHNIQUE_LABELS, LinkedPicture, LSBInputsDraft, LocomotiveInputsDraft,
    MetadataInputsDraft, StepDraft,
)
from src.core.configurable.link import root_cover
from src.core.configurable.step_output import StepOutput
from src.core.stego.metadata_handlers.mp3_handler import (
    APIC_TYPES, DESC_FRAMES, LANG_FRAMES, MP3Field, MetadataMP3Handler, apic_description,
)
from src.core.stego.metadata_handlers.png_handler import MetadataPNGHandler

CONFIG_VERSION = 1


class ConfigError(ValueError):
    """A config error with its step/field location, safe to show to the user."""


@dataclass
class ImportedPipeline:
    name: str
    steps: list[StepDraft]


# --- Shared checks ---
def require_type(value, expected, location):
    # bool is an int in Python, but not a YAML version or picture type.
    if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
        raise ConfigError(f"{location}: expected {expected.__name__}.")
    return value


def read_text(value, location, *, nullable=False):
    if value is None and nullable:
        return None
    return require_type(value, str, location)


def read_document(text: str) -> dict:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        location = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise ConfigError(f"Invalid YAML{location}.") from error
    require_type(data, dict, "pipeline")
    version = require_type(data.get("sieng2"), int, "sieng2")
    if version != CONFIG_VERSION:
        raise ConfigError(f"sieng2: unsupported config version {version}.")
    if data.get("kind") != "embed_pipeline":
        raise ConfigError("kind: expected embed_pipeline.")
    require_type(data.get("steps"), list, "steps")
    read_text(data.get("name", ""), "name")
    return data


def read_source(value, base_dir, earlier, location):
    """A manual path, an earlier output, or an empty slot."""
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        path = Path(value)
        return str((base_dir / path).resolve())
    require_type(value, dict, location)
    source_id = read_text(value.get("from"), f"{location} › from")
    output = read_text(value.get("output"), f"{location} › output")
    if source_id not in earlier:
        raise ConfigError(f"{location}: {source_id} is not an earlier step.")
    if not output.strip():
        raise ConfigError(f"{location} › output: cannot be empty.")
    # Whether the output exists is checked by link_problem, not treated as pending.
    return StepOutput(earlier[source_id], output)


def read_sources(value, base_dir, earlier, location):
    require_type(value, list, location)
    sources = []
    for index, item in enumerate(value, start=1):
        source = read_source(item, base_dir, earlier, f"{location}[{index}]")
        if source is None:
            raise ConfigError(f"{location}[{index}]: expected a path or output link.")
        sources.append(source)
    if sources and any(isinstance(source, StepOutput) != isinstance(sources[0], StepOutput) for source in sources):
        raise ConfigError(f"{location}: cannot mix paths and output links.")
    return sources


def note_missing(source, label, pending):
    if source is None:
        pending.append(f"{label} [pending]")
    elif isinstance(source, str) and not Path(source).is_file():
        pending.append(f"{label}: {Path(source).name} [pending]")


def read_encryption(data, base_dir, location, pending):
    encryption = data.get("encryption", {"mode": "password", "password": None})
    require_type(encryption, dict, f"{location} › encryption")
    mode = encryption.get("mode")
    if mode not in ("none", "password", "public_key"):
        raise ConfigError(f"{location} › encryption › mode: expected none, password or public_key.")
    password = read_text(encryption.get("password"), f"{location} › password", nullable=True)
    key = read_text(encryption.get("public_key"), f"{location} › public_key", nullable=True)
    key_path = str((base_dir / key).resolve()) if key else None
    if mode == "password" and not password:
        pending.append("Password [pending]")
    if mode == "public_key":
        note_missing(key_path, "Public key", pending)
    return dict(encryption_enabled=mode != "none", encryption_mode="password" if mode == "none" else mode,
                password=password or "", public_key_path=key_path)


# --- Metadata: YAML keeps edits, while a draft keeps the whole edited file ---
def read_metadata_edits(data, media, base_dir, earlier, location):
    edits = {"media": media, "set": {}, "remove": [], "pictures": []}
    removed = require_type(data.get("remove", []), list, f"{location} › remove")
    edits["remove"] = [read_text(key, f"{location} › remove") for key in removed]
    values = data.get("set", [] if media == "mp3" else {})
    if media == "png":
        require_type(values, dict, f"{location} › set")
        for key, text in values.items():
            try:
                MetadataPNGHandler().check_keyword(key)
            except ValueError as error:
                raise ConfigError(f"{location} › set: {error}") from error
            edits["set"][key] = read_text(text, f"{location} › set › {key}", nullable=True)
    else:
        require_type(values, list, f"{location} › set")
        edits["set"] = []
        seen = set()
        handler = MetadataMP3Handler()
        for index, item in enumerate(values, start=1):
            where = f"{location} › set[{index}]"
            require_type(item, dict, where)
            frame = read_text(item.get("frame"), f"{where} › frame")
            if frame == "APIC" or not handler.is_editable(frame):
                raise ConfigError(f"{where} › frame: unsupported text frame.")
            value = {"frame": frame, "text": read_text(item.get("text"), f"{where} › text", nullable=True)}
            if frame in DESC_FRAMES:
                value["desc"] = read_text(item.get("desc", ""), f"{where} › desc")
            if frame in LANG_FRAMES:
                value["lang"] = read_text(item.get("lang", "eng"), f"{where} › lang")
            field = MP3Field(frame, value["text"] or "", value.get("desc", ""), value.get("lang", "eng"))
            # Check desc/lang even if text is withheld; date frames need a valid year for this check.
            checked = field if field.text else MP3Field(frame, "2000" if frame in ("TDRC", "TDOR") else "pending",
                                                       field.desc, field.lang)
            try:
                handler.check_field(checked.key, checked)
            except ValueError as error:
                raise ConfigError(f"{where}: {error}") from error
            # A withheld URL has no key yet (WOAR's key contains its text).
            if field.text or frame in DESC_FRAMES or not frame.startswith("W"):
                if field.key in seen:
                    raise ConfigError(f"{where}: duplicate field.")
                seen.add(field.key)
            edits["set"].append(value)

    pictures = require_type(data.get("pictures", []), list, f"{location} › pictures")
    if media == "png" and pictures:
        raise ConfigError(f"{location} › pictures: only MP3 targets support pictures.")
    for index, picture in enumerate(pictures, start=1):
        where = f"{location} › pictures[{index}]"
        require_type(picture, dict, where)
        picture_type = require_type(picture.get("type"), int, f"{where} › type")
        if picture_type not in APIC_TYPES:
            raise ConfigError(f"{where} › type: expected a number from 0 to 20.")
        if "from" in picture:
            if "path" in picture:
                raise ConfigError(f"{where}: choose a path or output link, not both.")
            source = read_source(picture, base_dir, earlier, where)
        else:
            path = read_text(picture.get("path"), f"{where} › path", nullable=True)
            source = read_source(path, base_dir, earlier, where)
        edits["pictures"].append({"type": picture_type, "source": source})
    return edits


def build_metadata(target, edits, steps, pending, location):
    media = edits["media"]
    handler = MetadataMP3Handler() if media == "mp3" else MetadataPNGHandler()
    source = root_cover(steps, target) if isinstance(target, StepOutput) else target
    available = bool(source and Path(source).is_file())
    original = {}
    removed_frames = []
    if available:
        try:
            if media == "mp3":
                original = handler.read_frames(source)
                removed_frames = handler.read_unsupported(source)
            elif Path(source).suffix.lower() == ".png":
                original = handler.read_text(source)
            # LSB++ made from JPG/WebP starts with no PNG text metadata.
        except (OSError, ValueError, MutagenError) as error:
            raise ConfigError(f"{location} › target: cannot read metadata ({error}).") from error
    elif not isinstance(target, StepOutput):
        note_missing(target, "Target file not found", pending)

    entries = dict(original)
    for key in edits["remove"]:
        entries.pop(key, None)
    if media == "png":
        for key, text in edits["set"].items():
            if text is None:
                pending.append(f"Field {key} [pending]")
            entries[key] = text or ""
    else:
        for value in edits["set"]:
            if not value["text"]:
                pending.append(f"Field {value['frame']} [pending]")
                continue
            field = MP3Field(value["frame"], value["text"], value.get("desc", ""), value.get("lang", "eng"))
            entries[field.key] = field

    taken = {field.desc for field in entries.values() if isinstance(field, MP3Field) and field.frame_id == "APIC"}
    linked_pictures = []
    for picture in edits["pictures"]:
        picture_type, image_source = picture["type"], picture["source"]
        desc = apic_description(picture_type, taken)
        taken.add(desc)
        if isinstance(image_source, StepOutput):
            linked_pictures.append(LinkedPicture(image_source, picture_type, desc))
        elif image_source and Path(image_source).is_file():
            try:
                with Image.open(image_source) as image:
                    if image.format not in ("PNG", "JPEG"):
                        raise ValueError("expected a PNG or JPEG picture")
                    mime = Image.MIME[image.format]
                    image.verify()
                field = MP3Field("APIC", desc=desc, mime=mime, picture_type=picture_type,
                                 data=Path(image_source).read_bytes(), path=image_source)
                entries[field.key] = field
            except (OSError, ValueError, SyntaxError) as error:
                raise ConfigError(f"{location} › pictures: cannot read picture ({error}).") from error
        else:
            note_missing(image_source, f"Picture {desc}", pending)

    # Keep all edits if anything is missing, so a later form can apply them again.
    saved_edits = edits if not available or pending else {}
    payload_keys = handler.changed_keys(original, entries) + [picture.key for picture in linked_pictures]
    return MetadataInputsDraft(target, entries if available else {}, payload_keys if available else [],
                               removed_frames, linked_pictures if available else [], saved_edits)


# --- Import ---
def import_pipeline(text: str, base_dir: str | Path) -> ImportedPipeline:
    """Return new drafts. A failure never changes an existing pipeline."""
    data = read_document(text)
    base_dir = Path(base_dir).resolve()
    steps, earlier = [], {}
    for number, item in enumerate(data["steps"], start=1):
        location = f"steps[{number}]"
        require_type(item, dict, location)
        step_id = read_text(item.get("id"), f"{location} › id")
        if not step_id.strip() or step_id in earlier:
            raise ConfigError(f"{location} › id: must be nonempty and unique.")
        location = step_id
        technique = read_text(item.get("technique"), f"{location} › technique")
        if technique not in TECHNIQUE_LABELS:
            raise ConfigError(f"{location} › technique: unsupported technique.")
        step = StepDraft(uuid4().hex, technique,
                         read_text(item.get("description", TECHNIQUE_LABELS[technique]), f"{location} › description"),
                         read_text(item.get("guidenote", ""), f"{location} › guidenote"))
        input_fields = {"lsbpp": ("cover", "payload_text", "encryption"),
                        "locomotive": ("covers", "payload_mode", "payload_files", "payload_text", "encryption"),
                        "metadata": ("target", "set", "remove", "pictures")}[technique]
        if any(key in item for key in input_fields):
            if technique == "metadata":
                target = read_source(item.get("target"), base_dir, earlier, f"{location} › target")
                media = "mp3" if isinstance(target, str) and Path(target).suffix.lower() == ".mp3" else "png"
                if target is None and (isinstance(item.get("set"), list) or item.get("pictures")):
                    media = "mp3"
                if isinstance(target, str) and Path(target).suffix.lower() not in (".png", ".mp3"):
                    raise ConfigError(f"{location} › target: expected PNG or MP3.")
                edits = read_metadata_edits(item, media, base_dir, earlier, location)
                step.technique_inputs = build_metadata(target, edits, steps, step.pending, location)
            else:
                encryption = read_encryption(item, base_dir, location, step.pending)
                payload = read_text(item.get("payload_text"), f"{location} › payload_text", nullable=True)
                if technique == "lsbpp":
                    cover = read_source(item.get("cover"), base_dir, earlier, f"{location} › cover")
                    note_missing(cover, "Cover", step.pending)
                    if not payload or not payload.strip():
                        step.pending.append("Payload text [pending]")
                    step.technique_inputs = LSBInputsDraft(cover, payload or "", **encryption)
                else:
                    mode = item.get("payload_mode", "files")
                    if mode not in ("text", "files"):
                        raise ConfigError(f"{location} › payload_mode: expected text or files.")
                    covers = read_sources(item.get("covers", []), base_dir, earlier, f"{location} › covers")
                    files = read_sources(item.get("payload_files", []), base_dir, earlier, f"{location} › payload_files")
                    if not covers:
                        step.pending.append("Covers [pending]")
                    for cover in covers:
                        note_missing(cover, "Cover", step.pending)
                    if mode == "text" and (not payload or not payload.strip()):
                        step.pending.append("Payload text [pending]")
                    if mode == "files":
                        if not files:
                            step.pending.append("Payload files [pending]")
                        for file in files:
                            note_missing(file, "Payload file", step.pending)
                    step.technique_inputs = LocomotiveInputsDraft(covers, mode, files, payload or "", **encryption)
        steps.append(step)
        earlier[step_id] = step.key
    return ImportedPipeline(data.get("name", ""), steps)


# --- Export ---
def export_path(path, base_dir):
    if not path:
        return None
    path = Path(path).resolve()
    try:
        return path.relative_to(base_dir).as_posix()
    except ValueError:
        return path.as_posix()


def export_source(source, ids, base_dir):
    if isinstance(source, StepOutput):
        if source.step_key not in ids:
            raise ConfigError("Cannot export a link whose source step was removed.")
        return {"from": ids[source.step_key], "output": source.output_key}
    return export_path(source, base_dir)


def export_encryption(draft, include_passwords, base_dir):
    if not draft.encryption_enabled:
        return {"mode": "none"}
    if draft.encryption_mode == "password":
        return {"mode": "password", "password": draft.password if include_passwords else None}
    if draft.encryption_mode == "public_key":
        return {"mode": "public_key", "public_key": export_path(draft.public_key_path, base_dir)}
    raise ConfigError("encryption: unsupported mode.")


def metadata_edits(draft, steps):
    if draft.imported_edits:
        return draft.imported_edits
    source = root_cover(steps, draft.target) if isinstance(draft.target, StepOutput) else draft.target
    media = "mp3" if isinstance(draft.target, str) and Path(draft.target).suffix.lower() == ".mp3" else "png"
    handler = MetadataMP3Handler() if media == "mp3" else MetadataPNGHandler()
    if not source or not Path(source).is_file():
        raise ConfigError("Metadata target is unavailable; cannot work out its edits for export.")
    try:
        if media == "mp3":
            original = handler.read_frames(source)
        else:
            original = handler.read_text(source) if Path(source).suffix.lower() == ".png" else {}
    except (OSError, ValueError, MutagenError) as error:
        raise ConfigError(f"Cannot read Metadata target for export ({error}).") from error
    edits = {"media": media, "set": {}, "remove": [key for key in original if key not in draft.entries], "pictures": []}
    changed = handler.changed_keys(original, draft.entries)
    if media == "png":
        edits["set"] = {key: draft.entries[key] for key in changed}
    else:
        edits["set"] = []
        for key in changed:
            value = draft.entries[key]
            if value.frame_id == "APIC":
                # Replacing an existing picture must remove it before assigning its description again.
                if key in original:
                    edits["remove"].append(key)
                edits["pictures"].append({"type": value.picture_type, "source": value.path or None})
                continue
            item = {"frame": value.frame_id, "text": value.text}
            if value.frame_id in DESC_FRAMES:
                item["desc"] = value.desc
            if value.frame_id in LANG_FRAMES:
                item["lang"] = value.lang
            edits["set"].append(item)
        edits["pictures"] += [{"type": picture.picture_type, "source": picture.source} for picture in draft.linked_pictures]
    return edits


def export_metadata(draft, steps, ids, base_dir, include_secret):
    edits = metadata_edits(draft, steps)
    values = edits["set"]
    if edits["media"] == "png":
        values = {key: text if include_secret else None for key, text in values.items()}
    else:
        values = [{**item, "text": item["text"] if include_secret else None} for item in values]
    data = {"target": export_source(draft.target, ids, base_dir), "set": values, "remove": list(edits["remove"])}
    if edits["media"] == "mp3":
        data["pictures"] = []
        for picture in edits["pictures"]:
            source = export_source(picture["source"], ids, base_dir)
            item = {"type": picture["type"]}
            item.update(source if isinstance(source, dict) else {"path": source})
            data["pictures"].append(item)
    return data


def export_pipeline(steps: list[StepDraft], *, name: str = "", include_secret: bool = False,
                    include_passwords: bool = False, base_dir: str | Path) -> str:
    """Build YAML from saved drafts; text/password values are withheld by default."""
    if not steps:
        raise ConfigError("Pipeline is empty. Add a step first.")
    base_dir = Path(base_dir).resolve()
    ids = {step.key: f"step{number}" for number, step in enumerate(steps, start=1)}
    data = {"sieng2": CONFIG_VERSION, "kind": "embed_pipeline"}
    if name:
        data["name"] = name
    text = (f"# SIENG2 embed pipeline · exported {datetime.now():%Y-%m-%d %H:%M}\n"
            f"# Secret text: {'included' if include_secret else 'not included'} · "
            f"Passwords: {'included' if include_passwords else 'not included'}\n"
            "# Values written as null are filled in the app after import (the step shows [pending]).\n"
            "# Relative paths are read from the folder of this file.\n")
    text += yaml.safe_dump(data, allow_unicode=True, sort_keys=False) + "steps:\n"
    for number, step in enumerate(steps, start=1):
        if step.technique not in TECHNIQUE_LABELS:
            raise ConfigError(f"Step {number}: unsupported technique.")
        item = {"id": ids[step.key], "technique": step.technique,
                "description": step.description, "guidenote": step.guidenote}
        draft = step.technique_inputs
        if isinstance(draft, MetadataInputsDraft):
            item.update(export_metadata(draft, steps, ids, base_dir, include_secret))
        elif isinstance(draft, (LSBInputsDraft, LocomotiveInputsDraft)):
            if isinstance(draft, LSBInputsDraft):
                item["cover"] = export_source(draft.cover, ids, base_dir)
            else:
                item["covers"] = [export_source(cover, ids, base_dir) for cover in draft.covers]
                item["payload_mode"] = draft.payload_mode
                item["payload_files"] = [export_source(file, ids, base_dir) for file in draft.payload_files] if draft.payload_mode == "files" else []
            item["payload_text"] = draft.payload_text if include_secret else None
            item["encryption"] = export_encryption(draft, include_passwords, base_dir)
        text += f"  # Step {number} · {TECHNIQUE_LABELS[step.technique]}\n"
        text += "\n".join("  " + line for line in yaml.safe_dump([item], allow_unicode=True, sort_keys=False).splitlines()) + "\n"
    return text


def pipeline_label(data: dict) -> str:
    """Template name without reading any target files (GUI scans the folder later)."""
    name = read_text(data.get("name", ""), "name")
    if name:
        return name
    labels = []
    for number, step in enumerate(require_type(data.get("steps"), list, "steps"), start=1):
        require_type(step, dict, f"steps[{number}]")
        technique = read_text(step.get("technique"), f"steps[{number}] › technique")
        if technique not in TECHNIQUE_LABELS:
            raise ConfigError(f"steps[{number}] › technique: unsupported technique.")
        label = TECHNIQUE_LABELS[technique]
        if technique == "metadata":
            target = step.get("target")
            if isinstance(target, dict):
                label += "-PNG"
            elif isinstance(target, str) and Path(target).suffix.lower() in (".png", ".mp3"):
                label += "-" + Path(target).suffix[1:].upper()
        labels.append(f"Step {number} {label}")
    return ", ".join(labels)
