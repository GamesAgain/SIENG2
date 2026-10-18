"""WAV-specific models."""

from dataclasses import dataclass
from typing import Literal, TypeAlias

from src.core.analyzer.models.common import RSMeasurement
from src.core.analyzer.models.series import TemporalSeries


WAVEvidenceClassification: TypeAlias = Literal["Clean", "Stego", "Unknown"]
WAVSPAClassification: TypeAlias = WAVEvidenceClassification


@dataclass(frozen=True)
class WAVMediaInfo:
    channel_count: int
    sample_rate: int
    frame_count: int
    sample_count: int
    duration_seconds: float
    sample_width_bits: int
    compression_type: str
    compression_name: str


@dataclass(frozen=True)
class WAVChiSquareAnalysis:
    """Basic PoV Chi-square result for one PCM channel."""

    chi_square_total: float | None
    p_value: float | None
    dof: int | None = None
    sample_count: int = 0
    valid_pairs: int = 0


@dataclass(frozen=True)
class WAVChiSquarePrefixResult:
    """Chi-square result for one cumulative CH1 prefix."""

    percent: int
    end_sample: int
    end_seconds: float
    analysis: WAVChiSquareAnalysis


@dataclass(frozen=True)
class WAVChiSquareSegmentResult:
    """Chi-square result for one non-cumulative CH1 time segment."""

    start_sample: int
    end_sample: int
    start_seconds: float
    end_seconds: float
    analysis: WAVChiSquareAnalysis


@dataclass(frozen=True)
class WAVChiSquareResult:
    """Chi-square timelines grouped by WAV channel name."""

    channels: dict[str, TemporalSeries[WAVChiSquareAnalysis]]


@dataclass(frozen=True)
class WAVRSStatistics:
    """RS group counts and fractions for masks M and -M on one PCM channel."""

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


@dataclass(frozen=True)
class WAVRSPayloadEstimate:
    embedding_rate: float | None
    estimated_payload_bits: float | None
    expected_changed_samples: float | None
    capacity_samples: int
    root: float | None = None
    status: str = "unavailable"
    reason: str | None = None


@dataclass(frozen=True)
class WAVRSDecision:
    classification: WAVEvidenceClassification
    evaluated_rate: float | None
    threshold_rate: float
    reason: str
    analysis_scope: str


@dataclass(frozen=True)
class WAVRSResult:
    """Whole, prefix and segment RS measurements by WAV channel."""

    channels: dict[str, TemporalSeries[RSMeasurement]]
    decision: WAVRSDecision | None = None


@dataclass(frozen=True)
class WAVSPAStatistics:
    """Raw counts collected from adjacent PCM16 sample pairs."""

    j: int
    c_counts: tuple[int, ...]
    d_counts: tuple[int, ...]
    x_counts: tuple[int, ...]
    y_counts: tuple[int, ...]
    pair_count: int
    sample_count: int


@dataclass(frozen=True)
class WAVSPADiagnostics:
    """Named inputs and intermediate values of the WAV SPA equation."""

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


@dataclass(frozen=True)
class WAVSPAEstimate:
    """Estimated LSB replacement rate and equation diagnostics."""

    embedding_rate: float | None
    estimated_payload_bits: float | None
    expected_changed_samples: float | None
    pair_count: int
    sample_count: int
    coefficients: tuple[float, float, float] | None = None
    roots: tuple[float, ...] = ()
    discriminant: float | None = None
    status: str = "unavailable"
    reason: str | None = None
    diagnostics: WAVSPADiagnostics | None = None
    # Fraction of adjacent pairs with |s0 - s1| <= 2j + 2, i.e. the pairs the
    # equation can actually use.  A low value means the estimate is unstable.
    usable_pair_ratio: float | None = None


@dataclass(frozen=True)
class WAVSPADecision:
    """Operational decision made with the frozen, validated WAV SPA profile."""

    classification: WAVSPAClassification
    raw_rate: float | None
    evaluated_rate: float | None
    usable_pair_ratio: float | None
    threshold_rate: float
    min_usable_ratio: float
    j: int
    min_pairs: int
    was_clamped: bool
    supported_methods: tuple[str, ...]
    analysis_scope: str
    reason: str


@dataclass(frozen=True)
class WAVSPAAnalysis:
    """Raw SPA statistics together with their estimated payload."""

    statistics: WAVSPAStatistics
    estimate: WAVSPAEstimate
    decision: WAVSPADecision | None = None


@dataclass(frozen=True)
class WAVSPAResult:
    """SPA results grouped by WAV channel name."""

    channels: dict[str, WAVSPAAnalysis]
    decision: WAVSPADecision | None = None
