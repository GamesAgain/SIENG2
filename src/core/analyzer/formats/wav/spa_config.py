"""Frozen operating configuration for WAV SPA against Random LSB replacement.

SPA models LSB replacement spread evenly over the analysed samples, which is
what Random LSB replacement does.  The profile was therefore selected on
Random-LSB Stego plus Clean files only.  Sequential LSB data were not part of
the claim; selecting on Random + Sequential gave identical parameters, and
Sequential results at these parameters are reported for reference only.

Decision rule (see ``classify_wav_spa``):

1. ``usable_pair_ratio`` below ``WAV_SPA_MIN_USABLE_RATIO`` is Unknown: too few
   adjacent pairs satisfy ``|s0 - s1| <= 2j + 2`` for the equation to be stable.
2. Status ``"estimated"`` is classified by ``WAV_SPA_THRESHOLD_RATE``.  When
   ``WAV_SPA_CLAMP_OUT_OF_RANGE`` is enabled, an ``"out_of_range"`` root is first
   clamped to 0..1 and then classified the same way.
3. Every other detector status is Unknown, not Clean.
"""

from src.core.analyzer.models.wav import (
    WAVSPAClassification,
    WAVSPADecision,
    WAVSPAEstimate,
)

WAV_SPA_SUPPORTED_METHODS = ("random_lsb_replacement",)
WAV_SPA_ANALYSIS_SCOPE = "full_file"
WAV_SPA_J = 80
WAV_SPA_MIN_PAIRS = 100
# Selected on Calibration/Validation by scripts/select_wav_spa_used_profile.py
# --methods random_lsb_replacement --tag random (see
# validation/reports/wav_spa_used_threshold_report.md, section 9).  Do not change
# these values without repeating Calibration/Validation and using a new Test.
WAV_SPA_THRESHOLD_RATE = 0.035
WAV_SPA_THRESHOLD_PERCENT = WAV_SPA_THRESHOLD_RATE * 100.0
WAV_SPA_MIN_USABLE_RATIO = 0.6
WAV_SPA_CLAMP_OUT_OF_RANGE = True


def _evaluate_values(
    status: str,
    embedding_rate: float | None,
    usable_pair_ratio: float | None,
    *,
    threshold_rate: float,
    min_usable_ratio: float,
    clamp_out_of_range: bool,
) -> tuple[WAVSPAClassification, float | None, bool, str]:
    """Apply the validated gate, clamp and threshold in one place."""
    if min_usable_ratio > 0.0 and usable_pair_ratio is None:
        return (
            "Unknown",
            None,
            False,
            "Usable-pair ratio is unavailable, so the estimate cannot be trusted.",
        )
    if (
        min_usable_ratio > 0.0
        and usable_pair_ratio is not None
        and usable_pair_ratio < min_usable_ratio
    ):
        return (
            "Unknown",
            None,
            False,
            f"Usable-pair ratio {usable_pair_ratio:.3f} is below the "
            f"required {min_usable_ratio:.3f}.",
        )
    if embedding_rate is None:
        return (
            "Unknown",
            None,
            False,
            f"SPA status '{status}' did not produce an embedding-rate estimate.",
        )

    if status == "out_of_range" and clamp_out_of_range:
        evaluated_rate = min(1.0, max(0.0, embedding_rate))
        was_clamped = evaluated_rate != embedding_rate
    elif status == "estimated":
        evaluated_rate = embedding_rate
        was_clamped = False
    else:
        return (
            "Unknown",
            None,
            False,
            f"SPA status '{status}' is not eligible for classification.",
        )

    classification = (
        "Stego" if evaluated_rate >= threshold_rate else "Clean"
    )
    clamp_note = " after clamping" if was_clamped else ""
    reason = (
        f"Evaluated rate {evaluated_rate:.4f}{clamp_note} is "
        f"{'at or above' if classification == 'Stego' else 'below'} "
        f"the {threshold_rate:.4f} threshold."
    )
    return classification, evaluated_rate, was_clamped, reason


def evaluate_wav_spa(
    estimate: WAVSPAEstimate,
    *,
    threshold_rate: float = WAV_SPA_THRESHOLD_RATE,
    min_usable_ratio: float = WAV_SPA_MIN_USABLE_RATIO,
    clamp_out_of_range: bool = WAV_SPA_CLAMP_OUT_OF_RANGE,
    j: int = WAV_SPA_J,
    min_pairs: int = WAV_SPA_MIN_PAIRS,
) -> WAVSPADecision:
    """Return a transparent three-state decision for one WAV SPA estimate."""
    classification, evaluated_rate, was_clamped, reason = _evaluate_values(
        estimate.status,
        estimate.embedding_rate,
        estimate.usable_pair_ratio,
        threshold_rate=threshold_rate,
        min_usable_ratio=min_usable_ratio,
        clamp_out_of_range=clamp_out_of_range,
    )
    return WAVSPADecision(
        classification=classification,
        raw_rate=estimate.embedding_rate,
        evaluated_rate=evaluated_rate,
        usable_pair_ratio=estimate.usable_pair_ratio,
        threshold_rate=threshold_rate,
        min_usable_ratio=min_usable_ratio,
        j=j,
        min_pairs=min_pairs,
        was_clamped=was_clamped,
        supported_methods=WAV_SPA_SUPPORTED_METHODS,
        analysis_scope=WAV_SPA_ANALYSIS_SCOPE,
        reason=reason,
    )


def classify_wav_spa(
    status: str,
    embedding_rate: float | None,
    usable_pair_ratio: float | None = None,
    *,
    threshold_rate: float = WAV_SPA_THRESHOLD_RATE,
    min_usable_ratio: float = WAV_SPA_MIN_USABLE_RATIO,
    clamp_out_of_range: bool = WAV_SPA_CLAMP_OUT_OF_RANGE,
) -> str:
    """Return the frozen three-state decision for one WAV SPA estimate.

    Keyword arguments default to the frozen profile; they exist so that the
    calibration scripts can evaluate candidate rules with the same function.
    """
    classification, _rate, _clamped, _reason = _evaluate_values(
        status,
        embedding_rate,
        usable_pair_ratio,
        threshold_rate=threshold_rate,
        min_usable_ratio=min_usable_ratio,
        clamp_out_of_range=clamp_out_of_range,
    )
    return classification
