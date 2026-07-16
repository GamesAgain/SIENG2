import numpy as np
from .base import BaseAttack

class CorrelationAnalysis(BaseAttack):
    name = "Correlation Analysis"

    def analyze_blind(self, data_array: np.ndarray) -> dict:
        """
        Calculate lag-1 auto-correlation of the data array.
        Natural data has high correlation, encrypted/embedded data may have lower correlation.
        """
        if data_array is None or data_array.size < 2:
            return {"error": "Array too small", "correlation": 0.0}
            
        flat_data = data_array.ravel().astype(np.float64)
        
        x = flat_data[:-1]
        y = flat_data[1:]
        
        if np.std(x) == 0 or np.std(y) == 0:
            correlation = 0.0
        else:
            corr = np.corrcoef(x, y)[0, 1]
            correlation = 0.0 if np.isnan(corr) else float(corr)
            
        return {
            "correlation": correlation,
            # Thresholds vary widely depending on data type, so we don't strictly set 'detected'
            "detected": correlation < 0.1 
        }
