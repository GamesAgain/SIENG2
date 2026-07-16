from .compare_diff_base import CompareDiffTab
from src.core.analyzer.modules.stat.chi_square import ChiSquareAttack

# structural rate estimators (LSB replacement): show cover rate vs stego rate + the jump
RATE_METHODS = [
    ("rs_analysis", "RS Analysis (est. rate)"),
    ("spa", "Sample Pairs / SPA (est. rate)"),
    ("ws", "Weighted Stego / WS (est. rate)"),
]

# differential thresholds calibrated on cover-vs-stego pairs from the research dataset:
#   HCF-COM drop:  matching +4.7% / emd +4.3%  vs  pvd +1.4% / replacement +2.6%  -> 3% separates
#   PDH step rise: pvd +18.9% / replacement +92%  vs  matching +0.3% / emd +3.6%  -> 10% catches PVD
# (PDH also flags replacement, which RS/SPA/WS already cover - PDH's unique add is PVD.)
HCF_COM_DROP = 0.03
PDH_STEP_RISE = 0.10


class StatDiffTab(CompareDiffTab):
    def __init__(self):
        super().__init__(["METHOD", "ORIGINAL (COVER)", "SUSPICIOUS (STEGO)", "DIFFERENCE (Δ)"])

    def load_data(self, stat_diff: dict):
        self.table.setRowCount(0)
        orig_res = stat_diff.get("original", {})
        stego_res = stat_diff.get("stego", {})

        # --- Chi-Square: fractional reduction (the signal that works when a cover exists) ---
        chi_o = orig_res.get("chi_square")
        chi_s = stego_res.get("chi_square")
        if chi_o and chi_s:
            reduction = ChiSquareAttack().relative_reduction(chi_o.get("chi2", 0), chi_s.get("chi2", 0))
            color = "#EAB308" if reduction["detected"] else None
            self.add_row(["Chi-Square (χ² reduction)",
                          f"χ² = {chi_o.get('chi2', 0):.0f}", f"χ² = {chi_s.get('chi2', 0):.0f}",
                          f"{reduction['score']:+.1%} reduction"], color)

        # --- RS / SPA / WS: LSB-replacement rate jump from cover to stego ---
        for key, label in RATE_METHODS:
            o = orig_res.get(key)
            s = stego_res.get(key)
            if not o or not s:
                continue
            o_rate = o.get("estimated_embedding_rate", 0)
            s_rate = s.get("estimated_embedding_rate", 0)
            delta = s_rate - o_rate
            color = "#EAB308" if delta > 0.05 else None
            delta_str = f"+{delta * 100:.1f}%" if delta > 0.001 else "No Change"
            self.add_row([label, f"{o_rate * 100:.1f}%", f"{s_rate * 100:.1f}%", delta_str], color)

        # --- HCF-COM: center of mass drops under LSB matching / additive noise ---
        hcf_o = orig_res.get("hcf_com")
        hcf_s = stego_res.get("hcf_com")
        if hcf_o and hcf_s and hcf_o.get("hcf_com"):
            o_com = hcf_o["hcf_com"]
            s_com = hcf_s["hcf_com"]
            drop = (o_com - s_com) / o_com
            color = "#EAB308" if drop > HCF_COM_DROP else None
            self.add_row(["HCF-COM (LSB matching)", f"COM = {o_com:.2f}", f"COM = {s_com:.2f}",
                          f"{-drop * 100:+.1f}% COM"], color)

        # --- PDH: PVD raises the difference-histogram step artifact at range boundaries ---
        pdh_o = orig_res.get("pdh")
        pdh_s = stego_res.get("pdh")
        if pdh_o and pdh_s:
            o_step = pdh_o.get("pdh_step", 0)
            s_step = pdh_s.get("pdh_step", 0)
            rise = (s_step - o_step) / o_step if o_step > 0 else 0
            color = "#EAB308" if rise > PDH_STEP_RISE else None
            self.add_row(["PDH (PVD)", f"step = {o_step * 1000:.2f}e-3", f"step = {s_step * 1000:.2f}e-3",
                          f"{rise * 100:+.0f}% step"], color)
