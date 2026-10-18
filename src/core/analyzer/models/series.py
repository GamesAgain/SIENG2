"""Reusable spatial, temporal and frame result containers."""

from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class SpatialPrefix(Generic[T]):
    """One cumulative row-major spatial prefix."""

    percent: int
    end: int
    analysis: T


@dataclass(frozen=True)
class SpatialSegment(Generic[T]):
    """One non-cumulative row-major spatial range."""

    start: int
    end: int
    analysis: T


@dataclass(frozen=True)
class SpatialSeries(Generic[T]):
    """Whole, cumulative-prefix and segment results in spatial order."""

    whole: T
    prefix: tuple[SpatialPrefix[T], ...]
    segments: tuple[SpatialSegment[T], ...]


@dataclass(frozen=True)
class TemporalPrefix(Generic[T]):
    """One cumulative prefix along a media timeline."""

    percent: int
    end_frame: int
    end_seconds: float
    analysis: T


@dataclass(frozen=True)
class TemporalSegment(Generic[T]):
    """One non-cumulative range along a media timeline."""

    start_frame: int
    end_frame: int
    start_seconds: float
    end_seconds: float
    analysis: T


@dataclass(frozen=True)
class TemporalSeries(Generic[T]):
    """Whole, cumulative-prefix and segment results over time."""

    whole: T
    prefix: tuple[TemporalPrefix[T], ...]
    segments: tuple[TemporalSegment[T], ...]


@dataclass(frozen=True)
class FrameResult(Generic[T]):
    """Detector summaries for every channel in one decoded frame."""

    frame_index: int
    timestamp_seconds: float
    channels: dict[str, T]


@dataclass(frozen=True)
class FrameDetailResult(Generic[T]):
    """On-demand detector details for one decoded frame."""

    frame_index: int
    timestamp_seconds: float
    width: int
    height: int
    channels: dict[str, T]
