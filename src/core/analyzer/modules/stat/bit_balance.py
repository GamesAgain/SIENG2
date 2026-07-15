import numpy as np
from .base import BaseAttack

class BitBalanceTest(BaseAttack):
    name = "Bit-Balance Test"

    def analyze_blind(self, data_array: np.ndarray) -> dict:
        """
        Calculate the percentage of 0s and 1s in the binary representation
        of the data array.
        """
        if data_array is None or data_array.size == 0:
            return {"error": "Empty array"}
            
        flat_data = data_array.ravel()
        if flat_data.dtype != np.uint8:
            flat_data = flat_data.astype(np.uint8)
            
        bits = np.unpackbits(flat_data)
        total_bits = len(bits)
        if total_bits == 0:
            return {"zero_ratio": 0.0, "one_ratio": 0.0, "detected": False}
            
        ones = int(np.sum(bits))
        zeros = total_bits - ones
        
        zero_ratio = (zeros / total_bits) * 100.0
        one_ratio = (ones / total_bits) * 100.0
        
        # If the ratio is perfectly or almost perfectly 50/50, it might be encrypted/randomized
        detected = abs(zero_ratio - 50.0) < 0.1
        
        return {
            "zero_ratio": float(zero_ratio),
            "one_ratio": float(one_ratio),
            "detected": detected
        }
