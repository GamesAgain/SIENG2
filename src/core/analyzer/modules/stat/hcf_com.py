"""
HCF-COM (Histogram Characteristic Function - Center Of Mass) - detector for the
additive-noise / LSB-matching family (LSB Matching, LSBMR, EMD), which RS/SPA miss.

Reference: Harmsen, J. & Pearlman, W. (2003). "Steganalysis of Additive Noise
Modelable Information Hiding." SPIE 5020. (COM-drop detector, Ker 2005.)

How it works:
  ±1 embedding (LSB matching etc.) is additive noise, which convolves the pixel
  histogram with the noise PMF - a low-pass filter that attenuates high-frequency
  histogram detail. In the frequency domain (the histogram's DFT = "characteristic
  function"), this pulls the center of mass DOWN:
      H[k] = DFT(histogram);  COM = Σ k·|H[k]| / Σ |H[k]|   (k = 0 .. N/2)

Blind vs differential:
  The absolute COM value varies image-to-image, so a single-file COM can't give a
  reliable blind verdict (measured: clean ~37, LSB-matching ~33 - a real drop, but
  small next to the between-image spread). detected is therefore None in blind mode;
  the reliable signal is the COM DROP relative to the cover, which Compare mode has.
"""
import numpy as np

from .base import BaseAttack


class HCFCOMAnalysis(BaseAttack):
    name = "HCF Center of Mass"

    def analyze_blind(self, data_array: np.ndarray) -> dict:
        if data_array is None or data_array.size == 0:
            return {"error": "Empty array"}

        if data_array.ndim == 3:
            coms = [self._com(data_array[:, :, c]) for c in range(data_array.shape[2])]
            com = float(np.mean(coms))
        else:
            com = self._com(data_array)

        # blind: report the value only - the verdict (COM drop vs cover) lives in Compare mode
        return {"hcf_com": com, "detected": None}

    @staticmethod
    def _com(channel: np.ndarray) -> float:
        hist, _ = np.histogram(channel.ravel(), bins=256, range=(0, 256))
        half = 256 // 2 + 1                       # |H[k]| is symmetric; use the first half
        mag = np.abs(np.fft.fft(hist.astype(np.float64)))[:half]
        denom = float(np.sum(mag))
        if denom <= 0:
            return 0.0
        return float(np.sum(np.arange(half) * mag) / denom)
