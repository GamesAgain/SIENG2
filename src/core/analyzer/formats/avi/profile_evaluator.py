"""Apply frozen dataset/avi thresholds to compatible detector scores."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any

from src.core.analyzer.models.avi import AVIDetectorDecision
from src.core.analyzer.parameters import AnalysisParameters


PROFILE_PATH = Path(__file__).with_name("detector_profiles.json")


class AVIProfileError(ValueError):
    """Raised when the frozen AVI profile cannot be used safely."""


@lru_cache(maxsize=1)
def load_frozen_profiles() -> dict[str, Any]:
    """Load and minimally validate the versioned profile configuration."""
    try:
        payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AVIProfileError(
            f"Cannot load AVI detector profile: {exc}"
        ) from exc

    if payload.get("schema_version") != 1:
        raise AVIProfileError("Unsupported AVI detector profile schema.")
    if payload.get("profile_state") != "frozen":
        raise AVIProfileError("AVI detector profile is not frozen.")
    if payload.get("source_dataset") != "dataset/avi":
        raise AVIProfileError("AVI profile has the wrong source dataset.")
    if payload.get("score_direction") != "stego when score > threshold":
        raise AVIProfileError("Unsupported AVI profile score direction.")

    profiles = payload.get("detector_profiles")
    if not isinstance(profiles, dict):
        raise AVIProfileError("AVI detector profiles are missing.")
    for detector in ("chi_square", "spa", "rs"):
        profile = profiles.get(detector)
        if not isinstance(profile, dict):
            raise AVIProfileError(
                f"AVI profile for {detector} is missing."
            )
        required = {
            "training_method",
            "parameter_name",
            "parameter_value",
            "analysis_channel",
            "scope",
            "threshold",
        }
        if not required.issubset(profile):
            raise AVIProfileError(
                f"AVI profile for {detector} is incomplete."
            )
        if profile["analysis_channel"] != "Whole":
            raise AVIProfileError(
                f"AVI profile for {detector} must use the Whole target."
            )
        threshold = profile["threshold"]
        if not isinstance(threshold, (int, float)) or not math.isfinite(
            float(threshold)
        ):
            raise AVIProfileError(
                f"AVI profile threshold for {detector} is invalid."
            )
    return payload


def _profile_unavailable(
    detector: str,
    reason: str,
) -> AVIDetectorDecision:
    return AVIDetectorDecision(
        detector=detector,
        expected_method="unknown",
        scope="unknown",
        parameter_name="unknown",
        parameter_value="unknown",
        threshold=None,
        score=None,
        selected_channel=None,
        evidence_found=None,
        status="profile_unavailable",
        reason=reason,
    )


def _profile(detector: str) -> dict[str, Any]:
    return load_frozen_profiles()["detector_profiles"][detector]


def _finite_score(value: Any) -> float | None:
    if value is None:
        return None
    score = float(value)
    return score if math.isfinite(score) else None


def _decision(
    detector: str,
    profile: dict[str, Any],
    channel: str | None,
    score: float | None,
    compatible: bool,
    mismatch_reason: str | None = None,
) -> AVIDetectorDecision:
    threshold = float(profile["threshold"])
    common = dict(
        detector=detector,
        expected_method=str(profile["training_method"]),
        scope=str(profile["scope"]),
        parameter_name=str(profile["parameter_name"]),
        parameter_value=str(profile["parameter_value"]),
        threshold=threshold,
        score=score,
        selected_channel=channel,
    )
    if not compatible:
        return AVIDetectorDecision(
            **common,
            evidence_found=None,
            status="profile_mismatch",
            reason=mismatch_reason,
        )
    if score is None:
        return AVIDetectorDecision(
            **common,
            evidence_found=None,
            status="insufficient_data",
            reason="No valid Whole-target score is available for this profile.",
        )
    evidence_found = score > threshold
    return AVIDetectorDecision(
        **common,
        evidence_found=evidence_found,
        status="evidence_found" if evidence_found else "no_evidence",
    )


def evaluate_chi_square_profile(
    report: dict[str, Any],
    parameters: AnalysisParameters,
) -> AVIDetectorDecision:
    """Use the maximum valid Whole-target p-value over 10% temporal prefixes."""
    try:
        profile = _profile("chi_square")
    except AVIProfileError as exc:
        return _profile_unavailable("chi_square", str(exc))

    if profile["scope"] != "max_temporal_prefix":
        return _profile_unavailable("chi_square", "Invalid Chi-square score scope.")
    target = report.get("targets", {}).get("Whole")
    valid_prefixes = (
        [(item.percent, _finite_score(item.analysis.p_value))
         for item in target.get("temporal_prefix", ())
         if item.analysis.status == "ok"]
        if isinstance(target, dict) else []
    )
    valid_prefixes = [item for item in valid_prefixes if item[1] is not None]
    strongest = max(valid_prefixes, key=lambda item: item[1], default=None)
    score = strongest[1] if strongest is not None else None
    channel = "Whole" if isinstance(target, dict) else None
    expected = float(profile["parameter_value"])
    mismatch_reason = None
    if not math.isclose(float(parameters.min_expected), expected, rel_tol=0.0, abs_tol=1e-12):
        mismatch_reason = f"The locked Chi-square profile requires min_expected={expected:g}."
    elif parameters.prefix_step != profile["prefix_step"]:
        mismatch_reason = f"The locked Chi-square profile requires prefix_step={profile['prefix_step']}%."
    decision = _decision(
        "chi_square",
        profile,
        channel,
        score,
        mismatch_reason is None,
        mismatch_reason,
    )
    return replace(
        decision,
        score_prefix_percent=(
            strongest[0] if decision.evidence_found and strongest else None
        ),
    )


def evaluate_spa_profile(
    report: dict[str, Any],
    parameters: AnalysisParameters,
) -> AVIDetectorDecision:
    """Evaluate the locked Whole-target SPA estimate."""
    try:
        profile = _profile("spa")
    except AVIProfileError as exc:
        return _profile_unavailable("spa", str(exc))

    target = report.get("targets", {}).get("Whole")
    estimate = target["whole"].estimate if isinstance(target, dict) else None
    score = (_finite_score(estimate.embedding_rate)
             if estimate is not None and estimate.status == "estimated" else None)
    channel = "Whole" if isinstance(target, dict) else None
    expected = int(profile["parameter_value"])
    mismatch_reason = None
    if parameters.spa_j != expected or parameters.spa_min_pairs != profile["min_pairs"]:
        mismatch_reason = (
            f"The locked SPA profile requires j={expected} and "
            f"min_pairs={profile['min_pairs']}."
        )
    return _decision(
        "spa",
        profile,
        channel,
        score,
        mismatch_reason is None,
        mismatch_reason,
    )


def evaluate_rs_profile(report: dict[str, Any]) -> AVIDetectorDecision:
    """Evaluate the locked Whole-target RS estimate."""
    try:
        profile = _profile("rs")
    except AVIProfileError as exc:
        return _profile_unavailable("rs", str(exc))

    target = report.get("targets", {}).get("Whole")
    estimate = target["whole"].payload if isinstance(target, dict) else None
    score = (_finite_score(estimate.embedding_rate)
             if estimate is not None and estimate.status == "estimated" else None)
    channel = "Whole" if isinstance(target, dict) else None
    try:
        expected_mask = tuple(json.loads(profile["parameter_value"]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return _profile_unavailable("rs", "The RS profile mask is invalid.")
    actual_mask = tuple(report.get("mask", ()))
    mismatch_reason = None
    if actual_mask != expected_mask:
        mismatch_reason = f"The locked RS profile requires mask={expected_mask}."
    return _decision(
        "rs",
        profile,
        channel,
        score,
        mismatch_reason is None,
        mismatch_reason,
    )
