"""Run the saved pipeline steps in order and keep every output as a file in a temporary workspace."""
import shutil
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from src.core.configurable.drafts import (
    TECHNIQUE_LABELS, LSBInputsDraft, LocomotiveInputsDraft, MetadataInputsDraft, StepDraft,
)
from src.core.configurable.link import Draft, covers_of, is_linked, link_problem, links_of, output_name
from src.core.configurable.step_output import StepOutput
from src.core.stego.locomotive import Locomotive
from src.core.stego.lsb_pp import LSBPP
from src.core.stego.metadata_handlers.mp3_handler import MetadataMP3Handler, MP3Field
from src.core.stego.metadata_handlers.png_handler import MetadataPNGHandler

SAVE_FOLDER_PREFIX  = "SIENG2_Result"

@dataclass
class StepOutputFile:
    step_number: int
    technique: str
    path: Path  # <workspace>/<cover name>.png or .mp3  (A_2.png, A_3.png ... when the name is taken)
    reference: StepOutput  # how a later step picks this file as its Previous Output
    final: bool  # no later step uses it: it is the end of its chain and the one that is saved

# --- Checks ---
def missing_files(draft: Draft) -> list[str]:
    """Saved manual files that are gone from disk (only the ones the active mode uses)."""
    paths = [cover for cover in covers_of(draft) if not is_linked(cover)]  # a link has no file before the run
    if isinstance(draft, LocomotiveInputsDraft) and draft.payload_mode == "files":
        paths += [file for file in draft.payload_files if not is_linked(file)]
    if not isinstance(draft, MetadataInputsDraft) and draft.encryption_enabled and draft.encryption_mode == "public_key":
        paths.append(draft.public_key_path)
    return [path for path in paths if path and not Path(path).is_file()]

def step_status(step: StepDraft, steps: list[StepDraft] | None = None) -> tuple[str, str]:
    """
    Can this step run? Returns ("ready" | "setup" | "blocked", reason). steps = the whole pipeline (needed to check Previous Outputs).
    setup = this step still needs something from the user; blocked = what it uses from another step is gone or not allowed.
    The only place with these rules: the card badge shows the reason as a tooltip, check_steps raises it.
    """
    if step.technique_inputs is None:
        return "setup", "Open this step and save its inputs."

    problem = link_problem(steps, step) if steps is not None else None
    if problem:
        return "blocked", problem

    if step.pending:
        return "setup", step.pending[0]

    # A saved file may have been moved or deleted since Save
    missing = missing_files(step.technique_inputs)
    if missing:
        names = "\n".join(Path(path).name for path in missing)
        return "setup", f"A manual input file is unavailable; select it again:\n{names}"

    return "ready", "Inputs are saved; the pipeline has not run yet."

def check_steps(steps: list[StepDraft]) -> None:
    """Raise ValueError (naming the step) when the pipeline cannot run."""
    if not steps:
        raise ValueError("Pipeline is empty. Add a step first.")

    for number, step in enumerate(steps, start=1):
        state, reason = step_status(step, steps)
        if state != "ready":
            raise ValueError(f"Step {number}: {reason}")

# --- Run ---
def unique_name(name: str, used: set[str]) -> str:
    """Keep the name; add _2, _3 ... only when it is already taken (case-insensitive, like Windows)."""
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate, count = name, 1
    while candidate.casefold() in used:
        count += 1
        candidate = f"{stem}_{count}{suffix}"
    used.add(candidate.casefold())
    return candidate

def embed_step(draft: LSBInputsDraft | LocomotiveInputsDraft, progress_callback=None) -> list[bytes]:
    """Call the core for one step; return the png bytes of its outputs, in cover order (the core's file names are not used)."""
    password, public_key_path = draft.encryption_args()

    if isinstance(draft, LSBInputsDraft):
        _, data = LSBPP().embed(
            draft.cover, draft.payload_text,
            public_key_path=public_key_path, password=password, progress_callback=progress_callback,
        )
        return [data]

    if isinstance(draft, LocomotiveInputsDraft):
        results = Locomotive().embed(
            draft.covers,
            file_paths=draft.payload_files if draft.payload_mode == "files" else None,
            raw_text=draft.payload_text if draft.payload_mode == "text" else None,
            public_key_path=public_key_path, password=password, progress_callback=progress_callback,
        )
        # The core returns one output per cover, in cover order (one cover -> one output)
        return [data for _, data in results]

    raise ValueError("Unsupported step inputs.")

def write_metadata(draft: MetadataInputsDraft, destination: Path) -> None:
    """Save the Metadata step's values into a copy of its target (the hidden-field list is made here, from the real file)."""
    if Path(draft.target).suffix.lower() == ".mp3":
        # frame ที่ v2.3 เก็บไม่ได้: ผู้ใช้เห็นรายชื่อตอน Save step แล้ว (Save = ยอมให้ลบ)
        MetadataMP3Handler().write_frames(draft.target, str(destination), draft.entries,
                                          drop_unsupported=bool(draft.removed_frames))
    else:
        MetadataPNGHandler().write_text(draft.target, str(destination), draft.entries)

