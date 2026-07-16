"""
RS Analysis (Regular / Singular groups) - blind LSB-replacement detector that
estimates the embedding rate.

Reference: Fridrich, J., Goljan, M., & Du, R. (2001). "Reliable Detection of LSB
Steganography in Color and Grayscale Images." ACM Workshop on Multimedia & Security.
Rate-estimation cross-checked against Aletheia (Lerch-Hostalot,
https://github.com/daniellerch/aletheia) - re-implemented here, not copied.

How it works:
  Split each channel into groups of 4 adjacent pixels. A discrimination function
  f(G) = sum of |adjacent differences| measures group "noisiness". Apply a flipping
  mask M to the group and see whether f increases (Regular group) or decreases
  (Singular group). Do this for the mask M and its negation -M, on both the image
  as-is and the image with all LSBs flipped, giving four R-S measurements:
      d0  = R-S for (image,        M)      d1  = R-S for (LSB-flipped, M)
      nd0 = R-S for (image,       -M)      nd1 = R-S for (LSB-flipped, -M)
  The embedding rate is recovered from the RS-diagram quadratic:
      2(d1+d0)z^2 + (nd0 - nd1 - d1 - 3*d0)z + (d0 - nd0) = 0
      rate = z / (z - 0.5)          (z = root nearest zero)

Blind reliability (measured on our 50-image cover set + synthetic naive LSB):
  clean:   mean 0.007, max 0.048      10% embed: min 0.063      50% embed: min 0.28
  RS has a very tight clean baseline, so a 0.06 threshold detects even ~10%
  embedding with ~0% false positives - more sensitive at low rates than SPA.
  (Adaptive schemes like our own LSB++ sit at the clean baseline -> resist RS.)
"""
import numpy as np

from .base import BaseAttack

# Calibrated on the 50-image cover set (clean max 0.048); 0.06 -> ~0% FPR, catches >=~10%
RS_THRESHOLD = 0.06
_MASK = (1, 0, 0, 1)   # F+ on positions 0 and 3; -M applies F- on the same positions


class RSAnalysis(BaseAttack):
    name = "RS Analysis"

    def __init__(self, threshold: float = RS_THRESHOLD):
        self.threshold = threshold

    def analyze_blind(self, data_array: np.ndarray) -> dict:
        if data_array is None or data_array.size == 0:
            return {"error": "Empty array"}

        if data_array.ndim == 3:
            rates = [self._estimate_channel(data_array[:, :, c]) for c in range(data_array.shape[2])]
            rate = float(np.mean(rates))
        else:
            rate = self._estimate_channel(data_array)

        return {
            "estimated_embedding_rate": rate,
            "threshold": self.threshold,
            "detected": rate > self.threshold,
        }

    def _estimate_channel(self, channel: np.ndarray) -> float:
        mask = np.array(_MASK)
        neg_mask = -mask
        image = channel.astype(np.int64)
        lsb_flipped = image ^ 1   # the "fully flipped" reference end of the RS diagram

        d0 = self._regular_minus_singular(image, mask)
        d1 = self._regular_minus_singular(lsb_flipped, mask)
        nd0 = self._regular_minus_singular(image, neg_mask)
        nd1 = self._regular_minus_singular(lsb_flipped, neg_mask)

        a = 2 * (d1 + d0)
        b = nd0 - nd1 - d1 - 3 * d0
        c = d0 - nd0
        if a == 0:
            return 0.0

        disc = max(b * b - 4 * a * c, 0)
        root_plus = (-b + disc ** 0.5) / (2 * a)
        root_minus = (-b - disc ** 0.5) / (2 * a)
        z = min(root_plus, root_minus, key=abs)
        if z == 0.5:
            return 0.0
        return float(np.clip(z / (z - 0.5), 0.0, 1.0))

    def _regular_minus_singular(self, image: np.ndarray, mask: np.ndarray) -> float:
        """Fraction of Regular groups minus Singular groups for one flip mask."""
        _, width = image.shape
        usable_width = (width // 4) * 4
        groups = image[:, :usable_width].reshape(-1, 4)

        f_original = self._smoothness(groups)
        flipped = groups.copy()
        for pos, m in enumerate(mask):
            if m == 1:
                flipped[:, pos] = np.clip(groups[:, pos] ^ 1, 0, 255)              # F+
            elif m == -1:
                flipped[:, pos] = np.clip(((groups[:, pos] + 1) ^ 1) - 1, 0, 255)  # F-
        f_flipped = self._smoothness(flipped)

        n = len(groups)
        regular = np.sum(f_flipped > f_original) / n
        singular = np.sum(f_flipped < f_original) / n
        return regular - singular

    @staticmethod
    def _smoothness(groups: np.ndarray) -> np.ndarray:
        return np.sum(np.abs(np.diff(groups, axis=1)), axis=1)
