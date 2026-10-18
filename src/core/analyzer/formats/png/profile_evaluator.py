"""Apply the frozen 4.5.3 PNG rules to the same Whole-target scores."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.core.analyzer.models.png import PNGDetectorDecision
from src.core.analyzer.parameters import AnalysisParameters


@lru_cache(maxsize=1)
def load_profiles() -> dict[str, Any]:
    profile = json.loads(Path(__file__).with_name("detector_profiles.json").read_text(encoding="utf-8"))
    if profile.get("schema_version") != 1:
        raise ValueError("Unsupported PNG detector profile schema.")
    return profile


def _finite(value: float | None) -> float | None:
    return float(value) if value is not None and math.isfinite(value) else None


def _decision(
    detector: str, score: float | None, threshold: float, *,
    scope: str, method: str, parameter_name: str, parameter_value: str,
    channel: str | None, compatible: bool = True, reason: str | None = None,
    inclusive: bool = False,
) -> PNGDetectorDecision:
    if not compatible:
        status, evidence = "profile_mismatch", None
    elif score is None:
        status, evidence = "insufficient_data", None
        reason = reason or "No usable Whole-target score is available."
    else:
        evidence = score >= threshold if inclusive else score > threshold
        status = "evidence_found" if evidence else "no_evidence"
    return PNGDetectorDecision(
        detector, method, scope, parameter_name, parameter_value,
        threshold, score, channel, evidence, status, reason,
    )


def evaluate_chi_square(report: dict[str, Any], parameters: AnalysisParameters) -> PNGDetectorDecision:
    """A valid first 5% segment starts the consecutive above-alpha run."""
    profile = load_profiles()["chi_square"]
    target = report.get("Whole") or report.get("L")
    channel = "Whole" if "Whole" in report else "L" if "L" in report else None
    segments = target["segments"] if target else ()
    first = segments[0].chi_square if segments else None
    score = _finite(first.p_value) if first is not None and first.status == "ok" else None
    run_end = None
    if score is not None and score >= profile["alpha"]:
        for segment in segments:
            analysis = segment.chi_square
            p_value = _finite(analysis.p_value) if analysis.status == "ok" else None
            if p_value is None or p_value < profile["alpha"]:
                break
            run_end = segment.end
    compatible = (
        parameters.min_expected == profile["min_expected"]
        and parameters.segment_percent == profile["segment_percent"]
        and parameters.segment_step == profile["segment_step"]
    )
    reason = (
        f"The initial above-alpha run ends at {100 * run_end / segments[-1].end:.1f}% of the image."
        if run_end is not None else None
    )
    decision = _decision(
        "chi_square", score, profile["alpha"],
        scope="initial_segment_run", method="sequential_lsb_replacement",
        parameter_name="segment", parameter_value="5% window / 1% step; min_expected=5",
        channel=channel, compatible=compatible,
        reason="The frozen Chi-square rule requires 5% segments, 1% steps and min_expected=5." if not compatible else reason,
        inclusive=True,
    )
    # The end belongs to the calibrated initial run of sliding segments.
    # Keep it as data so the GUI never has to parse the human-readable reason.
    return replace(
        decision,
        observed_end_percent=(
            100 * run_end / segments[-1].end
            if decision.evidence_found and run_end is not None else None
        ),
    )


def evaluate_rs(report: dict[str, Any]) -> PNGDetectorDecision:
    profile = load_profiles()["rs"]
    target = report.get("Whole") or report.get("L")
    channel = "Whole" if "Whole" in report else "L" if "L" in report else None
    score = _finite(target["payload"].embedding_rate) if target else None
    return _decision(
        "rs", score, profile["threshold"], scope="whole_image",
        method="lsb_replacement", parameter_name="mask",
        parameter_value="[0, 1, 1, 0]", channel=channel,
    )


def evaluate_spa(report: dict[str, Any], parameters: AnalysisParameters) -> PNGDetectorDecision:
    profile = load_profiles()["spa"]
    target = report.get("Whole") or report.get("L")
    channel = "Whole" if "Whole" in report else "L" if "L" in report else None
    score = _finite(target["estimate"].embedding_rate) if target else None
    compatible = parameters.spa_j == profile["j"] and parameters.spa_min_pairs == profile["min_pairs"]
    return _decision(
        "spa", score, profile["threshold"], scope="whole_image",
        method="lsb_replacement", parameter_name="j",
        parameter_value="30; min_pairs=100", channel=channel,
        compatible=compatible,
        reason="The frozen SPA rule requires j=30 and min_pairs=100." if not compatible else None,
    )
