"""Shared percentage-based ranges for image, audio and video analysis."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PrefixRange:
    """One cumulative range from unit zero through ``end`` (exclusive)."""

    percent: int
    end: int


@dataclass(frozen=True)
class SlidingRange:
    """One non-cumulative range with an exclusive end position."""

    start: int
    end: int


def _validate_percent(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer.")
    if not 1 <= value <= 100:
        raise ValueError(f"{name} must be between 1 and 100.")


def _validate_total_units(total_units: int) -> None:
    if isinstance(total_units, bool) or not isinstance(total_units, int):
        raise ValueError("total_units must be an integer.")
    if total_units < 0:
        raise ValueError("total_units cannot be negative.")


def progressive_prefix_ranges(
    total_units: int,
    step_percent: int,
) -> tuple[PrefixRange, ...]:
    """Return cumulative percentage ranges, always including 100 percent."""
    _validate_total_units(total_units)
    _validate_percent("step_percent", step_percent)

    percents = [*range(step_percent, 100, step_percent), 100]
    return tuple(
        PrefixRange(
            percent=percent,
            end=math.ceil(total_units * percent / 100),
        )
        for percent in percents
    )


def sliding_ranges(
    total_units: int,
    segment_percent: int,
    step_percent: int,
) -> tuple[SlidingRange, ...]:
    """Return fixed-size percentage ranges and include the final boundary."""
    _validate_total_units(total_units)
    _validate_percent("segment_percent", segment_percent)
    _validate_percent("step_percent", step_percent)
    if step_percent > segment_percent:
        raise ValueError("step_percent must not exceed segment_percent.")
    if total_units == 0:
        return ()

    segment_size = math.ceil(total_units * segment_percent / 100)
    stride = max(1, math.ceil(total_units * step_percent / 100))
    starts = list(range(0, total_units - segment_size + 1, stride))
    last_start = total_units - segment_size
    if starts[-1] != last_start:
        starts.append(last_start)

    return tuple(
        SlidingRange(start=start, end=start + segment_size)
        for start in starts
    )
