"""Run the three bit-statistics detectors as one consistent analysis job."""

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

from src.core.analyzer import analyze_bit_statistics, detect_file_type
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
    media_type: str = "image"
    video_info: dict[str, Any] = field(default_factory=dict)
    audio_info: dict[str, Any] = field(default_factory=dict)


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
    progress_callback=None,
    cancel_check=None,
) -> BitStatisticsAnalysisResult:
    """Run image, video, or audio detectors against one unchanged file version."""
    validation_error = parameters.validation_error()
    if validation_error:
        raise ValueError(validation_error)

    fingerprint_before = fingerprint_file(image_path)
    file_info = detect_file_type(fingerprint_before.path)
    if file_info.media_type not in ("image", "video", "audio"):
        raise ValueError(
            f"Bit Statistics for {file_info.format_name} is a placeholder. "
            "PNG, AVI and PCM WAV detectors are connected right now."
        )

    extra = {}
    if file_info.media_type == "video":
        extra = dict(start_frame=parameters.start_frame, frame_count=parameters.frame_count,
                     progress_callback=progress_callback, cancel_check=cancel_check)
    elif file_info.media_type == "audio":
        extra = dict(progress_callback=progress_callback, cancel_check=cancel_check)
    backend_result = analyze_bit_statistics(
        fingerprint_before.path,
        min_expected=parameters.min_expected,
        prefix_step=parameters.prefix_step,
        segment_percent=parameters.segment_percent,
        segment_step=parameters.segment_step,
        spa_j=parameters.spa_j,
        spa_min_pairs=parameters.spa_min_pairs,
        **extra,
    )
    fingerprint_after = fingerprint_file(fingerprint_before.path)

    if fingerprint_after != fingerprint_before:
        raise RuntimeError("The selected file changed during analysis. Run it again.")

    return BitStatisticsAnalysisResult(
        file_path=fingerprint_before.path,
        file_fingerprint=fingerprint_before,
        parameters=parameters,
        chi_square=backend_result["chi_square"],
        rs=backend_result["rs"],
        spa=backend_result["spa"],
        image_info=backend_result.get("image_info", {}),
        media_type=file_info.media_type,
        video_info=backend_result.get("video_info", {}),
        audio_info=backend_result.get("audio_info", {}),
    )
