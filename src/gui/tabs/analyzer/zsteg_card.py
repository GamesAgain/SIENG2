"""
zsteg card for the Bit / Spatial Statistics tab. LSB extraction/enumeration for
PNG & BMP via the zsteg tool (runs in the analyzer Docker container). Only shown
for PNG/BMP files - zsteg does not support other formats.

Two-stage flow:
  Scan    -> enumerate hiding combinations (bit plane / channel / order), list findings
  Extract -> pull the raw bytes out of a chosen combination, preview + save
"""
import base64
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QIcon, QTransform
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox,
    QCheckBox, QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QDialog, QPlainTextEdit, QFileDialog, QProgressBar, QMessageBox,
)

from src.core.analyzer.docker_bridge import zsteg_scan, zsteg_extract
from src.gui.components.gui_utils import create_icon_pixmap

ICON_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "svg"


class ZstegWorker(QThread):
    """Runs a blocking zsteg docker call off the UI thread so the GUI stays responsive
    (some scans, especially --all, take a while). Emits the result dict when done."""
    done = pyqtSignal(dict)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self):
        self.done.emit(self._func(*self._args, **self._kwargs))


class ZstegCard(QFrame):
    def __init__(self):
        super().__init__()
        self.file_path = None
        self._scan_worker = None
        self._extract_worker = None
        self.setObjectName("card")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title = QLabel("LSB Extraction (zsteg)")
        title.setObjectName("cardTitle")
        layout.addWidget(title)

        hint = QLabel("Enumerates LSB hiding combinations (bit plane, channel, order) and extracts "
                      "readable payloads. PNG / BMP only.")
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # --- Action row: Scan + advanced toggle ---
        action_row = QHBoxLayout()
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.setObjectName("PrimaryActionBtn")
        self.scan_btn.clicked.connect(self.on_scan_clicked)
        action_row.addWidget(self.scan_btn)

        self._chevron = create_icon_pixmap(str(ICON_DIR / "chevron-down.svg"), "#818D9F", size=14)
        self.adv_toggle = QPushButton("Advanced Options")
        self.adv_toggle.setObjectName("SecondaryBtn")
        self.adv_toggle.setCheckable(True)
        self.adv_toggle.setIcon(QIcon(self._chevron))
        self.adv_toggle.toggled.connect(self._toggle_advanced)
        action_row.addWidget(self.adv_toggle)

        action_row.addStretch()
        # small indeterminate busy bar shown while a scan/extract runs on the worker thread
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate (animated)
        self.progress.setTextVisible(False)
        self.progress.setFixedSize(90, 6)
        self.progress.hide()
        action_row.addWidget(self.progress)
        self.status_label = QLabel("")
        self.status_label.setObjectName("hintLabel")
        action_row.addWidget(self.status_label)
        layout.addLayout(action_row)

        # --- Advanced options panel (hidden by default) ---
        self.adv_panel = self._build_advanced_panel()
        self.adv_panel.hide()
        layout.addWidget(self.adv_panel)

        # --- Results table ---
        self.table = QTableWidget(0, 3)
        self.table.setObjectName("darkTable")
        self.table.setMinimumHeight(220)
        self.table.setHorizontalHeaderLabels(["Combination", "Type", "Preview"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _: self.on_extract_clicked())
        layout.addWidget(self.table)

        # --- Extract row ---
        extract_row = QHBoxLayout()
        extract_row.addStretch()
        self.extract_btn = QPushButton("Extract Selected")
        self.extract_btn.setObjectName("SecondaryBtn")
        self.extract_btn.clicked.connect(self.on_extract_clicked)
        extract_row.addWidget(self.extract_btn)
        layout.addLayout(extract_row)

    def _build_advanced_panel(self) -> QFrame:
        panel = QFrame()
        grid = QVBoxLayout(panel)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        self.all_methods_cb = QCheckBox("Try all methods (-a) — every bit plane / channel / order")

        self.bits_input = QLineEdit()
        self.bits_input.setObjectName("formInput")
        self.bits_input.setPlaceholderText("e.g. 1,2,3   (bit planes 1-8; blank = default set)")

        self.channels_input = QLineEdit()
        self.channels_input.setObjectName("formInput")
        self.channels_input.setPlaceholderText("e.g. r,g,b,rgb   (blank = default set)")

        self.bit_order_combo = QComboBox()
        self.bit_order_combo.addItems(["Bit order: both", "Bit order: LSB first", "Bit order: MSB first"])

        self.pixel_order_combo = QComboBox()
        self.pixel_order_combo.addItems(["Pixel order: auto", "Pixel order: xy", "Pixel order: yx",
                                         "Pixel order: XY", "Pixel order: YX"])

        self.limit_input = QLineEdit()
        self.limit_input.setObjectName("formInput")
        self.limit_input.setPlaceholderText("Byte limit per combination (blank = 256)")

        for w in (self.all_methods_cb, self.bits_input, self.channels_input,
                  self.bit_order_combo, self.pixel_order_combo, self.limit_input):
            grid.addWidget(w)
        return panel

    # ---- called by the parent tab ----
    def set_target(self, file_path: str):
        """Point the card at a new file and reset previous results."""
        self.file_path = file_path
        self.table.setRowCount(0)
        self.status_label.setText("")

    # ---- handlers ----
    def _toggle_advanced(self, checked: bool):
        self.adv_panel.setVisible(checked)
        pix = self._chevron.transformed(QTransform().rotate(180)) if checked else self._chevron
        self.adv_toggle.setIcon(QIcon(pix))

    def _gather_options(self) -> dict:
        bit_order = {0: None, 1: "lsb", 2: "msb"}[self.bit_order_combo.currentIndex()]
        order = {0: None, 1: "xy", 2: "yx", 3: "XY", 4: "YX"}[self.pixel_order_combo.currentIndex()]
        limit_text = self.limit_input.text().strip()
        return {
            "all_methods": self.all_methods_cb.isChecked(),
            "bits": self.bits_input.text().strip() or None,
            "channels": self.channels_input.text().strip() or None,
            "order": order,
            "bit_order": bit_order,
            "limit": int(limit_text) if limit_text.isdigit() else None,
        }

    def _set_busy(self, busy: bool, message: str = ""):
        self.progress.setVisible(busy)
        self.status_label.setText(message)
        self.scan_btn.setEnabled(not busy)
        self.extract_btn.setEnabled(not busy)

    def on_scan_clicked(self):
        if not self.file_path or (self._scan_worker and self._scan_worker.isRunning()):
            return
        self._set_busy(True, "Scanning…")
        self._scan_worker = ZstegWorker(zsteg_scan, self.file_path, **self._gather_options())
        self._scan_worker.done.connect(self._on_scan_done)
        self._scan_worker.start()

    def _on_scan_done(self, result: dict):
        self._set_busy(False)
        if result.get("error"):
            QMessageBox.critical(self, "zsteg Scan Failed", result["error"])
            return
        self._populate(result.get("findings", []))

    def _populate(self, findings: list):
        self.table.setRowCount(len(findings))
        for row, f in enumerate(findings):
            combo_item = QTableWidgetItem(f.get("combination", ""))
            type_item = QTableWidgetItem(f.get("type", ""))
            preview_item = QTableWidgetItem(f.get("content", ""))
            # highlight readable-text findings (the likely real payload) over file/data noise
            if f.get("type") == "text":
                for item in (combo_item, type_item, preview_item):
                    item.setForeground(QBrush(QColor("#38BDF8")))
            self.table.setItem(row, 0, combo_item)
            self.table.setItem(row, 1, type_item)
            self.table.setItem(row, 2, preview_item)

        self.status_label.setText(f"{len(findings)} finding(s)" if findings
                                  else "No hidden LSB payloads found")

    def on_extract_clicked(self):
        row = self.table.currentRow()
        if row < 0 or not self.file_path or (self._extract_worker and self._extract_worker.isRunning()):
            return
        combination = self.table.item(row, 0).text()
        self._set_busy(True, f"Extracting {combination}…")
        self._extract_worker = ZstegWorker(zsteg_extract, self.file_path, combination)
        self._extract_worker.done.connect(lambda result, c=combination: self._on_extract_done(result, c))
        self._extract_worker.start()

    def _on_extract_done(self, result: dict, combination: str):
        self._set_busy(False)
        if result.get("error"):
            QMessageBox.critical(self, "zsteg Extract Failed", result["error"])
            return
        data = base64.b64decode(result.get("data_b64", ""))
        ExtractPreviewDialog(combination, data, result.get("total_bytes", len(data)),
                             result.get("truncated", False), self).exec()


class ExtractPreviewDialog(QDialog):
    """Show extracted bytes as text + hex, with a Save As option."""

    def __init__(self, combination: str, data: bytes, total_bytes: int, truncated: bool, parent=None):
        super().__init__(parent)
        self.data = data
        self.setWindowTitle(f"Extracted: {combination}")
        self.resize(640, 460)

        layout = QVBoxLayout(self)

        info = f"{total_bytes} bytes extracted"
        if truncated:
            info += f" (showing first {len(data)})"
        info_label = QLabel(info)
        info_label.setObjectName("hintLabel")
        layout.addWidget(info_label)

        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(self._render(data))
        layout.addWidget(view)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("Save As…")
        save_btn.setObjectName("SecondaryBtn")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    @staticmethod
    def _render(data: bytes) -> str:
        text = data.decode("utf-8", "replace")
        printable = "".join(ch if (ch.isprintable() or ch in "\r\n\t") else "." for ch in text)
        hexdump = data[:512].hex(" ")
        return f"--- TEXT ---\n{printable}\n\n--- HEX (first 512 bytes) ---\n{hexdump}"

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Extracted Data", "extracted.bin")
        if path:
            with open(path, "wb") as f:
                f.write(self.data)
