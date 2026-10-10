"""
Extract pipeline (docs/extract_pipeline.md): made from an embed run, read by the receiver's Extract page.

- build_extract_plan: steps + run outputs -> extract_pipeline.yaml (no passwords, no secret text, no sender paths)
- read_extract_plan : YAML -> ExtractPlan (checked before the page shows it)
- ready_steps / match_files / extract_step: what the receiver can extract now, and one extraction

Where an output of step A ends up (the links decide it):
  not used by any step        -> a final file (Save Outputs)
  cover / target of step B    -> inside B's output (same file, one more layer): look where B's output ends up
  payload of Locomotive B     -> recovered by extracting B
  MP3 picture of Metadata B   -> recovered by extracting B
Only the last two make a step wait for another one; layers in one file can be extracted in any order.
"""
import hashlib
import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from src.core.configurable.drafts import TECHNIQUE_LABELS, LocomotiveInputsDraft, LSBInputsDraft, MetadataInputsDraft, StepDraft
from src.core.configurable.link import covers_of, is_linked, output_name
from src.core.configurable.runner import StepOutputFile, final_files, payload_names, run_pipeline, unique_name
from src.core.configurable.step_output import StepOutput
from src.core.stego.locomotive import ZIP_PAYLOAD_NAME, Locomotive
from src.core.stego.lsb_pp import LSBPP
from src.core.stego.metadata_handlers.mp3_handler import MetadataMP3Handler, MP3Field
from src.core.stego.metadata_handlers.png_handler import MetadataPNGHandler

PLAN_VERSION = 1
PLAN_FILE_NAME = "extract_pipeline.yaml"
PICTURE_SUFFIX = {"image/png": ".png", "image/jpeg": ".jpg"}


# --- Plan data (what the receiver's page works with) ---
@dataclass(frozen=True)
class Need:
    file: str                     # file name
    source: str | None = None     # None = a final file the receiver uploads; else the id of the step that recovers it

    @property
    def key(self) -> tuple[str, str]:
        """Same key for a need and for the file that fills it."""
        return (self.source or "", self.file)

@dataclass
class PlanStep:
    id: str                       # step1, step2 ... = extract order (the embed numbers are never stored)
    technique: str
    description: str = ""
    guidenote: str = ""
    encryption: str = "none"      # none | password | public_key (the receiver uses the private key)
    session_id: int | None = None  # Locomotive only
    needs: list[Need] = field(default_factory=list)
    gives_text: bool = False      # LSB++ / Locomotive text
    gives_fields: bool = False    # Metadata
    gives_files: list[str] = field(default_factory=list)            # Locomotive payload file names
    gives_pictures: dict[str, str] = field(default_factory=dict)    # Metadata MP3: picture desc -> file name

@dataclass
class PlanFile:
    name: str
    sha256: str

@dataclass
class ExtractPlan:
    name: str
    files: list[PlanFile]
    steps: list[PlanStep]

@dataclass
class ExtractResult:
    text: str | None = None                                       # LSB++ / Locomotive text
    fields: dict[str, str] = field(default_factory=dict)          # Metadata: key -> value (PNG keyword / MP3 key like 'TXXX:desc')
    files: dict[str, Path] = field(default_factory=dict)          # recovered file name -> file in the workspace
    pictures: dict[str, MP3Field] = field(default_factory=dict)   # MP3 pictures: file name -> the picture (type, desc, mime)


