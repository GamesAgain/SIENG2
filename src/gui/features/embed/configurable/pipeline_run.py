"""Input snapshots and temporary output files for one pipeline run."""

from collections.abc import Iterable
from copy import deepcopy
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from src.core.configurable.step_output import FileSource, StepOutput
from src.gui.features.embed.configurable.pipeline_draft import PipelineStepDraft
from src.gui.features.embed.configurable.pipeline_links import (
    declared_step_outputs, evaluate_pipeline_statuses, validate_output_usage,
)


def file_fingerprint(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return size, digest.hexdigest()


def prepare_run_steps(steps: Iterable[PipelineStepDraft]) -> list[PipelineStepDraft]:
    """Copy saved values in order and check readiness without clearing any links."""
    run_steps = deepcopy(list(steps))
    if not run_steps:
        raise ValueError("Pipeline is empty.")

    step_keys = set()
    output_references = set()
    for number, step in enumerate(run_steps, start=1):
        if not isinstance(step.key, str) or not step.key or step.key in step_keys:
            raise ValueError(f"Step {number}: step key is missing or duplicated.")
        step_keys.add(step.key)
        for output in declared_step_outputs(step, number):
            reference = output.reference
            if not isinstance(reference.output_key, str) or not reference.output_key:
                raise ValueError(f"Step {number}: output key is missing.")
            if reference in output_references:
                raise ValueError(f"Step {number}: output key is duplicated.")
            output_references.add(reference)

    validate_output_usage(run_steps)
    statuses = evaluate_pipeline_statuses(run_steps)
    for number, step in enumerate(run_steps, start=1):
        state, reason = statuses[step.key]
        if state != "ready":
            raise ValueError(f"Step {number}: {reason}")
        if not declared_step_outputs(step, number):
            raise ValueError(f"Step {number}: technique and saved inputs do not match.")

    return run_steps


class PipelineRunContext:
    """Own one snapshot and its output files; no widgets or worker are created."""

    def __init__(self, steps: Iterable[PipelineStepDraft]):
        self.steps = prepare_run_steps(steps)
        self.expected_outputs: dict[StepOutput, str] = {}
        for number, step in enumerate(self.steps, start=1):
            for output in declared_step_outputs(step, number):
                self.expected_outputs[output.reference] = output.media_type

        self.workspace = TemporaryDirectory(prefix="sieng2-pipeline-")
        self.root = Path(self.workspace.name).resolve()
        self.outputs: dict[StepOutput, Path] = {}
        self.output_fingerprints: dict[StepOutput, tuple[int, str]] = {}
        # Keep recovery information beside files; it is not an extract config yet.
        self.step_results: dict[str, dict] = {}
        self.pixel_lineage: dict[StepOutput, set[str]] = {}
        self.started = False
        self.completed = False
        self.closed = False

    def new_output_path(self, media: str, filename: str | None = None) -> Path:
        if self.closed:
            raise ValueError("The run workspace is closed.")
        if media not in {"png", "mp3"}:
            raise ValueError("Outputs must be PNG or MP3 files.")
        if filename:
            # Separate folders prevent collisions while retaining payload filenames.
            name = Path(filename).name
            if name in {"", ".", ".."}:
                raise ValueError("Invalid output filename.")
            folder = self.root / uuid4().hex
            folder.mkdir()
            return folder / Path(name).with_suffix(f".{media}")
        # Internal names avoid collisions and never use user-supplied filenames.
        return self.root / f"{uuid4().hex}.{media}"

    def register_output(self, reference: StepOutput, path: str | Path) -> None:
        if self.closed:
            raise ValueError("The run workspace is closed.")
        if reference not in self.expected_outputs:
            raise ValueError("Output reference was not declared in this run.")
        if reference in self.outputs:
            raise ValueError("Output reference is already registered.")

        output_path = Path(path).resolve()
        if not output_path.is_relative_to(self.root):
            raise ValueError("Output file must be inside this run workspace.")
        if not output_path.is_file():
            raise ValueError("Output file has not been written successfully.")
        if output_path.suffix.lower() != f".{self.expected_outputs[reference]}":
            raise ValueError("Output file extension does not match its declared format.")
        if output_path in self.outputs.values():
            raise ValueError("Output file is already registered to another reference.")
        # Register only after writing; consumers cannot resolve unfinished outputs.
        fingerprint = file_fingerprint(output_path)
        self.outputs[reference] = output_path
        self.output_fingerprints[reference] = fingerprint

    def resolve_source(self, source: FileSource) -> Path:
        if self.closed:
            raise ValueError("The run workspace is closed.")
        if isinstance(source, str) and source:
            path = Path(source).resolve()
        elif isinstance(source, StepOutput):
            if source not in self.outputs:
                raise ValueError("Previous output has not been generated in this run.")
            path = self.outputs[source]
            if not path.resolve().is_relative_to(self.root):
                raise ValueError("Linked output is outside this run workspace.")
        else:
            raise ValueError("Invalid input source.")

        if not path.is_file():
            raise ValueError("Input file is unavailable.")
        return path

    def cleanup(self) -> None:
        """Release only this run's temporary files; manual sources are untouched."""
        if self.closed:
            return
        self.workspace.cleanup()
        self.outputs.clear()
        self.output_fingerprints.clear()
        self.step_results.clear()
        self.pixel_lineage.clear()
        self.closed = True
