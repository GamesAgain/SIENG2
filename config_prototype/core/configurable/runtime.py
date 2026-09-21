"""Per-run workspace, source resolution, and artifact lifecycle."""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping
from uuid import uuid4

from .compiler import CompiledPipeline, CompiledStep
from .step_output import FileSource, StepOutput


WORKSPACE_MARKER = ".sieng2-configurable-run"
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_UNSAFE_COMPONENT = re.compile(r"[^A-Za-z0-9_-]+")
_MEDIA_SUFFIX = {"png": ".png", "mp3": ".mp3"}
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class MissingRuntimeOutputError(KeyError):
    """A linked output has not been committed in the current run."""

    def __init__(self, reference: StepOutput) -> None:
        self.reference = reference
        super().__init__(
            "The requested previous output is unavailable in this run."
        )


class StepCommitError(RuntimeError):
    """A complete set of staged outputs could not be committed."""


class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _safe_component(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Workspace path components must be non-empty text.")

    cleaned = _UNSAFE_COMPONENT.sub("_", value).strip(" .")
    changed = cleaned != value
    if not cleaned:
        cleaned = "item"
        changed = True
    if len(cleaned) > 64:
        cleaned = cleaned[:48]
        changed = True
    if cleaned.upper() in _WINDOWS_RESERVED_NAMES:
        cleaned = f"item_{cleaned}"
        changed = True
    if changed:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
        cleaned = f"{cleaned}_{digest}"
    return cleaned


def _ensure_descendant(path: Path, parent: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(parent.resolve())
    except ValueError as error:
        raise ValueError("Workspace path escapes the run directory.") from error
    if resolved == parent.resolve():
        raise ValueError("Workspace path cannot be the run root.")
    return resolved


@dataclass(frozen=True, slots=True)
class RunWorkspace:
    """One isolated filesystem workspace owned by a single run."""

    base_dir: Path
    root: Path
    run_id: str

    @classmethod
    def create(
        cls,
        base_dir: str | Path | None = None,
        *,
        run_id: str | None = None,
    ) -> "RunWorkspace":
        base = (
            Path(base_dir)
            if base_dir is not None
            else Path(tempfile.gettempdir())
            / "sieng2"
            / "configurable-runs"
        )
        base.mkdir(parents=True, exist_ok=True)
        base = base.resolve()

        identifier = run_id or uuid4().hex
        if not _RUN_ID_PATTERN.fullmatch(identifier):
            raise ValueError(
                "run_id may contain only letters, numbers, underscores, "
                "and hyphens."
            )

        root = (base / identifier).resolve()
        if root.parent != base:
            raise ValueError(
                "A run workspace must be a direct child of its base directory."
            )
        root.mkdir(parents=False, exist_ok=False)
        try:
            (root / WORKSPACE_MARKER).write_text(
                identifier,
                encoding="utf-8",
            )
            (root / "steps").mkdir()
        except Exception:
            shutil.rmtree(root)
            raise
        return cls(base_dir=base, root=root, run_id=identifier)

    def _verified_root(self) -> Path:
        root = self.root.resolve()
        base = self.base_dir.resolve()
        marker = root / WORKSPACE_MARKER
        try:
            marker_matches = (
                marker.is_file()
                and marker.read_text(encoding="utf-8") == self.run_id
            )
        except OSError:
            marker_matches = False
        if root.parent != base or not marker_matches:
            raise ValueError("The run workspace cannot be verified.")
        return root

    def _step_directory(self, step: CompiledStep) -> Path:
        root = self._verified_root()
        step_name = (
            f"{step.position:03d}_{_safe_component(step.request.step_key)}"
        )
        directory = _ensure_descendant(
            root / "steps" / step_name,
            root,
        )
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def _output_filename(step: CompiledStep, output_index: int) -> str:
        output = step.outputs[output_index]
        try:
            suffix = _MEDIA_SUFFIX[output.media_type]
        except KeyError as error:
            raise ValueError(
                f"Unsupported declared media type: {output.media_type}."
            ) from error
        return f"{_safe_component(output.reference.output_key)}{suffix}"

    def _paths_for(
        self,
        step: CompiledStep,
        directory: Path,
    ) -> dict[StepOutput, Path]:
        paths: dict[StepOutput, Path] = {}
        used_paths: set[Path] = set()
        for index, output in enumerate(step.outputs):
            if output.reference in paths:
                raise ValueError("A step cannot declare the same output twice.")
            path = _ensure_descendant(
                directory / self._output_filename(step, index),
                self.root,
            )
            if path in used_paths:
                raise ValueError(
                    "Sanitized output names must remain unique within a step."
                )
            paths[output.reference] = path
            used_paths.add(path)
        return paths

    def staging_paths(
        self,
        step: CompiledStep,
    ) -> dict[StepOutput, Path]:
        """Create a fresh staging area for every declared step output."""

        staging = self._step_directory(step) / ".staging"
        staging = _ensure_descendant(staging, self.root)
        staging.mkdir(exist_ok=False)
        return self._paths_for(step, staging)

    def commit_step_outputs(
        self,
        step: CompiledStep,
        staged_paths: Mapping[StepOutput, Path],
    ) -> dict[StepOutput, Path]:
        """Move a complete staged output set into final paths atomically."""

        step_directory = self._step_directory(step)
        staging = _ensure_descendant(step_directory / ".staging", self.root)
        expected_staged = self._paths_for(step, staging)
        if set(staged_paths) != set(expected_staged):
            raise StepCommitError(
                "Staged outputs do not match the step declaration."
            )

        normalized_staged: dict[StepOutput, Path] = {}
        for reference, expected_path in expected_staged.items():
            provided_path = Path(staged_paths[reference]).resolve()
            if provided_path != expected_path:
                raise StepCommitError(
                    "A staged output path is outside its assigned location."
                )
            if not provided_path.is_file():
                raise StepCommitError(
                    "Every declared output must exist before commit."
                )
            normalized_staged[reference] = provided_path

        final_paths = self._paths_for(step, step_directory)
        if any(path.exists() for path in final_paths.values()):
            raise StepCommitError("A final output path already exists.")

        moved: list[tuple[Path, Path]] = []
        try:
            for reference in expected_staged:
                source = normalized_staged[reference]
                destination = final_paths[reference]
                source.replace(destination)
                moved.append((source, destination))
        except Exception as error:
            rollback_errors: list[Exception] = []
            for source, destination in reversed(moved):
                try:
                    if destination.exists() and not source.exists():
                        destination.replace(source)
                except Exception as rollback_error:
                    rollback_errors.append(rollback_error)
            if rollback_errors:
                raise StepCommitError(
                    "Step output commit failed and rollback was incomplete."
                ) from error
            raise StepCommitError("Step output commit failed.") from error

        try:
            staging.rmdir()
        except OSError:
            pass
        return final_paths

    def cleanup(self) -> None:
        """Delete only a verified direct child of the configured base."""

        root = self.root.resolve()
        if not root.exists():
            return
        try:
            root = self._verified_root()
        except ValueError as error:
            raise ValueError(
                "Refusing to clean an unverified run workspace."
            ) from error
        shutil.rmtree(root)


def resolve_source(
    source: FileSource,
    outputs: Mapping[StepOutput, Path],
) -> Path:
    """Resolve a manual path or a committed output from this run only."""

    if isinstance(source, str):
        path = Path(source).resolve()
        if not path.is_file():
            raise FileNotFoundError("The manual input file is unavailable.")
        return path
    if isinstance(source, StepOutput):
        path = outputs.get(source)
        if path is None or not Path(path).is_file():
            raise MissingRuntimeOutputError(source)
        return Path(path).resolve()
    raise TypeError("A file source must be a path or StepOutput.")


@dataclass(slots=True)
class RunArtifact:
    """Mutable state and committed outputs for one compiled run."""

    compiled: CompiledPipeline = field(repr=False)
    workspace: RunWorkspace
    status: RunStatus = RunStatus.RUNNING
    outputs: dict[StepOutput, Path] = field(default_factory=dict)
    step_metadata: dict[str, dict[str, object]] = field(default_factory=dict)
    failed_step_key: str | None = None
    workspace_cleaned: bool = False

    def _require_running(self) -> None:
        if self.status is not RunStatus.RUNNING:
            raise RuntimeError("The run is no longer accepting outputs.")

    def _require_compiled_step(self, step: CompiledStep) -> None:
        if step not in self.compiled.steps:
            raise ValueError("The step does not belong to this compiled run.")

    def staging_paths(
        self,
        step: CompiledStep,
    ) -> dict[StepOutput, Path]:
        self._require_running()
        self._require_compiled_step(step)
        return self.workspace.staging_paths(step)

    def resolve_source(self, source: FileSource) -> Path:
        return resolve_source(source, self.outputs)

    def commit_step_outputs(
        self,
        step: CompiledStep,
        staged_paths: Mapping[StepOutput, Path],
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> dict[StepOutput, Path]:
        self._require_running()
        self._require_compiled_step(step)
        if any(reference in self.outputs for reference in staged_paths):
            raise StepCommitError("A runtime output is already committed.")

        committed = self.workspace.commit_step_outputs(step, staged_paths)
        self.outputs.update(committed)
        if metadata is not None:
            self.step_metadata[step.request.step_key] = dict(metadata)
        return committed

    def succeed(self) -> None:
        self._require_running()
        expected = {
            output.reference
            for step in self.compiled.steps
            for output in step.outputs
        }
        if not expected.issubset(self.outputs):
            raise RuntimeError(
                "A run cannot succeed before every output is committed."
            )
        self.status = RunStatus.SUCCEEDED

    def fail(self, step_key: str) -> None:
        self._require_running()
        self.failed_step_key = step_key
        self.status = RunStatus.FAILED

    def cancel(self) -> None:
        self._require_running()
        self.status = RunStatus.CANCELLED
        self.cleanup()

    def cleanup(self) -> None:
        if self.workspace_cleaned:
            return
        self.workspace.cleanup()
        self.workspace_cleaned = True
