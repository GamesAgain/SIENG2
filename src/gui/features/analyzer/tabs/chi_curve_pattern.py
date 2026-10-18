"""A descriptive first-run reading of displayed Chi-square curves."""

from __future__ import annotations

import math


def _p(item) -> float | None:
    value = item.analysis.p_value
    status = getattr(item.analysis, "status", "ok")
    if status != "ok" or value is None or not math.isfinite(value):
        return None
    return value


def initial_pattern_end_percent(series) -> float | None:
    """Return an approximate end only when prefix and segment shapes agree.

    This reads chart shape for display. It is not a detection threshold.
    """
    prefix = series.prefix
    segments = series.segments
    if not prefix or len(segments) < 2:
        return None
    high, low = 0.95, 0.05
    if (_p(prefix[0]) or 0.0) < high or (_p(segments[0]) or 0.0) < high:
        return None

    segment_run = 0
    for item in segments:
        value = _p(item)
        if value is None or value < high:
            break
        segment_run += 1
    tail = [_p(item) for item in segments[segment_run:]]
    if not tail or any(value is None for value in tail):
        return None
    if not any(value <= low for value in tail):
        return None
    if any(value >= high for value in tail):
        return None

    prefix_run = 0
    for item in prefix:
        value = _p(item)
        if value is None or value < high:
            break
        prefix_run += 1
    prefix_tail = [_p(item) for item in prefix[prefix_run:]]
    if not any(value is not None and value <= low for value in prefix_tail):
        return None

    temporal = hasattr(segments[0], "end_frame")
    end_name = "end_frame" if temporal else "end"
    segment_end = getattr(segments[segment_run - 1], end_name)
    prefix_end = getattr(prefix[prefix_run - 1], end_name)
    total = getattr(prefix[-1], end_name)
    first_prefix_end = getattr(prefix[0], end_name)
    first_segment_width = (
        getattr(segments[0], end_name)
        - getattr(segments[0], "start_frame" if temporal else "start")
    )
    if total <= 0 or abs(prefix_end - segment_end) > max(
        first_prefix_end, first_segment_width
    ):
        return None
    return 100.0 * segment_end / total
