import numpy as np
from concurrent.futures import ThreadPoolExecutor
from src.core.analyzer.modules.stat.chi_square import ChiSquareAttack
from src.core.analyzer.modules.stat.rs_analysis import RSAnalysis
from src.core.analyzer.modules.stat.sample_pairs import SamplePairsAttack
from src.core.analyzer.modules.stat.ws import WeightedStegoAnalysis
from src.core.analyzer.modules.stat.hcf_com import HCFCOMAnalysis
from src.core.analyzer.modules.stat.pdh import PDHAnalysis


class StatisticalAnalyzer:
    """
    Blind spatial-domain steganalysis. Runs a panel of detectors that between them
    cover the main spatial hiding families:

      LSB Replacement  -> RS / SPA / WS  (blind, calibrated embedding-rate estimate)
      LSB Matching-family (matching/LSBMR/EMD) -> HCF-COM  (COM drop vs cover)
      PVD              -> PDH  (difference-histogram roughness change vs cover)
      Chi-Square       -> raw stat only blind (real verdict in Compare mode)

    HCF-COM and PDH are differential: their absolute value can't give a reliable
    blind verdict, so they report their metric with detected=None here and the
    verdict is produced in Compare mode (cover vs stego). RS/SPA/WS give a blind
    verdict against a calibrated threshold.

    Removed the former Bit-Balance and Correlation "detectors": neither is a real
    steganalysis method (both had ~zero power to separate clean from stego).
    """

    def __init__(self, stego_array: np.ndarray):
        self.stego_array = stego_array

    def analyze(self) -> dict:
        results = {}
        if self.stego_array is None or self.stego_array.size == 0:
            return {"error": "No data provided for statistical analysis."}

        detectors = {"chi_square": ChiSquareAttack()}
        # the rest need 2D+ data (images / video frames), not a 1D signal
        if self.stego_array.ndim >= 2:
            detectors.update({
                "rs_analysis": RSAnalysis(), "spa": SamplePairsAttack(),
                "ws": WeightedStegoAnalysis(), "hcf_com": HCFCOMAnalysis(), "pdh": PDHAnalysis(),
            })

        # The detectors are independent and read-only over the same array; they're heavy NumPy/
        # SciPy calls that release the GIL, so a thread pool overlaps them (RS+WS alone are most of
        # the time). Each is isolated so one failing doesn't lose the others' results.
        try:
            with ThreadPoolExecutor(max_workers=len(detectors)) as pool:
                futures = {name: pool.submit(det.analyze_blind, self.stego_array)
                           for name, det in detectors.items()}
                for name, future in futures.items():
                    try:
                        results[name] = future.result()
                    except Exception as e:
                        results[name] = {"error": str(e)}
        except Exception as e:
            results["error"] = str(e)

        return results
