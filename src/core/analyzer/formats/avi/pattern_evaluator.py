"""Interpret AVI Chi-square temporal curves without changing detection."""

from __future__ import annotations

import math
from typing import Any

from src.core.analyzer.formats.avi.detector.video_io import (
    prefix_ranges,
    sliding_ranges,
)
from src.core.analyzer.models.avi import (
    AVIChiSquarePattern,
    AVIDetectorDecision,
    AVIMediaInfo,
)


# Frozen from dataset/avi/experiments/chi_prefix_segments. The rule describes
# only the tested 30-frame, 160x120, uncompressed RGB AVI profile.
HIGH_P = 0.95
LOW_P = 0.05
MAX_BOUNDARY_DIFFERENCE_FRAMES = 3


def _valid_p(point: Any) -> float | None:
    analysis = point.analysis
    value = analysis.p_value
    if analysis.status != "ok" or value is None or not math.isfinite(value):
        return None
    return value


def evaluate_chi_square_pattern(
    report: dict[str, Any],
    decision: AVIDetectorDecision,
    media_info: AVIMediaInfo,
) -> AVIChiSquarePattern:
    """Identify an initial high run followed by a low tail in both curves."""
    def undetermined(reason: str) -> AVIChiSquarePattern:
        return AVIChiSquarePattern("undetermined", reason)

    if decision.status != "evidence_found":
        return undetermined("The calibrated Chi-square decision did not find evidence.")
    if (
        media_info.frame_count != 30
        or media_info.width != 160
        or media_info.height != 120
        or media_info.decoded_bits_per_pixel != 24
        or media_info.codec not in {"RGB", "DIB"}
    ):
        return undetermined("The temporal pattern rule has not been validated for this AVI profile.")

    target = report.get("targets", {}).get("Whole", {})
    prefix = target.get("temporal_prefix", ())
    segments = target.get("temporal_segments", ())
    expected_prefix = prefix_ranges(30, 10)
    expected_segments = sliding_ranges(30, 10, 5)
    if report.get("frame_count") != 30 or [
        (point.percent, point.end) for point in prefix
    ] != expected_prefix or [
        (point.start, point.end) for point in segments
    ] != expected_segments:
        return undetermined("The required 10% prefix and 10%/5% segment curves are unavailable.")
    if (_valid_p(prefix[0]) or 0.0) < HIGH_P or (_valid_p(segments[0]) or 0.0) < HIGH_P:
        return undetermined("The initial prefix and segment are not both high.")

    run_length = 0
    for point in segments:
        p = _valid_p(point)
        if p is None or p < HIGH_P:
            break
        run_length += 1
    later = [_valid_p(point) for point in segments[run_length:]]
    if len(later) < 2:
        return undetermined("There are too few post-boundary segments.")
    if any(p is None for p in later):
        return undetermined("A post-boundary segment is invalid.")
    if any(p >= HIGH_P for p in later):
        return undetermined("The segment curve has a later high rebound.")
    if sum(p <= LOW_P for p in later) < 2:
        return undetermined("The segment curve has no sustained low tail.")

    end_frame = segments[run_length - 1].end
    prefix_run = 0
    for point in prefix:
        p = _valid_p(point)
        if p is None or p < HIGH_P:
            break
        prefix_run += 1
    prefix_end = prefix[prefix_run - 1].end
    if abs(prefix_end - end_frame) > MAX_BOUNDARY_DIFFERENCE_FRAMES:
        return undetermined("The prefix and segment boundaries disagree.")
    return AVIChiSquarePattern(
        status="sequential_like",
        reason="Initial high prefix and segment runs followed by a sustained low tail.",
        end_frame=end_frame,
        end_percent=100.0 * end_frame / report["frame_count"],
    )
