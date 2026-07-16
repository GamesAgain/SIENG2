"""
Sample Pairs Analysis (SPA) - blind LSB-replacement detector.

Reference: Dumitrescu, S., Wu, X., & Wang, Z. (2003). "Detection of LSB
Steganography via Sample Pair Analysis." IEEE Trans. Signal Processing 51(7).
Algorithm cross-checked against the reference implementation in Aletheia
(Lerch-Hostalot, https://github.com/daniellerch/aletheia) - re-implemented here
in NumPy, not copied.

How it works:
  For each adjacent sample pair (r, s) the LSB of s and the sign of (r - s) place
  the pair into trace set X or Y. LSB embedding perturbs the X/Y balance in a way
  that lets us solve for the embedding rate directly. With:
      x = |X|, y = |Y|
      k = # pairs whose top 7 bits match (the pairs LSB flips can move between sets)
      N = total pairs
  the change rate beta is the smaller root of:
      2k*beta^2 + 2(2x - N)*beta + (y - x) = 0
  and the estimated embedding rate is alpha = 2*beta, in [0, 1].
  Near full embedding the discriminant can go slightly negative (complex conjugate
  roots); their common real part -b/2a is the correct estimate, so we floor the
  discriminant at 0.

Blind reliability (measured on our 50-image cover set + synthetic naive LSB):
  clean:   mean 0.08, max 0.28
  50% embed: min 0.39   |   100% embed: min 0.98
  So a fixed 0.30 threshold cleanly separates clean from >=~40% embedding with
  ~0% false positives. Very low embedding rates (<~25%) overlap the clean band
  and are NOT reliably detectable blind - an inherent limit of SPA, not a bug.
  (Adaptive schemes like our own LSB++ sit right at the clean baseline -> resist SPA.)
"""
import numpy as np

from .base import BaseAttack

# Calibrated on the 50-image cover set (clean max 0.28, 99th pct 0.25); 0.30 -> ~0% FPR
SPA_THRESHOLD = 0.30


class SamplePairsAttack(BaseAttack):
    name = "Sample Pairs Analysis (SPA)"

    def __init__(self, threshold: float = SPA_THRESHOLD):
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
        """SPA embedding-rate estimate for one 2D channel, pooling horizontal + vertical pairs."""
        I = channel.astype(np.int64)
        msb = I & 0xFE
        x = y = k = n = 0
        pair_dirs = [
            (I[:-1, :], I[1:, :], msb[:-1, :], msb[1:, :]),   # vertical
            (I[:, :-1], I[:, 1:], msb[:, :-1], msb[:, 1:]),   # horizontal
        ]
        for r, s, msb_r, msb_s in pair_dirs:
            lsb_zero = (s & 1) == 0
            lsb_one = ~lsb_zero
            r_lt_s = r < s
            r_gt_s = r > s
            x += int(np.sum((lsb_zero & r_lt_s) | (lsb_one & r_gt_s)))
            y += int(np.sum((lsb_zero & r_gt_s) | (lsb_one & r_lt_s)))
            k += int(np.sum(msb_r == msb_s))
            n += r.size

        if k == 0:
            return 0.0

        a = 2 * k
        b = 2 * (2 * x - n)
        c = y - x
        disc = max(b * b - 4 * a * c, 0)   # complex roots near full embedding -> take real part
        root_plus = (-b + disc ** 0.5) / (2 * a)
        root_minus = (-b - disc ** 0.5) / (2 * a)
        beta = min(root_plus, root_minus)
        return float(np.clip(2 * beta, 0.0, 1.0))