def entries_with_pictures(draft: MetadataInputsDraft, file_of) -> dict:
    """The step's entries + its linked pictures as real APIC fields (the exact bytes of the PNG the earlier step made)."""
    entries = dict(draft.entries)
    # เป้าหมายที่เป็น Previous Output เป็น PNG เสมอ -> MP3 ได้เฉพาะไฟล์ Manual .mp3
    is_mp3 = not is_linked(draft.target) and Path(draft.target).suffix.lower() == ".mp3"
    if draft.linked_pictures and not is_mp3:
        raise ValueError("Attached pictures can only be added to an MP3 target.")
    for picture in draft.linked_pictures:
        if picture.key in entries:
            raise ValueError(f"Two pictures use the description '{picture.desc}'. Edit one of them.")
        data = Path(file_of(picture.source)).read_bytes()
        entries[picture.key] = MP3Field("APIC", mime="image/png", picture_type=picture.picture_type, desc=picture.desc, data=data)
    return entries

def resolve_links(draft: Draft, produced: dict[StepOutput, Path], payload_folder: Path):
    """Copy of the draft where every Previous Output is replaced by the file that step made in the workspace.
    A payload file is copied into payload_folder under its own name (a.png / a.mp3), so the receiver gets that name back."""
    def file_of(cover):
        if not is_linked(cover):
            return cover
        if cover not in produced:  # its step was removed, or it does not run before this step
            raise ValueError(f"Previous Output '{cover.output_key}' is not available. Select the cover again.")
        return str(produced[cover])

    def payload_of(file):
        if not is_linked(file):
            return file
        source = Path(file_of(file))
        payload_folder.mkdir(exist_ok=True)
        target = payload_folder / (file.output_key + source.suffix)
        shutil.copyfile(source, target)
        return str(target)

    if isinstance(draft, LSBInputsDraft):
        return replace(draft, cover=file_of(draft.cover))
    if isinstance(draft, MetadataInputsDraft):
        return replace(draft, target=file_of(draft.target), entries=entries_with_pictures(draft, file_of), linked_pictures=[])
    payload_files = [payload_of(file) for file in draft.payload_files] if draft.payload_mode == "files" else draft.payload_files
    return replace(draft, covers=[file_of(cover) for cover in draft.covers], payload_files=payload_files)

def run_pipeline(steps: list[StepDraft], workspace: Path, progress_callback=None) -> list[StepOutputFile]:
    """Run the steps in card order and write every output into workspace. Stop at the first error."""
    check_steps(steps)
    outputs = []
    used_names = set()
    used = {link for step in steps for link in links_of(step.technique_inputs)}
    produced: dict[StepOutput, Path] = {}  # output of a step -> its file in the workspace (what a Previous Output points to)
    total = len(steps)

    for index, step in enumerate(steps):
        number = index + 1
        label = f"Step {number}/{total} ({TECHNIQUE_LABELS[step.technique]})"

        # 1. Progress of this step -> overall progress ("Step 2/3 (Locomotive): Encrypting payload...")
        def report(percent, message):
            if progress_callback is not None:
                overall = min(99, int((index + percent / 100) * 100 / total))
                progress_callback(overall, f"{label}: {message}")

        # 2. Previous Output covers become the files the earlier steps made (an error names the step)
        # 3. Write the outputs right away (bytes are not kept in memory), one flat folder, names never repeat
        # Output i was made from cover i: it is named after that cover (a Previous Output keeps its name: a -> a_2 -> a_3)
        files = []  # (cover, file in the workspace)
        try:
            draft = resolve_links(step.technique_inputs, produced, workspace / f"_payload_{step.key}")
            if isinstance(draft, MetadataInputsDraft):
                report(0, "Writing metadata...")
                target = step.technique_inputs.target
                path = workspace / unique_name(output_name(target) + Path(draft.target).suffix.lower(), used_names)
                write_metadata(draft, path)
                files.append((target, path))
            else:
                for cover, data in zip(covers_of(step.technique_inputs), embed_step(draft, report)):
                    path = workspace / unique_name(output_name(cover) + ".png", used_names)
                    path.write_bytes(data)
                    files.append((cover, path))
        except Exception as error:
            raise ValueError(f"{label}: {error}") from error

        for cover, path in files:
            name = output_name(cover)
            reference = StepOutput(step.key, name)
            produced[reference] = path
            outputs.append(StepOutputFile(number, step.technique, path, reference, final=reference not in used))

    if progress_callback is not None:
        progress_callback(100, f"Pipeline complete: {len(final_outputs(outputs))} output(s).")
    return outputs

def final_outputs(outputs: list[StepOutputFile]) -> list[StepOutputFile]:
    """The outputs that are saved: the end of each chain (the earlier layers are inside those files)."""
    return [output for output in outputs if output.final]

def final_files(outputs: list[StepOutputFile]) -> list[tuple[str, Path]]:
    """(name it is saved as, file in the workspace) of every final output: what Save Outputs gives and the page lists."""
    used_names = set()
    # The key keeps the name of the first file along the chain (a -> a -> a); _2, _3 only when two chains share it
    return [
        (unique_name(output.reference.output_key + output.path.suffix, used_names), output.path)
        for output in final_outputs(outputs)
    ]

# --- Save ---
def save_outputs(outputs: list[StepOutputFile], destination: Path) -> Path:
    """Copy the final outputs to <destination>/<SAVE_FOLDER_PREFIX>_<time>/<name>.png|.mp3, named after the file the chain started from."""
    folder = destination / f"{SAVE_FOLDER_PREFIX}_{datetime.now():%Y%m%d_%H%M%S}"
    folder.mkdir(parents=True, exist_ok=True)
    for name, path in final_files(outputs):
        shutil.copyfile(path, folder / name)
    return folder
