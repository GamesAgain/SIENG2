from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QScrollArea, QWidget, QProgressBar,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView
)
from src.core.analyzer.modules.stat.chi_square import ChiSquareAttack

RED = "#EF4444"
GREEN = "#10B981"
GRAY = "#94A3B8"
BLUE = "#38BDF8"

# structural rate estimators (LSB replacement family)
RATE_METHODS = [
    ("rs_analysis", "RS Analysis"),
    ("spa", "Sample Pairs (SPA)"),
    ("ws", "Weighted Stego (WS)"),
]

# Differential thresholds calibrated on cover-vs-stego pairs from the research dataset. Having the
# cover baseline is what makes HCF-COM / PDH reliable here (they are too noisy to use blind):
#   RS rate jump:  the authoritative LSB-replacement signal (tight clean baseline)
#   HCF-COM drop:  matching +4.7% / emd +4.3%  vs  pvd +1.4% / replacement +2.6%  -> 3% separates
#   PDH step rise: pvd +18.9%                   vs  matching +0.3% / emd +3.6%     -> 10% catches PVD
RATE_JUMP = 0.05        # a rate estimator's cover->stego rise that counts as "moved"
RS_REPLACEMENT = 0.10   # RS jump that names the file LSB replacement
HCF_COM_DROP = 0.03
PDH_STEP_RISE = 0.10


