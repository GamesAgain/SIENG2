"""Run the saved pipeline steps in order and keep every output as a file in a temporary workspace."""
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.configurable.drafts import TECHNIQUE_LABELS, LSBInputsDraft, LocomotiveInputsDraft, StepDraft
from src.core.stego.locomotive import Locomotive
from src.core.stego.lsb_pp import LSBPP

SAVE_FOLDER_PREFIX  = "SIENG2_Result"

@dataclass
class StepOutputFile:
    step_number: int
    technique: str
    path: Path  # <workspace>/<cover name>.png  (A_2.png, A_3.png ... when the name is taken)

# --- Checks ---
def missing_files(draft: LSBInputsDraft | LocomotiveInputsDraft) -> list[str]:
    """Saved manual files that are gone from disk (only the ones the active mode uses)."""
    if isinstance(draft, LSBInputsDraft):
        paths = [draft.cover]
    else:
        paths = list(draft.covers)
        if draft.payload_mode == "files":
            paths += draft.payload_files
    if draft.encryption_enabled and draft.encryption_mode == "public_key":
        paths.append(draft.public_key_path)
    return [path for path in paths if path and not Path(path).is_file()]

def step_status(step: StepDraft) -> tuple[str, str]:
    """
    Can this step run? Returns ("ready" | "setup", reason).
    The only place with these rules: the card badge shows the reason as a tooltip, check_steps raises it.
    """
    if step.technique == "metadata":
        return "setup", "Metadata steps cannot run yet."

    if step.technique_inputs is None:
        return "setup", "Open this step and save its inputs."

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
        state, reason = step_status(step)
        if state != "ready":
            raise ValueError(f"Step {number}: {reason}")

# --- Run ---
def pipeline_name(cover_path: str) -> str:
    """Output name from the cover: A.jpg -> A.png (a stego file is always PNG)."""
    return Path(cover_path).stem + ".png"

def unique_name(name: str, used: set[str]) -> str:
    """Keep the name; add _2, _3 ... only when it is already taken (case-insensitive, like Windows)."""
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate, count = name, 1
    while candidate.casefold() in used:
        count += 1
        candidate = f"{stem}_{count}{suffix}"
    used.add(candidate.casefold())
    return candidate

def embed_step(draft: LSBInputsDraft | LocomotiveInputsDraft, progress_callback=None) -> list[tuple[str, bytes]]:
    """Call the core for one step; return a list of (cover-based file name, png bytes)."""
    password, public_key_path = draft.encryption_args()

    if isinstance(draft, LSBInputsDraft):
        _, data = LSBPP().embed(
            draft.cover, draft.payload_text,
            public_key_path=public_key_path, password=password, progress_callback=progress_callback,
        )
        return [(pipeline_name(draft.cover), data)]

    if isinstance(draft, LocomotiveInputsDraft):
        results = Locomotive().embed(
            draft.covers,
            file_paths=draft.payload_files if draft.payload_mode == "files" else None,
            raw_text=draft.payload_text if draft.payload_mode == "text" else None,
            public_key_path=public_key_path, password=password, progress_callback=progress_callback,
        )
        # The core returns one output per cover, in cover order (one cover -> one output)
        return [(pipeline_name(cover), data) for cover, (_, data) in zip(draft.covers, results)]

    raise ValueError("Unsupported step inputs.")

def run_pipeline(steps: list[StepDraft], workspace: Path, progress_callback=None) -> list[StepOutputFile]:
    """Run the steps in card order and write every output into workspace. Stop at the first error."""
    check_steps(steps)
    outputs = []
    used_names = set()
    total = len(steps)

    for index, step in enumerate(steps):
        number = index + 1
        label = f"Step {number}/{total} ({TECHNIQUE_LABELS[step.technique]})"

        # 1. Progress of this step -> overall progress ("Step 2/3 (Locomotive): Encrypting payload...")
        def report(percent, message):
            if progress_callback is not None:
                overall = min(99, int((index + percent / 100) * 100 / total))
                progress_callback(overall, f"{label}: {message}")

        # 2. Embed (an error names the step)
        try:
            results = embed_step(step.technique_inputs, report)
        except Exception as error:
            raise ValueError(f"{label}: {error}") from error

        # 3. Write the outputs right away (bytes are not kept in memory), one flat folder, names never repeat
        for name, data in results:
            path = workspace / unique_name(name, used_names)
            path.write_bytes(data)
            outputs.append(StepOutputFile(number, step.technique, path))

    if progress_callback is not None:
        progress_callback(100, f"Pipeline complete: {len(outputs)} output(s).")
    return outputs

# --- Save ---
def save_outputs(outputs: list[StepOutputFile], destination: Path) -> Path:
    """Copy the outputs to <destination>/<SAVE_FOLDER_PREFIX>_<time>/<file name> (names are already unique)."""
    folder = destination / f"{SAVE_FOLDER_PREFIX}_{datetime.now():%Y%m%d_%H%M%S}"
    folder.mkdir(parents=True, exist_ok=True)
    for output in outputs:
        shutil.copyfile(output.path, folder / output.path.name)
    return folder
