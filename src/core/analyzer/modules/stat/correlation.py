import numpy as np
from .base import BaseAttack

class CorrelationAnalysis(BaseAttack):
    name = "Correlation Analysis"

    def analyze_blind(self, data_array: np.ndarray) -> dict:
        """
        Calculate lag-1 auto-correlation, same channel to same channel only.
        The previous version flattened an (H,W,3) image in C-order
        (R,G,B,R,G,B,...) before taking the lag-1 pair, so most pairs compared
        two DIFFERENT color channels at the same pixel (e.g. R next to G)
        instead of the same channel's spatial neighbor - not a meaningful
        spatial correlation measurement. Each channel is now flattened and
        correlated separately, then averaged. 1D/2D input (e.g. WAV's
        already-flattened LSB samples) is unaffected, same as before.
        """
        if data_array is None or data_array.size < 2:
            return {"error": "Array too small", "correlation": 0.0}

        if data_array.ndim == 3:
            channel_corrs = [self._lag1_correlation(data_array[:, :, c]) for c in range(data_array.shape[2])]
            channel_corrs = [c for c in channel_corrs if c is not None]
            correlation = float(np.mean(channel_corrs)) if channel_corrs else 0.0
        else:
            correlation = self._lag1_correlation(data_array) or 0.0

        return {
            "correlation": correlation,
            "detected": correlation < 0.1
        }

    @staticmethod
    def _lag1_correlation(arr: np.ndarray):
        flat = arr.ravel().astype(np.float64)
        if flat.size < 2:
            return None
        x = flat[:-1]
        y = flat[1:]
        if np.std(x) == 0 or np.std(y) == 0:
            return 0.0
        corr = np.corrcoef(x, y)[0, 1]
        return None if np.isnan(corr) else float(corr)
