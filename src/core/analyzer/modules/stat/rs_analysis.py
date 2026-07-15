"""
RS Analysis (Fridrich, Goljan & Du, 2001)
-----------------------------------------
Divides the image into groups of `group_size` consecutive pixels (horizontal).
For each group, apply two complementary flipping functions:
  F+ (positive): XOR with 1  → swaps pairs (0↔1, 2↔3, 4↔5 …)
  F- (negative): shifts pair → swaps pairs (1↔2, 3↔4, 5↔6 …)

Smoothness discriminant:  f(g) = Σ |g[i+1] - g[i]|

Classify each group relative to the original:
  Regular (R)  : f(F(g)) > f(g)
  Singular (S) : f(F(g)) < f(g)
  Unusable (U) : f(F(g)) = f(g)

In a natural image:  R+ ≈ R-  and  S+ ≈ S-
After embedding:     R+ > R-  and  S+ < S-

Asymmetry score = (R+ − R-) + (S- − S+)   [positive when embedded]

Mask used: [0, 1, 0, 1]  — flip pixels at positions 1 and 3 of each group.
"""
import numpy as np

from .base import BaseAttack

_MASK = np.array([0, 1, 0, 1], dtype=bool)   # which positions get flipped
_GROUP = 4                                     # pixels per group


class RSAnalysis(BaseAttack):
    name = "RS Analysis"

    def __init__(self, threshold: float = 0.02, group_size: int = _GROUP):
        self.threshold = threshold
        self.group_size = group_size

    def analyze_blind(self, data_array: np.ndarray) -> dict:
        stego_stats = self._rs(data_array)
        score = stego_stats["asymmetry"]
        detected = abs(score) > self.threshold
        return {
            "stats": stego_stats,
            "asymmetry": score,
            "detected": detected
        }



    # ------------------------------------------------------------------

    def _rs(self, arr: np.ndarray) -> dict:
        if arr.ndim == 3 and arr.shape[2] >= 3:
            # Convert RGB to Grayscale
            arr = np.dot(arr[...,:3], [0.2989, 0.5870, 0.1140]).astype(np.uint8)
        elif arr.ndim == 1:
            arr = arr.reshape(1, -1).astype(np.uint8)
        else:
            arr = arr.astype(np.uint8)
            
        h, w = arr.shape
        gs = self.group_size

        # Trim width to an exact multiple of group_size
        w_trim = (w // gs) * gs
        groups = arr[:, :w_trim].reshape(-1, gs).astype(np.int32)  # (N, gs)

        f0 = self._disc(groups)

        g_pos = self._flip_pos(groups)
        g_neg = self._flip_neg(groups)

        f_pos = self._disc(g_pos)
        f_neg = self._disc(g_neg)

        n = len(groups)
        R_p = np.sum(f_pos > f0) / n
        S_p = np.sum(f_pos < f0) / n
        R_n = np.sum(f_neg > f0) / n
        S_n = np.sum(f_neg < f0) / n

        asymmetry = (R_p - R_n) + (S_n - S_p)

        return {
            "R_pos": float(R_p),
            "S_pos": float(S_p),
            "R_neg": float(R_n),
            "S_neg": float(S_n),
            "asymmetry": float(asymmetry),
        }

    @staticmethod
    def _disc(groups: np.ndarray) -> np.ndarray:
        """Vectorised smoothness: sum of absolute first-differences per group."""
        return np.sum(np.abs(np.diff(groups, axis=1)), axis=1)

    @staticmethod
    def _flip_pos(groups: np.ndarray) -> np.ndarray:
        """F+: XOR 1 on masked positions → swaps (0↔1), (2↔3), (4↔5) …"""
        g = groups.copy()
        g[:, _MASK] ^= 1
        return g

    @staticmethod
    def _flip_neg(groups: np.ndarray) -> np.ndarray:
        """F-: ((x-1) XOR 1)+1 on masked positions → swaps (1↔2), (3↔4) …
           F-(0) = 0  (boundary: can't go to -1)."""
        g = groups.copy()
        col = g[:, _MASK]
        flipped = col.copy()
        pos = col > 0
        flipped[pos] = ((col[pos] - 1) ^ 1) + 1
        g[:, _MASK] = flipped
        return g
