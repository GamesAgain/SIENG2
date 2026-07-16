from .compare_diff_base import CompareDiffTab
from src.core.analyzer.modules.stat.chi_square import ChiSquareAttack

class StatDiffTab(CompareDiffTab):
    def __init__(self):
        super().__init__(["METHOD", "ORIGINAL (COVER)", "SUSPICIOUS (STEGO)", "DIFFERENCE (Δ)"])
        
    def load_data(self, stat_diff: dict):
        self.table.setRowCount(0)
        
        orig_res = stat_diff.get("original", {})
        stego_res = stat_diff.get("stego", {})
        
        methods = ["chi_square", "rs_analysis", "bit_balance", "spa", "correlation"]
        labels = {
            "chi_square": "Chi-Square Attack (χ² reduction)",
            "rs_analysis": "RS Analysis (Asymmetry)",
            "bit_balance": "Bit Balance Test (Zero Ratio)",
            "spa": "Sample Pairs Analysis (Est. Rate)",
            "correlation": "Correlation Analysis"
        }
        
        for method in methods:
            if method not in orig_res and method not in stego_res:
                continue
                
            orig_data = orig_res.get(method, {})
            stego_data = stego_res.get(method, {})
            
            orig_str = "-"
            stego_str = "-"
            delta_str = "-"
            color = None
            
            if method == "chi_square":
                # p_value saturates to ~0 for virtually any real image regardless of embedding
                # (see chi_square.py) - the fractional chi2 reduction is the signal that
                # actually works here, and only Compare mode has the cover needed to compute it
                if orig_data:
                    orig_str = f"χ² = {orig_data.get('chi2', 0):.2f}"
                if stego_data:
                    stego_str = f"χ² = {stego_data.get('chi2', 0):.2f}"

                if orig_data and stego_data:
                    reduction = ChiSquareAttack().relative_reduction(orig_data.get('chi2', 0), stego_data.get('chi2', 0))
                    delta_str = f"{reduction['score']:+.1%} reduction"
                    if reduction['detected']: color = "#EAB308"
                    
            elif method == "rs_analysis":
                orig_val = orig_data.get('asymmetry', 0)
                stego_val = stego_data.get('asymmetry', 0)
                
                if orig_data:
                    orig_str = f"Asym = {orig_val:.4f}"
                if stego_data:
                    stego_str = f"Asym = {stego_val:.4f}"
                    
                if orig_data and stego_data:
                    delta = abs(stego_val) - abs(orig_val)
                    delta_str = f"{delta:+.4f}"
                    if abs(delta) > 0.0001: color = "#EAB308"
                    
            elif method == "bit_balance":
                orig_val = orig_data.get('zero_ratio', 0)
                stego_val = stego_data.get('zero_ratio', 0)
                
                if orig_data:
                    orig_str = f"0: {orig_val:.2f}%, 1: {orig_data.get('one_ratio', 0):.2f}%"
                if stego_data:
                    stego_str = f"0: {stego_val:.2f}%, 1: {stego_data.get('one_ratio', 0):.2f}%"
                    
                if orig_data and stego_data:
                    delta = stego_val - orig_val
                    delta_str = f"{delta:+.2f}%"
                    if abs(delta) > 0.01: color = "#EAB308"
                    
            elif method == "spa":
                orig_val = orig_data.get('estimated_embedding_rate', 0)
                stego_val = stego_data.get('estimated_embedding_rate', 0)
                
                if orig_data:
                    orig_str = f"Rate = {orig_val:.4f}"
                if stego_data:
                    stego_str = f"Rate = {stego_val:.4f}"
                    
                if orig_data and stego_data:
                    delta = stego_val - orig_val
                    delta_str = f"{delta:+.4f}"
                    if abs(delta) > 0.0001: color = "#EAB308"
                    
            elif method == "correlation":
                orig_val = orig_data.get('correlation', 0)
                stego_val = stego_data.get('correlation', 0)
                
                if orig_data:
                    orig_str = f"Corr = {orig_val:.4f}"
                if stego_data:
                    stego_str = f"Corr = {stego_val:.4f}"
                    
                if orig_data and stego_data:
                    delta = stego_val - orig_val
                    delta_str = f"{delta:+.4f}"
                    if abs(delta) > 0.0001: color = "#EAB308"
            
            if delta_str == "-":
                pass
            elif delta_str.startswith("+0.0000") or delta_str.startswith("-0.0000") or delta_str == "+0.00%":
                delta_str = "No Change"
                color = None
                    
            self.add_row([labels.get(method, method), orig_str, stego_str, delta_str], color)


