"""
PDH (Pixel Difference Histogram) - detector for PVD (Pixel-Value Differencing)
steganography, which RS/SPA/WS/HCF-COM all miss.

Reference: Zhang, X. & Wang, S. (2004). "Vulnerability of Pixel-Value Differencing
Steganography to Histogram Analysis and Modification for Enhanced Security."
Pattern Recognition Letters 25(3).

How it works:
  PVD hides data in the DIFFERENCE of non-overlapping pixel pairs, re-quantizing
  each difference to L + b within its range. A random payload flattens the fine
  structure of the difference histogram inside each range and leaves step artifacts
  at the range boundaries. We measure the histogram's roughness (mean |2nd-order
  difference|) plus the step artifact at the PVD range boundaries.

Blind vs differential:
  Embedding of any kind changes the difference-histogram roughness, so a single
  absolute roughness value doesn't cleanly isolate PVD blind (measured: clean and
  several stego types all shift). detected is None in blind mode; the reliable
  signal is the roughness CHANGE (and the boundary step) relative to the cover,
  which Compare mode has.
"""
import numpy as np

from .base import BaseAttack

# Wu & Tsai PVD range boundaries - where PVD leaves its zig-zag step artifacts
_PVD_BOUNDARIES = (8, 16, 32, 64, 128)


class PDHAnalysis(BaseAttack):
    name = "Pixel Difference Histogram"

    def analyze_blind(self, data_array: np.ndarray) -> dict:
        if data_array is None or data_array.size == 0:
            return {"error": "Empty array"}

        # PVD works on grayscale-style pixel pairs; use luminance-ish mean of channels
        gray = data_array.mean(axis=2).astype(np.int32) if data_array.ndim == 3 else data_array.astype(np.int32)

        # non-overlapping horizontal pairs (matches how PVD pairs pixels)
        h, w = gray.shape
        w_even = w - (w % 2)
        left = gray[:, 0:w_even:2].ravel()
        right = gray[:, 1:w_even:2].ravel()
        diff = np.abs(left - right)

        hist, _ = np.histogram(diff, bins=256, range=(0, 256))
        total = hist.sum()
        if total == 0:
            return {"pdh_roughness": 0.0, "pdh_step": 0.0, "detected": None}
        hist_norm = hist.astype(np.float64) / total

        second_diff = hist_norm[:-2] - 2 * hist_norm[1:-1] + hist_norm[2:]
        roughness = float(np.mean(np.abs(second_diff)))

        steps = [abs(2 * hist_norm[d] - hist_norm[d - 1] - hist_norm[d + 1])
                 for d in _PVD_BOUNDARIES if 1 <= d < 255]
        step = float(np.mean(steps)) if steps else 0.0

        # blind: report values only - the verdict (roughness change vs cover) is in Compare mode
        return {"pdh_roughness": roughness, "pdh_step": step, "detected": None}
