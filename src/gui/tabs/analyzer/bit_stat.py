from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QScrollArea, QWidget, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QProgressBar
)
from PyQt6.QtGui import QColor, QBrush, QIcon, QTransform

from src.gui.tabs.analyzer.zsteg_card import ZstegCard
from src.gui.components.gui_utils import create_icon_pixmap

ICON_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "svg"

# zsteg only supports these formats - the LSB Extraction card is hidden for others
ZSTEG_FORMATS = {".png", ".bmp"}

RED = "#EF4444"
GREEN = "#10B981"
GRAY = "#94A3B8"
BLUE = "#38BDF8"

# structural rate-estimating detectors (LSB replacement family), shown as rate bars
RATE_DETECTORS = [
    ("rs_analysis", "RS Analysis"),
    ("spa", "Sample Pairs (SPA)"),
    ("ws", "Weighted Stego (WS)"),
]


class BitStatTab(QFrame):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        # whole tab scrolls when the stat card + expanded zsteg card overflow the viewport
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("transparentScroll")

        content = QWidget()
        content.setObjectName("transparentScrollContent")
        self.main_layout = QVBoxLayout(content)
        self.main_layout.setSpacing(10)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        self.main_layout.addWidget(self._build_stat_card())

        # LSB Extraction (zsteg) card - shown only for PNG/BMP (see set_target_file)
        self.zsteg_card = ZstegCard()
        self.zsteg_card.hide()
        self.main_layout.addWidget(self.zsteg_card)

        self.main_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _build_stat_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title = QLabel("Spatial-Domain LSB Analysis")
        title.setObjectName("cardTitle")
        layout.addWidget(title)

        # Overall verdict banner (colored, set in load_data)
        self.verdict_banner = QLabel("Run analysis to detect LSB steganography.")
        self.verdict_banner.setWordWrap(True)
        self.verdict_banner.setStyleSheet(
            f"padding: 10px 12px; border-radius: 6px; background: rgba(148,163,184,0.12); color: {GRAY};")
        layout.addWidget(self.verdict_banner)

        # Per-detector table with visual embedding-rate bars
        self.table = QTableWidget(0, 4)
        self.table.setObjectName("darkTable")
        self.table.setHorizontalHeaderLabels(["Method", "Estimated Embedding Rate", "Threshold", "Verdict"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

        note = QLabel(
            "RS / SPA / WS estimate LSB-replacement rate blind (RS from ~10%, SPA/WS from ~25-40%; very "
            "low rates may be missed). HCF-COM (LSB matching) and PDH (PVD) need an original to compare "
            "against — run those in Compare mode.")
        note.setObjectName("hintLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        # Collapsible raw-value table for expert users (every method's exact measurement)
        self._chevron = create_icon_pixmap(str(ICON_DIR / "chevron-down.svg"), "#818D9F", size=14)
        self.raw_toggle = QPushButton("Reference Measurements")
        self.raw_toggle.setObjectName("SecondaryBtn")
        self.raw_toggle.setCheckable(True)
        self.raw_toggle.setIcon(QIcon(self._chevron))
        self.raw_toggle.toggled.connect(self._toggle_raw)
        layout.addWidget(self.raw_toggle, alignment=Qt.AlignmentFlag.AlignLeft)

        self.raw_table = QTableWidget(0, 2)
        self.raw_table.setObjectName("darkTable")
        self.raw_table.setHorizontalHeaderLabels(["Method", "Raw Measurement"])
        self.raw_table.verticalHeader().setVisible(False)
        self.raw_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.raw_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.raw_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.raw_table.hide()
        layout.addWidget(self.raw_table)

        return card

    def _toggle_raw(self, checked: bool):
        self.raw_table.setVisible(checked)
        pix = self._chevron.transformed(QTransform().rotate(180)) if checked else self._chevron
        self.raw_toggle.setIcon(QIcon(pix))

    @staticmethod
    def _fit_table(table: QTableWidget):
        """Shrink a QTableWidget to exactly its header + rows so the card hugs the data
        instead of reserving a tall empty band below the last row."""
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        h = table.horizontalHeader().sizeHint().height() + table.frameWidth() * 2 + 2
        for r in range(table.rowCount()):
            h += table.rowHeight(r)
        table.setFixedHeight(h)

    def set_target_file(self, file_path: str):
        """Point the zsteg card at the current file and show it only for PNG/BMP."""
        if file_path and Path(file_path).suffix.lower() in ZSTEG_FORMATS:
            self.zsteg_card.set_target(file_path)
            self.zsteg_card.show()
        else:
            self.zsteg_card.hide()

    def load_data(self, data: dict):
        self.table.setRowCount(0)
        self.raw_table.setRowCount(0)
        stat = data.get("statistical_analysis", {})

        if not stat or "error" in stat:
            self._set_banner("Run analysis to detect LSB steganography.", GRAY)
            return

        self._populate_raw(stat)

        # --- structural rate estimators (RS, SPA) ---
        any_detected = False
        detected_rates = []
        for key, label in RATE_DETECTORS:
            d = stat.get(key)
            if not d or "estimated_embedding_rate" not in d:
                continue
            rate = d["estimated_embedding_rate"]
            threshold = d.get("threshold", 0)
            detected = bool(d.get("detected"))
            any_detected = any_detected or detected
            if detected:
                detected_rates.append(rate)
            self._add_rate_row(label, rate, threshold, detected)
        self._fit_table(self.table)

        # Chi-Square / HCF-COM / PDH are differential-only (no reliable blind verdict) - they
        # are not shown here; their cover-vs-stego verdict lives in Compare mode (see the note below).

        # --- overall verdict banner ---
        if any_detected:
            est = max(detected_rates) * 100
            self._set_banner(f"Likely LSB steganography — estimated embedding ≈ {est:.0f}% of LSB capacity", RED)
        else:
            self._set_banner("No spatial-domain LSB steganography detected", GREEN)

    def _populate_raw(self, stat: dict):
        """Every method's exact measured value, for expert users."""
        rows = []
        for key, label in RATE_DETECTORS:
            d = stat.get(key)
            if d and "estimated_embedding_rate" in d:
                rows.append((label, f"estimated rate = {d['estimated_embedding_rate']:.4f}"))
        chi = stat.get("chi_square")
        if chi:
            rows.append(("Chi-Square", f"χ² = {chi.get('chi2', 0):.1f},  p = {chi.get('p_value', 0):.4g}"))
        hcf = stat.get("hcf_com")
        if hcf:
            rows.append(("HCF-COM", f"center of mass = {hcf.get('hcf_com', 0):.4f}"))
        pdh = stat.get("pdh")
        if pdh:
            rows.append(("PDH", f"roughness = {pdh.get('pdh_roughness', 0):.3e},  step = {pdh.get('pdh_step', 0):.3e}"))

        self.raw_table.setRowCount(len(rows))
        for i, (label, value) in enumerate(rows):
            self.raw_table.setRowHeight(i, 30)
            self.raw_table.setItem(i, 0, QTableWidgetItem(label))
            self.raw_table.setItem(i, 1, QTableWidgetItem(value))
        self._fit_table(self.raw_table)

    def _set_banner(self, text: str, color: str):
        self.verdict_banner.setText(text)
        # tint the background from the same color at low alpha
        r, g, b = QColor(color).red(), QColor(color).green(), QColor(color).blue()
        self.verdict_banner.setStyleSheet(
            f"padding: 10px 12px; border-radius: 6px; background: rgba({r},{g},{b},0.12); color: {color};")

    def _add_rate_row(self, method: str, rate: float, threshold: float, detected: bool):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 34)

        self.table.setItem(row, 0, QTableWidgetItem(method))

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(round(rate * 100)))
        bar.setFormat(f"{rate * 100:.1f}%")
        bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chunk = RED if detected else BLUE
        bar.setStyleSheet(
            "QProgressBar { background: rgba(148,163,184,0.15); border: none; border-radius: 4px; color: #E2E8F0; }"
            f"QProgressBar::chunk {{ background: {chunk}; border-radius: 4px; }}")
        self.table.setCellWidget(row, 1, bar)

        self.table.setItem(row, 2, QTableWidgetItem(f"{threshold * 100:.0f}%"))

        verdict = QTableWidgetItem("Suspicious" if detected else "Clean")
        verdict.setForeground(QBrush(QColor(RED if detected else GREEN)))
        self.table.setItem(row, 3, verdict)
