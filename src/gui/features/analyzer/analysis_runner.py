"""Run the three bit-statistics detectors as one consistent analysis job."""

from dataclasses import dataclass, field
from PIL import Image
from hashlib import sha256
from pathlib import Path
from typing import Any

from src.core.analyzer.bit_statistics.chi_square import analyze_chi_square
from src.core.analyzer.bit_statistics.rs_analysis import analyze_rs
from src.core.analyzer.bit_statistics.spa import analyze_spa
from src.gui.features.analyzer.analysis_parameters_dialog import AnalysisParameters


@dataclass(frozen=True)
class FileFingerprint:
    """Identity of the exact file version used by an analysis job."""

    path: str
    size: int
    modified_ns: int
    sha256: str


@dataclass(frozen=True)
class BitStatisticsAnalysisResult:
    """Results from all detectors together with their input context."""

    file_path: str
    file_fingerprint: FileFingerprint
    parameters: AnalysisParameters
    chi_square: dict[str, Any]
    rs: dict[str, Any]
    spa: dict[str, Any]
    image_info: dict[str, Any] = field(default_factory=dict)


def fingerprint_file(file_path: str) -> FileFingerprint:
    """Hash a stable file and include its size and modification time."""
    path = Path(file_path).resolve(strict=True)
    stat_before = path.stat()
    digest = sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    stat_after = path.stat()

    before = (stat_before.st_size, stat_before.st_mtime_ns)
    after = (stat_after.st_size, stat_after.st_mtime_ns)
    if before != after:
        raise RuntimeError("The selected file changed while it was being read.")

    return FileFingerprint(
        path=str(path),
        size=stat_after.st_size,
        modified_ns=stat_after.st_mtime_ns,
        sha256=digest.hexdigest(),
    )


def run_bit_statistics_analysis(
    image_path: str,
    parameters: AnalysisParameters,
) -> BitStatisticsAnalysisResult:
    """Run Chi-square, RS and SPA against one unchanged image version."""
    validation_error = parameters.validation_error()
    if validation_error:
        raise ValueError(validation_error)

    fingerprint_before = fingerprint_file(image_path)
    with Image.open(fingerprint_before.path) as image:
        image_info = dict(name=Path(image_path).name, width=image.width,
                          height=image.height, mode=image.mode, format=image.format)
    chi_square_result = analyze_chi_square(
        fingerprint_before.path,
        min_expected=parameters.min_expected,
        prefix_step=parameters.prefix_step,
        segment_percent=parameters.segment_percent,
        segment_step=parameters.segment_step,
    )
    rs_result = analyze_rs(
        fingerprint_before.path,
        prefix_step=parameters.prefix_step,
    )
    spa_result = analyze_spa(
        fingerprint_before.path,
        j=parameters.spa_j,
        min_pairs=parameters.spa_min_pairs,
    )
    fingerprint_after = fingerprint_file(fingerprint_before.path)

    if fingerprint_after != fingerprint_before:
        raise RuntimeError("The selected file changed during analysis. Run it again.")

    return BitStatisticsAnalysisResult(
        file_path=fingerprint_before.path,
        file_fingerprint=fingerprint_before,
        parameters=parameters,
        chi_square=chi_square_result,
        rs=rs_result,
        spa=spa_result,
        image_info=image_info,
    )
