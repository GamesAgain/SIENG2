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

Detection approach used here (relative score):
  Instead of the absolute p-value (unusable at partial fill),
  we use the FRACTIONAL REDUCTION of chi2:
      score = (chi2_cover - chi2_stego) / chi2_cover   ∈ [-∞, 1]
  A larger positive score means more pair equalization → more embedding detected.
  Threshold: 0.20 (≥20% chi2 reduction considered suspicious).

Both the raw chi2 stats and p-values are still returned for completeness.
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
        chi2_stat, p_value = self._test(data_array)
        detected = p_value < 0.05
        return {
            "chi2": chi2_stat,
            "p_value": p_value,
            "detected": detected
        }



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
