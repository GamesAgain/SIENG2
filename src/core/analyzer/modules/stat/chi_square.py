"""
Chi-Square Attack (Westfeld & Pfitzmann, 1999)
----------------------------------------------
LSB Replace forces pairs (2k, 2k+1) to have equal histogram counts.

Theory:
  - Natural image  → pairs are NOT equal → large χ² stat
  - After LSB Replace (full capacity) → pairs approach equal → small χ² stat

Practical limitation at partial fill ratios (10-50%):
  Natural images produce chi2 stats in the range 100K-400K.
  Even after 50% fill, chi2 drops to ~60% of original — still enormous relative
  to the detection threshold (~150 for df=128), so p-value saturates to 0.0
  for ALL tested images regardless of algorithm.

Detection approach:
  analyze_blind() (single file, no cover) can only report the raw chi2/p_value -
  detected is None there since the absolute p-value is unusable (verified
  empirically: 50/50 real cover photos already have p_value < 0.05 with nothing
  embedded). relative_reduction() is the actual detector, used when a cover is
  available (Compare mode) - the FRACTIONAL REDUCTION of chi2:
      score = (chi2_cover - chi2_stego) / chi2_cover   ∈ [-∞, 1]
  A larger positive score means more pair equalization → more embedding detected.
  Threshold: 0.20 (≥20% chi2 reduction considered suspicious).
"""
import numpy as np
from scipy.stats import chi2 as chi2_dist

from .base import BaseAttack


class ChiSquareAttack(BaseAttack):
    name = "Chi-Square"

    def __init__(self, threshold: float = 0.20):
        # Fractional chi2 reduction threshold for detection
        # 0.20 = 20% drop in chi2 between cover and stego
        self.threshold = threshold

    def analyze_blind(self, data_array: np.ndarray) -> dict:
        """
        Blind (single-file) mode has no cover to compute the relative reduction
        against, and the absolute p_value is not usable as a verdict either -
        verified empirically across 50 real cover photos, all 50 already have
        p_value < 0.05 with nothing embedded (chi2 stays in the tens/hundreds
        of thousands, so p saturates to ~0 exactly as the module docstring
        describes). detected is None here on purpose: there is no honest blind
        threshold to apply. See relative_reduction() for the differential
        check that Compare mode uses instead, where a cover is available.
        """
        chi2_stat, p_value = self._test(data_array)
        return {
            "chi2": chi2_stat,
            "p_value": p_value,
            "detected": None
        }

    def relative_reduction(self, chi2_cover: float, chi2_stego: float) -> dict:
        """
        Differential check for Compare mode (cover + stego both available):
        fractional drop in chi2 after embedding. See module docstring.
        """
        if chi2_cover <= 0:
            return {"score": 0.0, "detected": False}
        score = (chi2_cover - chi2_stego) / chi2_cover
        return {"score": score, "detected": score >= self.threshold}



    def _test(self, arr: np.ndarray) -> tuple[float, float]:
        flat = arr.ravel()

        hist = np.bincount(flat, minlength=256).astype(np.float64)  # (256,)

        # Group into 128 pairs: (v0,v1), (v2,v3), …
        pairs = hist.reshape(-1, 2)                        # (128, 2)
        pair_sum = pairs.sum(axis=1)                       # (128,)
        expected = pair_sum / 2                            # expected count per value

        # Drop pairs where expected == 0 (both values absent)
        valid = expected > 0
        obs = pairs[valid].ravel()
        exp = np.repeat(expected[valid], 2)

        chi2_stat = float(np.sum((obs - exp) ** 2 / exp))
        df = int(valid.sum())                              # one constraint per pair

        # Use sf (survival function = 1-cdf) for numerical stability:
        # cdf saturates to 1.0 for large chi2 → 1-cdf underflows to 0.0
        p_value = float(chi2_dist.sf(chi2_stat, df))

        return chi2_stat, p_value
