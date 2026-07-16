"""
Sample Pairs Analysis (SPA)
Reference: Dumitrescu, S., Wu, X., & Wang, Z. (2003).
           Detection of LSB Steganography via Sample Pair Analysis.
           IEEE Transactions on Signal Processing, 51(7), 1995–2007.

Background:
  For consecutive pixel channels (x_i, x_{i+1}), define "close pairs" as those
  where |x_i - x_{i+1}| == 1.  Split by parity of the smaller value:

    P = #{close pairs where min(x_i, x_{i+1}) is even}
        covers integer boundary pairs {0,1}, {2,3}, {4,5}, …, {254,255}
    Q = #{close pairs where min(x_i, x_{i+1}) is odd}
        covers integer boundary pairs {1,2}, {3,4}, {5,6}, …, {253,254}

  The Dumitrescu 2003 paper's theory (for i.i.d. signals) predicts P → Q after
  LSBR embedding.  In practice, spatially correlated natural images behave
  differently via adjacent-pixel scanning:

  LSBR creates a directional effect:
    - Equal pairs (2k, 2k) split into close P-type pairs (2k, 2k+1) / (2k+1, 2k)
    - Q-type pairs (2k+1, 2k+2) are mostly destroyed (diff jumps to 2-3)
    - Net effect: P INCREASES, Q DECREASES → |P-Q| imbalance GROWS.

  LSBM / LSBMR (symmetric ±1):
    - Minimal structural disruption; |P-Q| grows only slightly.

  LSB++ (multi-bit, adaptive):
    - 2-3 bit embedding causes large value jumps, destroying many close pairs
      and creating new P-type pairs → |P-Q| grows moderately.

Detection strategy (differential, cover + stego available):
  Measures the growth in |P-Q| imbalance after embedding:

    score = (|P_s - Q_s| - |P_c - Q_c|) / (P_c + Q_c)

  Positive score → imbalance grew → embedding occurred.
  Threshold default = 0.01.

  Additional metric — close_pair_ratio = (P_s+Q_s) / (P_c+Q_c):
    < 1: multi-bit embedding destroyed some close pairs
    > 1: embedding created new close pairs (often single-bit methods)

  Both horizontal and vertical adjacent pairs are counted (all 3 RGB channels).
"""
import numpy as np

from .base import BaseAttack


class SamplePairsAttack(BaseAttack):
    name = "Sample Pairs Analysis (SPA)"

    def __init__(self, threshold: float = 0.05):
        # Estimated embedding rate threshold for detection
        self.threshold = threshold

    def analyze_blind(self, data_array: np.ndarray) -> dict:
        """
        Estimate LSB embedding rate using Sample Pair Analysis (Dumitrescu 2003).
        """
        if data_array is None or data_array.size == 0:
            return {"error": "Empty array"}
            
        arr = data_array.astype(np.int32)
        P_t = 0
        Q_t = 0
        W_t = 0
        Z_t = 0
        
        # Horizontal pairs
        a_h = arr[:, :-1, :] if arr.ndim == 3 else arr[:, :-1]
        b_h = arr[:, 1:, :] if arr.ndim == 3 else arr[:, 1:]
        p_h, q_h, w_h, z_h = self._classify_pairs(a_h, b_h)
        P_t += p_h; Q_t += q_h; W_t += w_h; Z_t += z_h
        
        # Vertical pairs
        if arr.ndim == 3:
            a_v = arr[:-1, :, :]
            b_v = arr[1:, :, :]
        else:
            a_v = arr[:-1, :]
            b_v = arr[1:, :]
        p_v, q_v, w_v, z_v = self._classify_pairs(a_v, b_v)
        P_t += p_v; Q_t += q_v; W_t += w_v; Z_t += z_v
        
        # Total number of adjacent pairs
        total_pairs = (arr.shape[0] * (arr.shape[1] - 1)) + ((arr.shape[0] - 1) * arr.shape[1])
        if arr.ndim == 3:
            total_pairs *= arr.shape[2]
            
        # Dumitrescu's Quadratic Equation: a*p^2 + b*p + c = 0
        a = 0.5 * (W_t + Z_t)
        b = 2 * P_t - total_pairs
        c = Q_t - P_t
        
        estimated_rate = 0.0
        if a != 0:
            disc = (b ** 2) - (4 * a * c)
            if disc >= 0:
                p1 = (-b + np.sqrt(disc)) / (2 * a)
                p2 = (-b - np.sqrt(disc)) / (2 * a)
                
                # We usually want the root with the smaller absolute value
                estimated_rate = float(p1 if abs(p1) < abs(p2) else p2)
                
        # Normalize in case of slight overshoot due to noise
        if estimated_rate < 0:
            estimated_rate = 0.0
        elif estimated_rate > 1:
            estimated_rate = 1.0
            
        detected = estimated_rate > self.threshold
        
        return {
            "estimated_embedding_rate": estimated_rate,
            "detected": detected,
            "P": P_t,
            "Q": Q_t,
            "W": W_t,
            "Z": Z_t
        }

    def _classify_pairs(self, a: np.ndarray, b: np.ndarray) -> tuple[int, int, int, int]:
        close = np.abs(a - b) == 1
        same = (a == b)
        min_val = np.minimum(a, b)
        
        P = int(np.sum(close & ((min_val & 1) == 0)))
        Q = int(np.sum(close & ((min_val & 1) == 1)))
        W = int(np.sum(same & ((a & 1) == 0)))
        Z = int(np.sum(same & ((a & 1) == 1)))
        
        return P, Q, W, Z
