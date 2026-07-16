import numpy as np
from src.core.analyzer.modules.stat.chi_square import ChiSquareAttack
from src.core.analyzer.modules.stat.rs_analysis import RSAnalysis
from src.core.analyzer.modules.stat.bit_balance import BitBalanceTest
from src.core.analyzer.modules.stat.correlation import CorrelationAnalysis
from src.core.analyzer.modules.stat.sample_pairs import SamplePairsAttack

class StatisticalAnalyzer:
    def __init__(self, stego_array: np.ndarray):
        self.stego_array = stego_array

    def analyze(self) -> dict:
        results = {}
        if self.stego_array is None or self.stego_array.size == 0:
            return {"error": "No data provided for statistical analysis."}
             
        try:
            # 1D and 2D Data Tests
            chi_analyzer = ChiSquareAttack()
            results["chi_square"] = chi_analyzer.analyze_blind(self.stego_array)
            
            bit_analyzer = BitBalanceTest()
            results["bit_balance"] = bit_analyzer.analyze_blind(self.stego_array)
            
            # 2D Data Tests (Images / Video Frames)
            if self.stego_array.ndim >= 2:
                rs_analyzer = RSAnalysis()
                results["rs_analysis"] = rs_analyzer.analyze_blind(self.stego_array)
                
                spa_analyzer = SamplePairsAttack()
                results["spa"] = spa_analyzer.analyze_blind(self.stego_array)
                
                corr_analyzer = CorrelationAnalysis()
                results["correlation"] = corr_analyzer.analyze_blind(self.stego_array)
                
        except Exception as e:
            results["error"] = str(e)
            
        return results