def sha256_of(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --- Build (sender, after Run Pipeline) ---
def build_extract_plan(steps: list[StepDraft], outputs: list[StepOutputFile], name: str = "") -> str:
    """YAML text of the extract pipeline for this run (the same steps and outputs run_pipeline got and returned)."""
    produced = {output.reference: output.path for output in outputs}
    finals = [output for output in outputs if output.final]
    final_name = {output.reference: saved for output, (saved, _) in zip(finals, final_files(outputs))}
    session = {output.reference.step_key: output.session_id for output in outputs}
    index = {step.key: number for number, step in enumerate(steps)}

    # 1. Who uses each output, and how
    cover_user: dict[StepOutput, str] = {}        # output -> step that wrote into it
    recovered_by: dict[StepOutput, tuple[str, str]] = {}  # output -> (step that hides it, file name it comes back as)
    gives: dict[str, dict] = {step.key: {"files": [], "pictures": {}} for step in steps}
    for step in steps:
        draft = step.technique_inputs
        for cover in covers_of(draft):
            if is_linked(cover):
                cover_user[cover] = step.key
        if isinstance(draft, LocomotiveInputsDraft) and draft.payload_mode == "files":
            names = payload_names(draft.payload_files, lambda file: str(produced[file]))
            for file in draft.payload_files:
                file_name = names[file] if is_linked(file) else Path(file).name
                gives[step.key]["files"].append(file_name)
                if is_linked(file):
                    recovered_by[file] = (step.key, file_name)
        if isinstance(draft, MetadataInputsDraft):
            used = set()
            for picture in draft.linked_pictures:
                file_name = unique_name(picture.source.output_key + Path(produced[picture.source]).suffix, used)
                gives[step.key]["pictures"][picture.desc] = file_name
                recovered_by[picture.source] = (step.key, file_name)

    def location(reference: StepOutput) -> tuple[str | None, str]:
        """(step key that recovers it or None for a final file, file name). A cover link = the same file as the next layer."""
        while reference in cover_user:
            reference = StepOutput(cover_user[reference], reference.output_key)
        if reference in recovered_by:
            return recovered_by[reference]
        return None, final_name[reference]

    # 2. What each step needs: the file(s) that hold its own outputs
    needs = {step.key: [location(StepOutput(step.key, output_name(cover))) for cover in covers_of(step.technique_inputs)]
             for step in steps}

    # 3. Order (Kahn): a step is ready when every file it needs is there; among ready ones the last embedded goes first
    available = {(None, name) for name in final_name.values()}
    order, waiting = [], list(steps)
    while waiting:
        ready = [step for step in waiting if all(need in available for need in needs[step.key])]
        if not ready:
            raise ValueError("Cannot order the extract steps: a needed file is never recovered.")
        step = max(ready, key=lambda step: index[step.key])
        order.append(step)
        waiting.remove(step)
        available |= {(step.key, file) for file in gives[step.key]["files"]}
        available |= {(step.key, file) for file in gives[step.key]["pictures"].values()}

    # 4. Write it with new ids (step1 = extracted first); the embed numbers stay out of the file
    new_id = {step.key: f"step{number}" for number, step in enumerate(order, start=1)}
    items = []
    for step in order:
        draft = step.technique_inputs
        item = {"id": new_id[step.key], "technique": step.technique,
                "description": step.description, "guidenote": step.guidenote, "encryption": encryption_of(draft)}
        if step.technique == "locomotive":
            item["session_id"] = session[step.key]
        item["needs"] = [{"file": file} if source is None else {"from": new_id[source], "file": file}
                         for source, file in needs[step.key]]
        if isinstance(draft, MetadataInputsDraft):
            item["gives"] = {"fields": True}
            if gives[step.key]["pictures"]:
                item["gives"]["pictures"] = [{"desc": desc, "file": file} for desc, file in gives[step.key]["pictures"].items()]
        elif gives[step.key]["files"]:
            item["gives"] = {"files": gives[step.key]["files"]}
        else:
            item["gives"] = {"text": True}
        items.append(item)

    data = {"sieng2": PLAN_VERSION, "kind": "extract_pipeline"}
    if name:
        data["name"] = name
    data["files"] = [{"name": saved, "sha256": sha256_of(path)} for saved, path in final_files(outputs)]
    data["steps"] = items
    header = (f"# SIENG2 extract pipeline · made {datetime.now():%Y-%m-%d %H:%M} by Run Pipeline\n"
              "# No passwords or secret text are stored. Upload the final files, then extract the steps in order.\n")
    return header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False)

@dataclass
class PipelineRun:
    outputs: list[StepOutputFile]
    plan_path: Path  # extract_pipeline.yaml in the run's workspace (Save Outputs copies it next to the final files)

