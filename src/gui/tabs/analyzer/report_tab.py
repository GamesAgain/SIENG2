from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QScrollArea, QWidget
)
from PyQt6.QtGui import QColor

RED = "#f43f5e"
YELLOW = "#EAB308"
GREEN = "#10B981"
GRAY = "#94A3B8"

STAT_LABELS = {
    "rs_analysis": "RS Analysis",
    "spa": "Sample Pairs (SPA)",
    "ws": "Weighted Stego (WS)",
}


class ReportTab(QFrame):
    """
    Overall analysis report — aggregates the Metadata / File Structure / Bit-Spatial
    findings the other tabs already computed into one grouped summary, so the user
    sees the whole picture without opening each tab. Does not re-run analyze().
    """

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
        self.card_layout = QVBoxLayout(card)
        self.card_layout.setContentsMargins(15, 15, 15, 15)
        self.card_layout.setSpacing(10)

        title = QLabel("Analysis Report")
        title.setObjectName("cardTitle")
        self.card_layout.addWidget(title)

        self.verdict_banner = QLabel("Run analysis to generate a report.")
        self.verdict_banner.setWordWrap(True)
        self._style_banner(GRAY)
        self.card_layout.addWidget(self.verdict_banner)

        # domain sections are rebuilt on each load_data
        self.sections = QVBoxLayout()
        self.sections.setSpacing(4)
        self.card_layout.addLayout(self.sections)

        main.addWidget(card)
        main.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _style_banner(self, color: str):
        c = QColor(color)
        self.verdict_banner.setStyleSheet(
            f"padding: 10px 12px; border-radius: 6px; background: rgba({c.red()},{c.green()},{c.blue()},0.12); color: {color};")

    def _clear_sections(self):
        while self.sections.count():
            item = self.sections.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _add_section(self, title: str, findings: list):
        """findings: list of (text, color). Renders a domain header + indented finding lines."""
        header = QLabel(title.upper())
        header.setObjectName("sectionLabel")
        self.sections.addWidget(header)
        for text, color in findings:
            row = QLabel(f"•  {text}")
            row.setWordWrap(True)
            row.setStyleSheet(f"color: {color}; margin-left: 6px;")
            self.sections.addWidget(row)
        self.sections.addSpacing(6)

    def load_data(self, data: dict):
        self._clear_sections()

        if not data or not any(k in data for k in ("metadata_analysis", "structure_analysis", "statistical_analysis")):
            self.verdict_banner.setText("Run analysis to generate a report.")
            self._style_banner(GRAY)
            return

        worst = GREEN  # escalates to YELLOW / RED as findings are added

        # --- Metadata domain ---
        meta = data.get("metadata_analysis", {})
        n_meta = (len(meta.get("time_anomalies", [])) + len(meta.get("software_anomalies", []))
                  + len(meta.get("text_anomalies", [])))
        if n_meta:
            self._add_section("Metadata", [(f"{n_meta} anomaly(ies) found (timestamp / software / text)", RED)])
            worst = RED
        else:
            self._add_section("Metadata", [("No anomalies found", GREEN)])

        # --- File Structure domain ---
        struct = data.get("structure_analysis", {})
        struct_findings = []
        overlay = struct.get("overlay_analysis", {})
        if overlay.get("has_overlay"):
            struct_findings.append((f"{overlay.get('overlay_size_bytes', 0)} bytes appended after the file's real end", RED))
            worst = RED
        if struct.get("suspicious_chunk_count", 0):
            struct_findings.append((f"{struct['suspicious_chunk_count']} non-standard chunk(s)", RED))
            worst = RED
        for anomaly in struct.get("integrity_anomalies", []):
            struct_findings.append((anomaly.get("detail", "integrity anomaly"), RED))
            worst = RED
        sigs = struct.get("binwalk_raw", {}).get("signatures", [])
        if sigs:
            struct_findings.append((f"{len(sigs)} file signature(s) detected by binwalk (informational)", GRAY))
        if not struct_findings or all(c == GRAY for _, c in struct_findings):
            struct_findings.insert(0, ("No structural anomalies found", GREEN))
        self._add_section("File Structure", struct_findings)

        # --- Bit / Spatial domain (blind detectors only; matching/PVD live in Compare) ---
        stat = data.get("statistical_analysis", {})
        applicable = {k: v for k, v in stat.items() if isinstance(v, dict) and v.get("detected") is not None}
        triggered = [STAT_LABELS.get(k, k) for k, v in applicable.items() if v.get("detected")]
        if triggered:
            self._add_section("Bit / Spatial", [(f"LSB replacement flagged by {', '.join(triggered)}", RED)])
            worst = RED
        elif applicable:
            self._add_section("Bit / Spatial", [("No LSB-replacement signature (run Compare for LSB matching / PVD)", GREEN)])

        # --- overall verdict banner ---
        if worst == RED:
            self.verdict_banner.setText("<b>Suspicious — one or more domains show signs of hidden data.</b>")
        else:
            self.verdict_banner.setText("<b>No anomalies detected across metadata, structure, and statistical tests.</b>")
        self._style_banner(worst)
