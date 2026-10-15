"""Run Docker inspection against a stable version of the selected file."""

from dataclasses import dataclass

from src.core.analyzer.inspection.bridge import inspect
from src.gui.features.analyzer.analysis_runner import FileFingerprint, fingerprint_file


@dataclass(frozen=True)
class InspectionResult:
    file_path: str
    file_fingerprint: FileFingerprint
    data: dict


def run_inspection(file_path: str, *, cancel_check=None) -> InspectionResult:
    before = fingerprint_file(file_path)
    data = inspect(before.path, cancel_check=cancel_check)
    after = fingerprint_file(before.path)
    if before != after:
        raise RuntimeError("The selected file changed during inspection. Run it again.")
    return InspectionResult(before.path, before, data)
