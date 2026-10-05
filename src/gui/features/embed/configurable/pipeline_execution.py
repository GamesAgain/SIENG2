"""Execute saved steps in order inside one FunctionWorker."""

from copy import deepcopy

from PIL import Image

from src.core.configurable.step_output import StepOutput
from src.core.stego.lsb_pp import LSBPP
from src.core.stego.locomotive import Locomotive
from src.core.stego.metadata_handlers.png_handler import MetadataPNGHandler
from src.gui.components.widgets.key_validation import inspect_public_key
from src.gui.features.embed.configurable.pipeline_run import PipelineRunContext
from src.gui.features.embed.configurable.pipeline_draft import PipelineStepDraft
from src.gui.features.embed.forms.metadata.png_form import PNGMetadataDraft
from src.gui.features.embed.forms.metadata.file_info import get_mp3_file_info
from src.gui.features.embed.forms.metadata.mp3_draft import (
    MP3ComplexFrameDraft, MP3MetadataDraft, read_attached_picture,
    read_mp3_draft, validate_attached_pictures, validate_text_frames,
)
from src.gui.services.metadata_png_execution import save_png_metadata
from src.gui.services.metadata_mp3_execution import save_mp3_metadata


def run_pipeline(run: PipelineRunContext, progress_callback=None) -> PipelineRunContext:
    if run.closed or run.started or run.outputs or run.completed:
        raise ValueError("Create a new run workspace before executing again.")
    run.started = True
    total = len(run.steps)
    last_percent = 0
    for index, step in enumerate(run.steps):
        label = f"Step {index + 1}/{total} ({step.technique})"

        def report(percent, message):
            nonlocal last_percent
            # A technique's 100 means computation finished, not registered yet.
            local = min(99, max(0, int(percent)))
            last_percent = max(last_percent, min(99, int((index + local / 100) * 100 / total)))
            if progress_callback:
                progress_callback(last_percent, f"{label}: {message}")

        report(0, "Starting…")
        try:
            execute_step(run, step, report)
        except Exception as error:
            raise ValueError(f"{label}: {error}") from error
    run.completed = True
    if progress_callback:
        progress_callback(100, f"Pipeline complete: {len(run.outputs)} outputs.")
    return run


def merge_mp3_inputs(existing: MP3MetadataDraft, added: MP3MetadataDraft) -> MP3MetadataDraft:
    """A linked target adds entries; do not silently replace earlier payloads."""
    merged = deepcopy(existing)
    by_id = {frame.frame_id: frame for frame in merged.text_frames.frames}
    for frame in added.text_frames.frames:
        previous = by_id.get(frame.frame_id)
        if previous is None:
            merged.text_frames.frames.append(deepcopy(frame))
            by_id[frame.frame_id] = merged.text_frames.frames[-1]
        elif isinstance(previous, MP3ComplexFrameDraft) and isinstance(frame, MP3ComplexFrameDraft):
            previous.instances.extend(deepcopy(frame.instances))
        else:
            raise ValueError(f"Linked target already contains {frame.frame_id}; choose a different frame.")
    merged.attached_pictures.extend(deepcopy(added.attached_pictures))
    # Validators also reject duplicate complex identities and APIC descriptions/types.
    validate_text_frames(merged.text_frames)
    validate_attached_pictures(merged.attached_pictures)
    return merged


