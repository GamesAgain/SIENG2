"""Single source of truth for AVI detector and handler result models."""

from dataclasses import dataclass
from typing import Generic, TypeAlias, TypeVar

from src.core.analyzer.models.series import (
    FrameDetailResult,
    FrameResult,
    SpatialSeries,
    TemporalSeries,
)


T = TypeVar("T")


@dataclass(frozen=True)
class AVIDetectorDecision:
    """Calibrated AVI assessment kept separate from raw detector output."""

    detector: str
    expected_method: str
    scope: str
    parameter_name: str
    parameter_value: str
    threshold: float | None
    score: float | None
    selected_channel: str | None
    evidence_found: bool | None
    status: str
    reason: str | None = None
    score_prefix_percent: int | None = None


@dataclass(frozen=True)
class AVIChiSquarePattern:
    """Descriptive temporal pattern, separate from the detection decision."""

    status: str
    reason: str
    end_frame: int | None = None
    end_percent: float | None = None


@dataclass(frozen=True)
class AVIMediaInfo:
    """Technical video information read while loading an AVI."""

    width: int
    height: int
    frame_rate: float
    frame_count: int
    duration_seconds: float
    codec: str | None = None
    decoded_bits_per_pixel: int | None = None


@dataclass(frozen=True)
class AVIPrefixResult(Generic[T]):
    """Cumulative prefix ending at an exclusive frame or pixel index."""

    percent: int
    end: int
    analysis: T


@dataclass(frozen=True)
class AVISegmentResult(Generic[T]):
    """Non-cumulative range using inclusive start and exclusive end."""

    start: int
    end: int
    analysis: T


@dataclass
class AVIChiSquareAnalysis:
    """Chi-square Pairs-of-Values result for one AVI sample range."""

    chi_square_total: float | None
    p_value: float | None
    dof: int | None = None
    sample_count: int | None = None
    valid_pairs: int | None = None
    status: str = "unavailable"
    reason: str | None = None


@dataclass
class AVIRSStatistics:
    """Regular, singular and unusable RS group statistics."""

    total_groups: int = 0
    sample_count: int = 0
    RM_count: int = 0
    SM_count: int = 0
    UM_count: int = 0
    R_negM_count: int = 0
    S_negM_count: int = 0
    U_negM_count: int = 0
    RM: float | None = None
    SM: float | None = None
    UM: float | None = None
    R_negM: float | None = None
    S_negM: float | None = None
    U_negM: float | None = None


@dataclass
class AVIRSPayloadEstimate:
    """Payload-rate estimate derived from pooled AVI RS counts."""

    embedding_rate: float | None
    estimated_payload_bits: float | None
    expected_changed_samples: float | None
    capacity_samples: int
    root: float | None = None
    status: str = "unavailable"
    reason: str | None = None


@dataclass
class AVIRSMeasurement:
    """RS group statistics paired with their payload estimate."""

    rs: AVIRSStatistics
    payload: AVIRSPayloadEstimate


@dataclass
class AVISPAStatistics:
    c_counts: list[int]
    d_counts: list[int]
    x_counts: list[int]
    y_counts: list[int]
    pair_count: int
    sample_count: int


@dataclass
class AVISPADiagnostics:
    j: int
    c0: int
    c_j_plus_1: int
    d0: int
    d_2j_plus_2: int
    sum_x: int
    sum_y: int
    trace_difference: int
    discriminant: float | None = None
    selected_root: float | None = None


@dataclass
class AVISPAEstimate:
    embedding_rate: float | None
    estimated_payload_bits: float | None
    expected_changed_samples: float | None
    pair_count: int
    sample_count: int
    coefficients: tuple[float, float, float] | None = None
    roots: tuple[float, ...] = ()
    status: str = "unavailable"
    reason: str | None = None
    diagnostics: AVISPADiagnostics | None = None


@dataclass
class AVISPAAnalysis:
    statistics: AVISPAStatistics
    estimate: AVISPAEstimate


AVIFrameChiSquareResult: TypeAlias = FrameResult[AVIChiSquareAnalysis]
AVIFrameChiSquareDetailResult: TypeAlias = FrameDetailResult[
    SpatialSeries[AVIChiSquareAnalysis]
]


@dataclass(frozen=True)
class AVIChiSquareResult:
    """AVI Chi-square results for the full video and decoded frames."""

    video: dict[str, TemporalSeries[AVIChiSquareAnalysis]]
    frames: tuple[AVIFrameChiSquareResult, ...]
    analyzed_frame_count: int
    total_frame_count: int
    decision: AVIDetectorDecision | None = None
    pattern: AVIChiSquarePattern | None = None


AVIFrameRSResult: TypeAlias = FrameResult[AVIRSMeasurement]
AVIFrameRSDetailResult: TypeAlias = FrameDetailResult[
    SpatialSeries[AVIRSMeasurement]
]


@dataclass(frozen=True)
class AVIRSResult:
    """AVI RS results for the full video and decoded frames."""

    video: dict[str, TemporalSeries[AVIRSMeasurement]]
    frames: tuple[AVIFrameRSResult, ...]
    analyzed_frame_count: int
    total_frame_count: int
    decision: AVIDetectorDecision | None = None


AVIFrameSPAResult: TypeAlias = FrameResult[AVISPAAnalysis]
AVIFrameSPADetailResult: TypeAlias = FrameDetailResult[AVISPAAnalysis]


@dataclass(frozen=True)
class AVISPAResult:
    """AVI SPA results for the full video and decoded frames."""

    video: dict[str, TemporalSeries[AVISPAAnalysis]]
    frames: tuple[AVIFrameSPAResult, ...]
    analyzed_frame_count: int
    total_frame_count: int
    decision: AVIDetectorDecision | None = None