def run_with_plan(steps: list[StepDraft], workspace: Path, name: str = "", progress_callback=None) -> PipelineRun:
    """Run Pipeline + write its extract plan into the same workspace (the page runs this in a worker: hashing reads every final file)."""
    outputs = run_pipeline(steps, workspace, progress_callback)
    plan_path = Path(workspace) / PLAN_FILE_NAME  # outputs are .png / .mp3, so this name is never taken
    plan_path.write_text(build_extract_plan(steps, outputs, name), encoding="utf-8")
    return PipelineRun(outputs, plan_path)

def encryption_of(draft) -> str:
    if isinstance(draft, (LSBInputsDraft, LocomotiveInputsDraft)) and draft.encryption_enabled:
        return draft.encryption_mode
    return "none"


# --- Read (receiver) ---
def plan_error(location: str, message: str) -> ValueError:
    return ValueError(f"{location}: {message}")

def read_extract_plan(text: str) -> ExtractPlan:
    """Check the whole file first; raise ValueError with the place that is wrong."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ValueError("Not a valid YAML file.") from error
    if not isinstance(data, dict) or data.get("kind") != "extract_pipeline":
        raise ValueError("This is not an extract pipeline file (kind: extract_pipeline).")
    if data.get("sieng2") != PLAN_VERSION:
        raise ValueError(f"Unsupported extract pipeline version: {data.get('sieng2')!r}.")

    files = []
    for number, item in enumerate(data.get("files") or [], start=1):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("sha256"), str):
            raise plan_error(f"files[{number}]", "expected name and sha256.")
        files.append(PlanFile(item["name"], item["sha256"].lower()))
    final_names = {file.name for file in files}
    if not files or len(final_names) != len(files):
        raise ValueError("files: expected a list of unique final file names.")

    steps, gives = [], {}
    for number, item in enumerate(data.get("steps") or [], start=1):
        where = f"steps[{number}]"
        if not isinstance(item, dict):
            raise plan_error(where, "expected a step.")
        step_id = item.get("id")
        if not isinstance(step_id, str) or not step_id or step_id in gives:
            raise plan_error(where, "id must be text and unique.")
        technique = item.get("technique")
        if technique not in TECHNIQUE_LABELS:
            raise plan_error(step_id, "unsupported technique.")
        encryption = item.get("encryption", "none")
        if encryption not in ("none", "password", "public_key"):
            raise plan_error(step_id, "encryption must be none, password or public_key.")
        session_id = item.get("session_id")
        if session_id is not None and (not isinstance(session_id, int) or isinstance(session_id, bool)):
            raise plan_error(step_id, "session_id must be a number.")

        step = PlanStep(step_id, technique, str(item.get("description") or ""), str(item.get("guidenote") or ""),
                        encryption, session_id)
        for need in item.get("needs") or []:
            if not isinstance(need, dict) or not isinstance(need.get("file"), str):
                raise plan_error(step_id, "each need must have a file.")
            source = need.get("from")
            if source is None and need["file"] not in final_names:
                raise plan_error(step_id, f"{need['file']} is not in files.")
            if source is not None and need["file"] not in gives.get(source, set()):
                raise plan_error(step_id, f"{need['file']} is not recovered by an earlier step {source}.")
            step.needs.append(Need(need["file"], source))
        if not step.needs or (technique != "locomotive" and len(step.needs) != 1):
            raise plan_error(step_id, "wrong number of needed files.")

        given = item.get("gives") or {}
        if not isinstance(given, dict):
            raise plan_error(step_id, "gives must be a mapping.")
        step.gives_text = bool(given.get("text"))
        step.gives_fields = bool(given.get("fields"))
        step.gives_files = [Path(str(name)).name for name in given.get("files") or []]  # a name only, never a path
        for picture in given.get("pictures") or []:
            if not isinstance(picture, dict) or not isinstance(picture.get("desc"), str) or not isinstance(picture.get("file"), str):
                raise plan_error(step_id, "each picture must have desc and file.")
            step.gives_pictures[picture["desc"]] = Path(picture["file"]).name
        gives[step_id] = set(step.gives_files) | set(step.gives_pictures.values())
        steps.append(step)
    if not steps:
        raise ValueError("steps: the plan has no steps.")
    return ExtractPlan(str(data.get("name") or ""), files, steps)


# --- Receiver helpers ---
def match_files(plan: ExtractPlan, paths: list[str]) -> tuple[dict[str, str], list[str]]:
    """
    Uploaded files -> plan file names: same SHA-256 first, then the same name (with a warning).
    Returns ({plan file name: path}, warnings). A file that matches nothing is left out.
    """
    by_hash = {file.sha256: file.name for file in plan.files}
    names = {file.name.casefold(): file for file in plan.files}
    matched, warnings, left = {}, [], []
    for path in paths:
        name = by_hash.get(sha256_of(path))
        if name and name not in matched:
            matched[name] = str(path)
        else:
            left.append(path)
    for path in left:
        file = names.get(Path(path).name.casefold())
        if file and file.name not in matched:
            matched[file.name] = str(path)
            warnings.append(f"{Path(path).name} is not the file made by this pipeline (its content changed). It is used anyway.")
    return matched, warnings

def ready_steps(plan: ExtractPlan, available: set[tuple[str, str]], done: set[str]) -> list[PlanStep]:
    """Steps not done yet whose needed files are all there. available = Need.key of every file the receiver has now."""
    return [step for step in plan.steps if step.id not in done and all(need.key in available for need in step.needs)]


# --- Extract one step ---
def extract_step(step: PlanStep, paths: list[str], workspace: Path, password: str | None = None,
                 private_key_path: str | None = None, progress_callback=None) -> ExtractResult:
    """
    paths = the files of step.needs, in that order. Recovered files go to workspace/<step id>/.
    password: the step's password, or the private key's password (None if it has none).
    """
    folder = Path(workspace) / step.id
    result = ExtractResult()
    key = private_key_path if step.encryption == "public_key" else None
    password = password if step.encryption != "none" else None

    if step.technique == "lsbpp":
        result.text = LSBPP().extract(paths[0], private_key_path=key, password=password, progress_callback=progress_callback)
    elif step.technique == "locomotive":
        name, data = Locomotive().extract(paths, private_key_path=key, password=password, session_id=step.session_id,
                                          progress_callback=progress_callback)
        if not step.gives_files:
            result.text = data.decode("utf-8")
        elif len(step.gives_files) == 1:
            result.files[step.gives_files[0]] = write_file(folder, step.gives_files[0], data)
        else:
            if name != ZIP_PAYLOAD_NAME:
                raise ValueError("The payload is not the expected group of files.")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                inside = set(archive.namelist())
                for file_name in step.gives_files:  # only the names in the plan: a zip entry never picks its own path
                    if file_name not in inside:
                        raise ValueError(f"{file_name} is missing from the payload.")
                    result.files[file_name] = write_file(folder, file_name, archive.read(file_name))
    else:
        if Path(paths[0]).suffix.lower() == ".mp3":
            secret = MetadataMP3Handler().read_secret(paths[0])
            used = set(step.gives_pictures.values())
            for field_key, value in secret.items():
                if value.frame_id != "APIC":
                    result.fields[field_key] = value.text  # the page shows key_label(key)
                    continue
                file_name = step.gives_pictures.get(value.desc) or unique_name(
                    value.desc + PICTURE_SUFFIX.get(value.mime, ".png"), used)
                result.files[file_name] = write_file(folder, file_name, value.data)
                result.pictures[file_name] = value
        else:
            result.fields = MetadataPNGHandler().read_secret(paths[0])
        if not result.fields and not result.files:
            raise ValueError("No hidden fields were found in this file.")
        missing = [file for file in step.gives_pictures.values() if file not in result.files]
        if missing:
            raise ValueError(f"Attached picture not found: {', '.join(missing)}.")
    return result

def write_file(folder: Path, name: str, data: bytes) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / Path(name).name
    path.write_bytes(data)
    return path
