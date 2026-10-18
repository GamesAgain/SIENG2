"""Run inspection against a stable version of the selected file."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from src.core.analyzer.inspection.bridge import inspect


@dataclass(frozen=True)
class InspectionFingerprint:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class InspectionResult:
    file_path: str
    file_fingerprint: InspectionFingerprint
    data: dict


def fingerprint_file(file_path: str) -> InspectionFingerprint:
    """Fingerprint the whole source file before and after inspection."""
    path = Path(file_path).resolve(strict=True)
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return InspectionFingerprint(str(path), path.stat().st_size, digest.hexdigest())


def run_inspection(file_path: str, *, cancel_check=None) -> InspectionResult:
    """Reject an inspection result when the selected file changes mid-run."""
    before = fingerprint_file(file_path)
    data = inspect(before.path, cancel_check=cancel_check)
    after = fingerprint_file(before.path)
    if before != after:
        raise RuntimeError("The selected file changed during inspection. Run it again.")
    return InspectionResult(before.path, before, data)
