"""PNG-specific media and bit-statistics result models."""

from dataclasses import dataclass

from src.core.analyzer.formats.png.detector.chi_square import ChiSquareResult
from src.core.analyzer.formats.png.detector.spa import SPAEstimate, SPAStatistics
from src.core.analyzer.models.common import RSMeasurement
from src.core.analyzer.models.series import SpatialSeries


@dataclass(frozen=True)
class PNGMediaInfo:
    """Technical image information read while loading a PNG."""

    width: int
    height: int
    mode: str


@dataclass(frozen=True)
class PNGDetectorDecision:
    """Frozen PNG threshold result, separate from the raw detector report."""

    detector: str
    expected_method: str
    scope: str
    parameter_name: str
    parameter_value: str
    threshold: float
    score: float | None
    selected_channel: str | None
    evidence_found: bool | None
    status: str
    reason: str | None = None
    observed_end_percent: float | None = None


@dataclass(frozen=True)
class PNGChiSquareResult:
    """Chi-square results keyed by Whole/R/G/B or L image targets."""

    channels: dict[str, SpatialSeries[ChiSquareResult]]
    decision: PNGDetectorDecision | None = None


@dataclass(frozen=True)
class PNGRSResult:
    """RS results keyed by Whole/R/G/B or L image targets."""

    channels: dict[str, SpatialSeries[RSMeasurement]]
    decision: PNGDetectorDecision | None = None


@dataclass(frozen=True)
class PNGSPAAnalysis:
    """Raw SPA counts and estimate for one image channel."""

    statistics: SPAStatistics
    estimate: SPAEstimate


@dataclass(frozen=True)
class PNGSPAResult:
    """SPA results keyed by Whole/R/G/B or L image targets."""

    channels: dict[str, PNGSPAAnalysis]
    decision: PNGDetectorDecision | None = None