class StatDiffTab(QFrame):
    """Cover-vs-stego statistical comparison. Unlike the blind Analyzer tab, having the original
    lets the noisy additive-noise / PVD detectors work - so this tab groups the detectors by the
    technique they reveal, names the likely technique, and marks the decisive row, instead of
    dumping a flat table of numbers the user has to interpret."""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("transparentScroll")

        content = QWidget()
        content.setObjectName("transparentScrollContent")
        main = QVBoxLayout(content)
        main.setContentsMargins(10, 10, 10, 10)
        main.setSpacing(10)

        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title = QLabel("Statistical Comparison")
        title.setObjectName("cardTitle")
        layout.addWidget(title)

        self.verdict_banner = QLabel("Run a comparison to analyze the two files.")
        self.verdict_banner.setWordWrap(True)
        self._style_banner(GRAY)
        layout.addWidget(self.verdict_banner)

        self.table = QTableWidget(0, 5)
        self.table.setObjectName("darkTable")
        self.table.setHorizontalHeaderLabels(
            ["Method", "Original (Cover)", "Suspicious (Stego)", "Change", "Verdict"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

        note = QLabel(
            "Grouped by the technique each detector reveals. RS/SPA/WS catch LSB replacement; "
            "Chi-Square and HCF-COM catch LSB matching / additive noise; PDH catches PVD. "
            "The decisive row for the verdict is highlighted.")
        note.setObjectName("hintLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        main.addWidget(card)
        main.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ---------- rendering helpers ----------
    def _style_banner(self, color: str):
        c = QColor(color)
        self.verdict_banner.setStyleSheet(
            f"padding: 10px 12px; border-radius: 6px; "
            f"background: rgba({c.red()},{c.green()},{c.blue()},0.12); color: {color};")

    def _add_group(self, title: str):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 26)
        item = QTableWidgetItem(title.upper())
        item.setForeground(QBrush(QColor(GRAY)))
        f = item.font()
        f.setBold(True)
        f.setPointSize(max(f.pointSize() - 1, 7))
        item.setFont(f)
        item.setBackground(QBrush(QColor("#2A2A2A")))
        self.table.setItem(row, 0, item)
        for col in range(1, 5):
            filler = QTableWidgetItem("")
            filler.setBackground(QBrush(QColor("#2A2A2A")))
            self.table.setItem(row, col, filler)
        self.table.setSpan(row, 0, 1, 5)

    def _add_metric(self, method, cover, stego, change, suspicious, decisive=False, bar_rate=None):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 34)
        color = RED if suspicious else None

        name = QTableWidgetItem(("▶  " if decisive else "     ") + method)
        if decisive:
            name.setForeground(QBrush(QColor(RED)))
        self.table.setItem(row, 0, name)

        self.table.setItem(row, 1, QTableWidgetItem(cover))

        if bar_rate is not None:
            self.table.setCellWidget(row, 2, self._rate_bar(bar_rate, suspicious))
        else:
            self.table.setItem(row, 2, QTableWidgetItem(stego))

        change_item = QTableWidgetItem(change)
        if color:
            change_item.setForeground(QBrush(QColor(color)))
        self.table.setItem(row, 3, change_item)

        v = QTableWidgetItem("Suspicious" if suspicious else "Clean")
        v.setForeground(QBrush(QColor(RED if suspicious else GREEN)))
        self.table.setItem(row, 4, v)

    @staticmethod
    def _rate_bar(rate: float, suspicious: bool) -> QProgressBar:
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(round(rate * 100)))
        bar.setFormat(f"{rate * 100:.1f}%")
        bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chunk = RED if suspicious else BLUE
        # square corners (no radius) so the bar sits flush with the table cell
        bar.setStyleSheet(
            "QProgressBar { background: rgba(148,163,184,0.15); border: none; border-radius: 0; color: #E2E8F0; }"
            f"QProgressBar::chunk {{ background: {chunk}; border-radius: 0; }}")
        return bar

    def _fit_table(self):
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        h = self.table.horizontalHeader().sizeHint().height() + self.table.frameWidth() * 2 + 2
        for r in range(self.table.rowCount()):
            h += self.table.rowHeight(r)
        self.table.setFixedHeight(h)

    # ---------- data ----------
    def load_data(self, stat_diff: dict):
        self.table.clearSpans()
        self.table.setRowCount(0)
        orig = stat_diff.get("original", {})
        stego = stat_diff.get("stego", {})

        if not orig or not stego:
            self._style_banner(GRAY)
            self.verdict_banner.setText("Run a comparison to analyze the two files.")
            self._fit_table()
            return

        # ----- Spatial LSB (replacement): RS / SPA / WS -----
        rs_jump = 0.0
        self._add_group("Spatial LSB — replacement (RS / SPA / WS)")
        for key, label in RATE_METHODS:
            o, s = orig.get(key), stego.get(key)
            if not o or not s:
                continue
            o_rate = o.get("estimated_embedding_rate", 0.0)
            s_rate = s.get("estimated_embedding_rate", 0.0)
            delta = s_rate - o_rate
            susp = delta > RATE_JUMP
            if key == "rs_analysis":
                rs_jump = delta
            change = f"+{delta * 100:.1f}%" if delta > 0.001 else "no change"
            self._add_metric(label, f"{o_rate * 100:.1f}%", None, change, susp, bar_rate=s_rate)

        # ----- Additive noise (LSB matching / EMD): Chi-Square + HCF-COM -----
        self._add_group("Additive noise — LSB matching / EMD (Chi-Square / HCF-COM)")
        hcf_drop = 0.0
        chi_o, chi_s = orig.get("chi_square"), stego.get("chi_square")
        if chi_o and chi_s:
            red = ChiSquareAttack().relative_reduction(chi_o.get("chi2", 0), chi_s.get("chi2", 0))
            self._add_metric("Chi-Square (χ² reduction)",
                             f"χ² = {chi_o.get('chi2', 0):.0f}",
                             f"χ² = {chi_s.get('chi2', 0):.0f}",
                             f"{red['score']:+.1%}", bool(red["detected"]))
        hc_o, hc_s = orig.get("hcf_com"), stego.get("hcf_com")
        if hc_o and hc_s and hc_o.get("hcf_com"):
            o_com, s_com = hc_o["hcf_com"], hc_s["hcf_com"]
            hcf_drop = (o_com - s_com) / o_com
            susp = hcf_drop > HCF_COM_DROP
            self._add_metric("HCF-COM (center of mass)", f"{o_com:.2f}", f"{s_com:.2f}",
                             f"{-hcf_drop * 100:+.1f}%", susp)

        # ----- PVD: PDH step -----
        self._add_group("PVD — pixel-value differencing (PDH)")
        pdh_rise = 0.0
        pd_o, pd_s = orig.get("pdh"), stego.get("pdh")
        if pd_o and pd_s:
            o_step, s_step = pd_o.get("pdh_step", 0.0), pd_s.get("pdh_step", 0.0)
            pdh_rise = (s_step - o_step) / o_step if o_step > 0 else 0.0
            susp = pdh_rise > PDH_STEP_RISE
            self._add_metric("PDH (difference-histogram step)",
                             f"{o_step * 1000:.2f}e-3", f"{s_step * 1000:.2f}e-3",
                             f"{pdh_rise * 100:+.0f}%", susp)

        self._verdict_and_highlight(rs_jump, hcf_drop, pdh_rise, stego)
        self._fit_table()

    def _verdict_and_highlight(self, rs_jump, hcf_drop, pdh_rise, stego):
        """Priority cascade RS > HCF-COM > PDH (each claims only if the reliabler ones are silent),
        then mark the decisive detector row with a caret + red name."""
        decisive_row_key = None
        if rs_jump > RS_REPLACEMENT:
            rs_rate = stego.get("rs_analysis", {}).get("estimated_embedding_rate", 0) * 100
            self.verdict_banner.setText(
                f"<b>LSB replacement detected</b> — estimated embedding ≈ {rs_rate:.0f}% of capacity "
                f"(RS/SPA/WS rate rose sharply from cover to stego).")
            self._style_banner(RED)
            decisive_row_key = "RS Analysis"
        elif hcf_drop > HCF_COM_DROP:
            self.verdict_banner.setText(
                "<b>LSB matching / additive-noise embedding detected</b> — the histogram's "
                "center of mass dropped, the signature RS/SPA/WS cannot see.")
            self._style_banner(RED)
            decisive_row_key = "HCF-COM (center of mass)"
        elif pdh_rise > PDH_STEP_RISE:
            self.verdict_banner.setText(
                "<b>PVD embedding detected</b> — the difference-histogram step artifact rose, "
                "the signature only visible against the original.")
            self._style_banner(RED)
            decisive_row_key = "PDH (difference-histogram step)"
        else:
            self.verdict_banner.setText(
                "<b>No statistical evidence of embedding</b> — every detector stayed within its "
                "cover-to-stego noise margin.")
            self._style_banner(GREEN)

        if decisive_row_key:
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 0)
                if item and item.text().strip() == decisive_row_key:
                    item.setText("▶  " + decisive_row_key)
                    item.setForeground(QBrush(QColor(RED)))
                    break