def execute_step(run: PipelineRunContext, step: PipelineStepDraft, progress_callback=None) -> None:
    draft = deepcopy(step.technique_inputs)
    password = public_key_path = None
    if step.technique in {"lsbpp", "locomotive"} and draft.encryption_enabled:
        if draft.encryption_mode == "password":
            if not draft.password:
                raise ValueError("Enter a password.")
            password = draft.password
        elif draft.encryption_mode == "public_key":
            result = inspect_public_key(draft.public_key_path or "")
            if not result.valid:
                raise ValueError(result.message)
            public_key_path = draft.public_key_path
        else:
            raise ValueError("Unsupported encryption mode.")

    outputs = []  # Write every file first; publish only after the step succeeds.
    details = {}
    if step.technique == "lsbpp":
        cover = run.resolve_source(draft.cover)
        lineage = set(run.pixel_lineage.get(draft.cover, set()))
        if lineage:
            raise ValueError("This linked carrier already contains LSB++ data; embedding again would overwrite it.")
        name, data = LSBPP().embed(str(cover), draft.payload_text, password=password,
                                 public_key_path=public_key_path, progress_callback=progress_callback)
        path = run.new_output_path("png", name)
        path.write_bytes(data)
        outputs.append((StepOutput(step.key, "result"), path, lineage | {step.key}))

    elif step.technique == "locomotive":
        covers = [run.resolve_source(cover.source) for cover in draft.covers]
        for path in covers:
            with Image.open(path) as image:
                if image.format != "PNG":
                    raise ValueError(f"Cover is not a PNG image: {path.name}")
                image.verify()
        payload_paths = []
        if draft.payload_mode == "files":
            payload_paths = [run.resolve_source(source) for source in draft.payload_files]
            names = [path.name for path in payload_paths]
            if len(names) != len(set(names)):
                raise ValueError("Payload filenames are duplicated; rename manual files or change the selection.")
            details["payload_names"] = names
        engine = Locomotive()
        results = engine.embed([str(path) for path in covers],
                               file_paths=[str(path) for path in payload_paths] or None,
                               raw_text=draft.payload_text if draft.payload_mode == "text" else None,
                               password=password, public_key_path=public_key_path,
                               progress_callback=progress_callback)
        if len(results) != len(draft.covers):
            raise ValueError("Locomotive output count does not match the covers.")
        for cover, (name, data) in zip(draft.covers, results):
            path = run.new_output_path("png", name)
            path.write_bytes(data)
            # File payload is nested bytes, not the outer carrier's pixel lineage.
            lineage = set(run.pixel_lineage.get(cover.source, set()))
            outputs.append((StepOutput(step.key, cover.output_key), path, lineage))
        details["session_id"] = engine.last_session_id

    elif step.technique == "metadata":
        target = run.resolve_source(draft.cover)
        linked_target = isinstance(draft.cover, StepOutput)
        if isinstance(draft.payload, PNGMetadataDraft):
            with Image.open(target) as image:
                if image.format != "PNG":
                    raise ValueError("Metadata target is not a PNG image.")
                image.verify()
            entries = draft.payload.entries
            if linked_target:
                existing = MetadataPNGHandler().read_itxt_chunk(str(target))
                duplicates = existing.keys() & entries.keys()
                if duplicates:
                    raise ValueError("Linked target already contains metadata keys: " + ", ".join(sorted(duplicates)))
                entries = {**existing, **entries}
            path = run.new_output_path("png", f"{target.stem}_metadata.png")
            save_png_metadata(str(target), str(path), entries, progress_callback)
        elif isinstance(draft.payload, MP3MetadataDraft):
            get_mp3_file_info(str(target))
            payload = draft.payload
            details["apic_sources"] = []
            for picture in payload.attached_pictures:
                if picture.source is not None:
                    reference = picture.source
                    image = read_attached_picture(str(run.resolve_source(reference)))
                    picture.data, picture.mime, picture.source_name = image.data, image.mime, image.source_name
                    picture.original_data = picture.original_mime = None
                    picture.source = None  # Only the execution copy becomes resolved.
                    details["apic_sources"].append((reference, picture.picture_type, picture.description))
            validate_text_frames(payload.text_frames)
            validate_attached_pictures(payload.attached_pictures)
            if linked_target:
                payload = merge_mp3_inputs(read_mp3_draft(str(target)), payload)
            path = run.new_output_path("mp3", f"{target.stem}_metadata.mp3")
            save_mp3_metadata(str(target), str(path), payload, progress_callback)
        else:
            raise ValueError("Unsupported metadata inputs.")
        lineage = set(run.pixel_lineage.get(draft.cover, set()))
        outputs.append((StepOutput(step.key, "result"), path, lineage))
    else:
        raise ValueError("Unsupported pipeline technique.")

    for reference, path, lineage in outputs:
        run.register_output(reference, path)
        run.pixel_lineage[reference] = lineage
    details["outputs"] = {reference: path.name for reference, path, _ in outputs}
    run.step_results[step.key] = details
