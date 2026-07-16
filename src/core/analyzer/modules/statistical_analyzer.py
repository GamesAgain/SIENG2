import numpy as np
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

        try:
            results["chi_square"] = ChiSquareAttack().analyze_blind(self.stego_array)

            # the rest need 2D+ data (images / video frames), not a 1D signal
            if self.stego_array.ndim >= 2:
                results["rs_analysis"] = RSAnalysis().analyze_blind(self.stego_array)
                results["spa"] = SamplePairsAttack().analyze_blind(self.stego_array)
                results["ws"] = WeightedStegoAnalysis().analyze_blind(self.stego_array)
                results["hcf_com"] = HCFCOMAnalysis().analyze_blind(self.stego_array)
                results["pdh"] = PDHAnalysis().analyze_blind(self.stego_array)
        except Exception as e:
            results["error"] = str(e)

        return results
