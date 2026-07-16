import numpy as np
from .base import BaseAttack

class BitBalanceTest(BaseAttack):
    name = "Bit-Balance Test"

    def analyze_blind(self, data_array: np.ndarray) -> dict:
        """
        Calculate the percentage of 0s and 1s in the LSB plane specifically -
        LSB steganography only ever touches bit 0 of each byte, so that's the
        only bit worth testing here. The previous version used
        np.unpackbits() on the raw bytes, which tests all 8 bits of every
        pixel (including the high-order bits that carry the actual image
        content, not just noise) - not a meaningful LSB steganalysis signal.
        """
        if data_array is None or data_array.size == 0:
            return {"error": "Empty array"}

        flat_data = data_array.ravel()
        if flat_data.dtype != np.uint8:
            flat_data = flat_data.astype(np.uint8)

        lsb_bits = flat_data & 1
        total_bits = len(lsb_bits)
        if total_bits == 0:
            return {"zero_ratio": 0.0, "one_ratio": 0.0, "detected": False}

        ones = int(np.sum(lsb_bits))
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
