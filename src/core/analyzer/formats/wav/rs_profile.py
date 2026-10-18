"""Locked WAV RS threshold from ref's Development/Test experiment.

The RS detector's score and status match all 390 rows in the locked Test
scores.  The threshold is from dataset/wav/dev/results/calibration_5fold.
"""

from __future__ import annotations

from math import isfinite

from src.core.analyzer.models.wav import WAVRSDecision, WAVRSPayloadEstimate

PROFILE_THRESHOLD = 0.5573329600403398
PROFILE_SCOPE = "whole_file_mono_pcm16"


def evaluate_rs_profile(
    estimate: WAVRSPayloadEstimate,
    *,
    channel_count: int,
    sample_rate: int,
    sample_count: int,
) -> WAVRSDecision:
    """Use ref's strict score > threshold rule for mono PCM16 audio."""
    if channel_count != 1:
        classification = "Unknown"
        score = None
        reason = "The locked RS threshold requires mono PCM16 audio."
    elif (estimate.status != "estimated" or estimate.embedding_rate is None
          or not isfinite(estimate.embedding_rate)):
        classification = "Unknown"
        score = None
        reason = f"RS returned '{estimate.status}'; no valid score is available."
        if estimate.reason:
            reason += f" {estimate.reason}"
    else:
        score = estimate.embedding_rate
        classification = "Stego" if score > PROFILE_THRESHOLD else "Clean"
        reason = (
            f"Valid RS score {score:.6f} "
            + ("exceeds" if classification == "Stego" else "does not exceed")
            + f" the locked {PROFILE_THRESHOLD:.6f} threshold."
        )
    return WAVRSDecision(classification, score, PROFILE_THRESHOLD, reason,
                         PROFILE_SCOPE)
