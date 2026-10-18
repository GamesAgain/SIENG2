"""Frozen WAV SPA operating point from the src overlapping-pair experiment.

The threshold is the 68th ordered score of 70 Development covers.  It was
locked before evaluation on the 30-cover/360-stego hold-out Test set.  See
scripts/wav/src_spa_overlap/EXPERIMENT_REPORT_TH.md for the recorded results.
"""

from __future__ import annotations

from math import isfinite

from src.core.analyzer.models.wav import WAVSPADecision, WAVSPAEstimate
from src.core.analyzer.parameters import AnalysisParameters

PROFILE_J = 30
PROFILE_MIN_PAIRS = 100
PROFILE_THRESHOLD = 0.4290213796957147
PROFILE_METHODS = ("lsb_replacement_sequential", "lsb_replacement_shuffled")
PROFILE_SCOPE = "whole_file_mono_pcm16"


def evaluate_experimental_spa_profile(
    estimate: WAVSPAEstimate,
    parameters: AnalysisParameters,
    *,
    channel_count: int,
    sample_rate: int,
    sample_count: int,
) -> WAVSPADecision:
    """Apply the locked score rule to a valid mono PCM16 estimate."""
    mismatches = []
    if parameters.spa_j != PROFILE_J or parameters.spa_min_pairs != PROFILE_MIN_PAIRS:
        mismatches.append(f"SPA requires j={PROFILE_J} and min_pairs={PROFILE_MIN_PAIRS}")
    if channel_count != 1:
        mismatches.append("profile requires mono PCM16 audio")

    rate = estimate.embedding_rate
    usable = estimate.status == "estimated" and rate is not None and isfinite(rate)
    if mismatches:
        classification = "Unknown"
        evaluated_rate = None
        reason = "Experimental profile unavailable: " + "; ".join(mismatches) + "."
    elif not usable:
        classification = "Unknown"
        evaluated_rate = None
        reason = f"SPA returned '{estimate.status}'; no valid score is available."
        if estimate.reason:
            reason += f" {estimate.reason}"
    else:
        evaluated_rate = rate
        classification = "Stego" if rate > PROFILE_THRESHOLD else "Clean"
        reason = (
            f"Valid SPA score {rate:.6f} "
            + ("exceeds" if classification == "Stego" else "does not exceed")
            + f" the locked {PROFILE_THRESHOLD:.6f} threshold."
        )

    return WAVSPADecision(
        classification=classification,
        raw_rate=rate,
        evaluated_rate=evaluated_rate,
        usable_pair_ratio=estimate.usable_pair_ratio,
        threshold_rate=PROFILE_THRESHOLD,
        min_usable_ratio=0.0,
        j=PROFILE_J,
        min_pairs=PROFILE_MIN_PAIRS,
        was_clamped=False,
        supported_methods=PROFILE_METHODS,
        analysis_scope=PROFILE_SCOPE,
        reason=reason,
    )
