"""
Weighted Stego-image (WS) analysis - blind LSB-replacement detector that estimates
the embedding rate. Same family as RS/SPA (LSB replacement), included as an
independent third estimate for cross-confirmation.

Reference: Fridrich, J. & Goljan, M. (2004). "On Estimation of Secret Message
Length in LSB Steganography in Spatial Domain." SPIE 5306.

How it works:
  Predict each pixel's cover value from its 4 neighbours, take the residual, and
  weight it by how flat (predictable) the local area is. The estimator
      p_hat = 2 * Σ w_i (-1)^{x_i} (x_i - x̂_i) / Σ w_i
  is near 0 for a clean image and grows with the LSB-replacement embedding rate.
  We use |p_hat| as the rate estimate (the sign is just the residual direction).

Blind reliability (measured on our 50-image cover set + controlled naive LSB):
  clean:  mean 0.06, max 0.24   |   25% embed ~0.60   |   100% embed ~0.90
  Textured covers give a wider clean spread than RS, so a 0.25 threshold keeps
  false positives ~0 but only catches ~25%+ embedding (similar sensitivity to SPA).
"""
import numpy as np
import scipy.ndimage as ndimage

from .base import BaseAttack

# Calibrated on the 50-image cover set (clean max 0.24); 0.25 -> ~0% FPR
WS_THRESHOLD = 0.25

_PRED_KERNEL = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]], dtype=np.float64) / 4.0
_MEAN_KERNEL = np.ones((3, 3), dtype=np.float64) / 9.0


class WeightedStegoAnalysis(BaseAttack):
    name = "Weighted Stego (WS)"

    def __init__(self, threshold: float = WS_THRESHOLD):
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
        pixels = channel.astype(np.float64)
        cover_pred = ndimage.convolve(pixels, _PRED_KERNEL, mode="reflect")
        residual = pixels - cover_pred
        parity = np.where(pixels.astype(np.int32) % 2 == 0, 1.0, -1.0)

        # weight = flatness: high where the local prediction residual has low variance
        local_mean = ndimage.convolve(residual, _MEAN_KERNEL, mode="reflect")
        local_var = ndimage.convolve(residual ** 2, _MEAN_KERNEL, mode="reflect") - local_mean ** 2
        weights = 1.0 / (1.0 + np.maximum(local_var, 1e-10))

        p_hat = 2.0 * np.sum(weights * parity * residual) / np.sum(weights)
        return float(np.clip(abs(p_hat), 0.0, 1.0))
