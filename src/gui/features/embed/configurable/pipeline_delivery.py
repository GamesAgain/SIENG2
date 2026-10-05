"""Package a completed run and the information needed to recover every step."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
from uuid import uuid4

from src.core.configurable.step_output import StepOutput
from src.gui.features.embed.configurable.pipeline_run import PipelineRunContext, file_fingerprint
from src.gui.features.embed.forms.lsb_form import LSBInputsDraft
from src.gui.features.embed.forms.locomotive_form import LocomotiveInputsDraft
from src.gui.features.embed.forms.metadata_form import MetadataInputsDraft
from src.gui.features.embed.forms.metadata.png_form import PNGMetadataDraft
from src.gui.features.embed.forms.metadata.mp3_draft import MP3ComplexFrameDraft, MP3MetadataDraft, IDENTITY_FIELDS


def collect_deliverables(run: PipelineRunContext) -> list[StepOutput]:
    if run.closed or not run.completed:
        raise ValueError("Save Outputs requires a completed run with an open workspace.")
    if set(run.outputs) != set(run.expected_outputs):
        raise ValueError("The run does not contain all declared outputs.")
    consumed = set()
    for step in run.steps:
        draft = step.technique_inputs
        if isinstance(draft, LSBInputsDraft):
            sources = [draft.cover]
        elif isinstance(draft, LocomotiveInputsDraft):
            sources = [cover.source for cover in draft.covers]
            # Dormant File Input reserves the picker, but was not used by this run.
            if draft.payload_mode == "files":
                sources.extend(draft.payload_files)
        elif isinstance(draft, MetadataInputsDraft):
            sources = [draft.cover]
            if isinstance(draft.payload, MP3MetadataDraft):
                sources.extend(picture.source for picture in draft.payload.attached_pictures)
        else:
            raise ValueError("Unsupported saved inputs.")
        for source in sources:
            if isinstance(source, StepOutput):
                if source not in run.outputs or source in consumed:
                    raise ValueError("A linked output is missing or consumed more than once.")
                consumed.add(source)
    for reference, path in run.outputs.items():
        if not path.resolve().is_relative_to(run.root) or not path.is_file():
            raise ValueError("A run output is missing or outside its workspace.")
        if file_fingerprint(path) != run.output_fingerprints.get(reference):
            raise ValueError(f"Run output changed after execution: {path.name}")
    return [reference for reference in run.expected_outputs if reference not in consumed]


def build_extract_config(run: PipelineRunContext, filenames: dict[StepOutput, str]) -> dict:
    deliverables = collect_deliverables(run)
    if set(filenames) != set(deliverables):
        raise ValueError("Package files do not match the run's leaf outputs.")

    def resource(reference):
        if not all(re.fullmatch(r"[A-Za-z0-9_-]+", value) for value in (reference.step_key, reference.output_key)):
            raise ValueError("Output identity contains unsupported characters.")
        return f"file:{reference.step_key}#{reference.output_key}"

    # Cover/Target stacking retains a payload in a later carrier. File/APIC links
    # instead recover the original file, so they are deliberately not aliases.
    carrier_links = {}
    for step in run.steps:
        draft = step.technique_inputs
        if isinstance(draft, LocomotiveInputsDraft):
            pairs = [(cover.source, StepOutput(step.key, cover.output_key)) for cover in draft.covers]
        else:
            pairs = [(draft.cover, StepOutput(step.key, "result"))]
        for source, output in pairs:
            if isinstance(source, StepOutput):
                if run.expected_outputs[source] != run.expected_outputs[output]:
                    raise ValueError("Carrier stacking changed the media type.")
                carrier_links[source] = output

    def carrier(reference):
        visited = set()
        while reference in carrier_links:
            if reference in visited:
                raise ValueError("Carrier recovery contains a cycle.")
            visited.add(reference)
            reference = carrier_links[reference]
        return resource(reference)

    nodes = []
    for number, step in enumerate(run.steps, start=1):
        draft = step.technique_inputs
        references = [reference for reference in run.expected_outputs if reference.step_key == step.key]
        details = run.step_results.get(step.key, {})
        node = {
            "step_key": step.key, "step_number": number, "technique": step.technique,
            "needs": [carrier(reference) for reference in references],
            "provides": [f"payload:{step.key}"],
        }
        if step.guidenote:
            node["guidenote"] = step.guidenote
        if isinstance(draft, (LSBInputsDraft, LocomotiveInputsDraft)):
            node["decrypt"] = {"mode": draft.encryption_mode if draft.encryption_enabled else "none"}
        if isinstance(draft, LocomotiveInputsDraft):
            session_id = details.get("session_id")
            if not isinstance(session_id, int):
                raise ValueError(f"Step {number}: Locomotive session information is unavailable.")
            node["session_id"] = session_id
            node["file_payloads"] = []
            if draft.payload_mode == "files":
                names = details.get("payload_names", [])
                if len(names) != len(draft.payload_files):
                    raise ValueError(f"Step {number}: payload filename mapping is incomplete.")
                # Count manual AND linked files: one linked + one manual is a ZIP.
                node["payload_kind"] = "zip" if len(names) > 1 else "file"
                for source, filename in zip(draft.payload_files, names):
                    if isinstance(source, StepOutput):
                        size, digest = run.output_fingerprints[source]
                        node["file_payloads"].append({"resource": resource(source), "filename": filename,
                                                      "size": size, "sha256": digest,
                                                      "media": run.expected_outputs[source]})
                        node["provides"].append(resource(source))
            else:
                node["payload_kind"] = "text"
        elif isinstance(draft, MetadataInputsDraft):
            if isinstance(draft.payload, PNGMetadataDraft):
                node["metadata"] = {"media": "png", "keys": list(draft.payload.entries)}
            else:
                frames = []
                for frame in draft.payload.text_frames.frames:
                    descriptor = {"id": frame.frame_id}
                    if isinstance(frame, MP3ComplexFrameDraft):
                        descriptor["identities"] = [
                            {name: getattr(instance, name) or "" for name in IDENTITY_FIELDS[frame.frame_id]}
                            for instance in frame.instances
                        ]
                    frames.append(descriptor)
                node["metadata"] = {"media": "mp3", "frames": frames,
                                    "pictures": [{"type": picture.picture_type, "description": picture.description}
                                                 for picture in draft.payload.attached_pictures]}
                node["apic_files"] = []
                for reference, picture_type, description in details.get("apic_sources", []):
                    size, digest = run.output_fingerprints[reference]
                    node["apic_files"].append({"resource": resource(reference),
                                               "type": picture_type, "description": description,
                                               "size": size, "sha256": digest, "media": "png"})
                    node["provides"].append(resource(reference))
                expected_apic = [picture.source for picture in draft.payload.attached_pictures if picture.source is not None]
                if [entry[0] for entry in details.get("apic_sources", [])] != expected_apic:
                    raise ValueError(f"Step {number}: APIC recovery mapping is incomplete.")
        nodes.append(node)

    resources = {}
    used_names = set()
    for reference, filename in filenames.items():
        if Path(filename).name != filename or filename in {"", ".", ".."} or filename.casefold() in used_names:
            raise ValueError("Package filenames must be unique filenames without directories.")
        if Path(filename).suffix.lower() != f".{run.expected_outputs[reference]}":
            raise ValueError("Package filename does not match the output media type.")
        used_names.add(filename.casefold())
        size, digest = run.output_fingerprints[reference]
        resources[resource(reference)] = {"filename": filename, "media": run.expected_outputs[reference],
                                          "size": size, "sha256": digest}

    # Resolve dependencies using only package files and files recovered by nodes.
    # This validates branching/join; simply reversing the step list is insufficient.
    available = set(resources)
    pending = list(nodes)
    ordered = []
    while pending:
        runnable = next((node for node in pending if set(node["needs"]) <= available), None)
        if runnable is None:
            raise ValueError("The selected package cannot recover every step.")
        ordered.append(runnable)
        available.update(runnable["provides"])
        pending.remove(runnable)
    return {"format": "sieng2.configurable.extract", "version": 2,
            "resources": resources, "steps": ordered}


def save_outputs(run: PipelineRunContext, destination: str | Path, progress_callback=None) -> Path:
    deliverables = collect_deliverables(run)
    filenames = {}
    for number, step in enumerate(run.steps, start=1):
        references = [reference for reference in run.expected_outputs if reference.step_key == step.key]
        for index, reference in enumerate(references, start=1):
            if reference in deliverables:
                suffix = f"_output_{index}" if len(references) > 1 else ""
                filenames[reference] = f"step_{number:02d}_{step.technique}{suffix}.{run.expected_outputs[reference]}"
    config = build_extract_config(run, filenames)
    destination = Path(destination).resolve()
    if destination.is_relative_to(run.root):
        raise ValueError("Choose a destination outside the temporary run workspace.")
    if not destination.is_dir():
        raise ValueError("Choose an existing destination folder.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    package = destination / f"SIENG2_{stamp}_{uuid4().hex[:8]}"
    with TemporaryDirectory(prefix=".sieng2-package-", dir=destination) as directory:
        stage = Path(directory)
        for index, (reference, filename) in enumerate(filenames.items(), start=1):
            target = stage / filename
            shutil.copyfile(run.outputs[reference], target)
            if file_fingerprint(target) != run.output_fingerprints[reference]:
                raise ValueError(f"Copied output failed verification: {filename}")
            if progress_callback:
                progress_callback(int(index * 90 / len(filenames)), f"Preparing {filename}…")
        # JSON is also valid YAML 1.2. Use the standard library, without adding a
        # YAML dependency; version 2 uses stable output keys instead of old indices.
        manifest = stage / "extract_config.yaml"
        manifest.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        if json.loads(manifest.read_text(encoding="utf-8")) != config:
            raise ValueError("Extract config failed verification.")
        if package.exists():
            raise FileExistsError("Package destination already exists.")
        stage.rename(package)  # Publish the entire package only after verification.
    if progress_callback:
        progress_callback(100, f"Saved {len(filenames)} outputs + extract_config.yaml")
    return package
