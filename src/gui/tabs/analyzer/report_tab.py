from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QListWidget, QListWidgetItem
)
from PyQt6.QtGui import QColor, QBrush

STAT_LABELS = {
    "chi_square": "Chi-Square Attack",
    "rs_analysis": "RS Analysis",
    "bit_balance": "Bit Balance Test",
    "spa": "Sample Pairs Analysis (SPA)",
    "correlation": "Correlation Analysis",
}


class ReportTab(QFrame):
    """
    สรุปผลรวมของ Metadata/File Structure/Bit Statistics เป็นรายการเดียว -
    ไม่เรียก analyze() เพิ่มเอง แค่รวม field ที่ analyzer_page.py คำนวณไว้แล้ว
    ให้ผู้ใช้เห็นภาพรวมโดยไม่ต้องไล่เปิดทีละแท็บ
    """

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("Overall Summary")
        title.setObjectName("cardTitle")
        layout.addWidget(title)

        self.summary_list = QListWidget()
        self.summary_list.setWordWrap(True)
        self.summary_list.setObjectName("summaryList")
        layout.addWidget(self.summary_list)

    def load_data(self, data: dict):
        self.summary_list.clear()
        findings = []

        # 1. Metadata anomalies
        metadata = data.get("metadata_analysis", {})
        meta_anomaly_count = (
            len(metadata.get("time_anomalies", []))
            + len(metadata.get("software_anomalies", []))
            + len(metadata.get("text_anomalies", []))
        )
        if meta_anomaly_count:
            findings.append((f"Metadata: {meta_anomaly_count} anomaly(ies) found (timestamp/software/text)", "#EF4444"))
        else:
            findings.append(("Metadata: no anomalies found", "#10B981"))

        # 2. Structure anomalies
        structure = data.get("structure_analysis", {})
        overlay = structure.get("overlay_analysis", {})
        if overlay.get("has_overlay"):
            findings.append((f"Structure: {overlay.get('overlay_size_bytes', 0)} bytes appended after the file's real end", "#EF4444"))

        suspicious_chunks = structure.get("suspicious_chunk_count", 0)
        if suspicious_chunks:
            findings.append((f"Structure: {suspicious_chunks} non-standard chunk(s) found", "#EF4444"))

        integrity_anomalies = structure.get("integrity_anomalies", [])
        for anomaly in integrity_anomalies:
            findings.append((f"Structure: {anomaly.get('detail', 'integrity anomaly')}", "#EF4444"))

        # binwalk always reports >1 signature for an ordinary file of most formats (e.g. a
        # valid PNG shows both its own container AND its Zlib-compressed IDAT stream) - with
        # no cover reference to compare against (that's what Compare mode is for), there's no
        # safe baseline to call any particular count "extra", so just report it as information.
        signatures = structure.get("binwalk_raw", {}).get("signatures", [])
        if signatures:
            findings.append((f"Structure: {len(signatures)} file signature(s) detected by binwalk (informational)", None))

        if not overlay.get("has_overlay") and not suspicious_chunks and not integrity_anomalies:
            findings.append(("Structure: no anomalies found", "#10B981"))

        # 3. Statistical detectors - "detected" can be None (e.g. chi-square blind mode has no
        # cover to compare against, see chi_square.py) meaning "not applicable", not "clean"
        stat_results = data.get("statistical_analysis", {})
        applicable = {k: v for k, v in stat_results.items() if isinstance(v, dict) and v.get("detected") is not None}
        triggered = [STAT_LABELS.get(k, k) for k, v in applicable.items() if v.get("detected")]
        if triggered:
            findings.append((f"Statistical: {len(triggered)}/{len(applicable)} detector(s) flagged this file ({', '.join(triggered)})", "#EAB308"))
        elif applicable:
            findings.append(("Statistical: no detector flagged this file", "#10B981"))

        for text, color in findings:
            item = QListWidgetItem(text)
            if color:
                item.setForeground(QBrush(QColor(color)))
            self.summary_list.addItem(item)
