"""File-structure inspection view."""

import base64

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QFrame, QLabel, QListWidget, QPlainTextEdit,
    QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from src.core.analyzer.models.analysis import AnalysisResult


class FileStructureTab(QFrame):
    """Own and display the structure section of an analysis result."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.analysis_result: AnalysisResult | None = None
        self._setup_ui()
        self.clear_analysis_result()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.status_hint = QLabel()
        self.status_hint.setObjectName("hintLabel")
        self.status_hint.setWordWrap(True)
        layout.addWidget(self.status_hint)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setObjectName("analysisRawTable")
        self.tree_widget.setHeaderLabels(
            ["Name", "Size", "Value", "Description", "Warnings"]
        )
        self.tree_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree_widget.setAlternatingRowColors(True)
        self.tree_widget.header().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tree_widget.setColumnWidth(0, 175)
        self.tree_widget.setColumnWidth(1, 80)
        self.tree_widget.setColumnWidth(2, 160)
        self.tree_widget.itemDoubleClicked.connect(self._preview_overlay)

        self.binwalk_list = QListWidget()
        self.binwalk_list.setObjectName("analysisRawTable")
        self.binwalk_list.setAlternatingRowColors(True)
        self.summary_list = QListWidget()
        self.summary_list.setObjectName("analysisRawTable")
        self.summary_list.setAlternatingRowColors(True)
        self.summary_list.currentRowChanged.connect(self._select_finding)
        self._finding_items = []

        split = QSplitter()
        left = QFrame()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self._card("Internal Structure", self.tree_widget), 3)
        left_layout.addWidget(self._card("Embedded Signatures", self.binwalk_list), 1)
        split.addWidget(left)
        split.addWidget(self._card("Structure Findings", self.summary_list))
        split.setSizes([650, 350])
        layout.addWidget(split, 1)

    @staticmethod
    def _card(title: str, widget) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)
        label = QLabel(title)
        label.setObjectName("cardTitle")
        layout.addWidget(label)
        layout.addWidget(widget, 1)
        return card

    def set_analysis_result(self, result: AnalysisResult) -> None:
        """Store the completed result and show structure availability."""
        if not isinstance(result, AnalysisResult):
            raise TypeError("result must be an AnalysisResult.")

        self.analysis_result = result

    def clear_analysis_result(self) -> None:
        """Forget the old result and restore the waiting state."""
        self.analysis_result = None
        self.tree_widget.clear()
        self.binwalk_list.clear()
        self.summary_list.clear()
        self._finding_items = []
        self.status_hint.setText("Analysis results will appear here.")

    def set_inspection_status(self, message: str) -> None:
        """Show inspection progress before the detailed result UI is installed."""
        self.status_hint.setText(message)

    def _add_node(self, parent, node: dict) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, [
            str(node.get("name", "")),
            str(node.get("size_bytes", "")),
            str(node.get("value", ""))[:160],
            str(node.get("description", ""))[:220],
            "",
        ])
        for child in node.get("sub_chunks", []):
            self._add_node(item, child)
        return item

    def _select_finding(self, row: int) -> None:
        if 0 <= row < len(self._finding_items):
            item = self._finding_items[row]
            if item is not None:
                self.tree_widget.setCurrentItem(item)
                self.tree_widget.scrollToItem(item)

    def _preview_overlay(self, item: QTreeWidgetItem, _column: int) -> None:
        encoded = item.data(0, Qt.ItemDataRole.UserRole)
        if not encoded:
            return
        preview = base64.b64decode(encoded)
        dialog = QDialog(self)
        dialog.setWindowTitle("Post-content overlay preview")
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        lines = []
        for offset in range(0, len(preview), 16):
            block = preview[offset:offset + 16]
            ascii_text = "".join(
                chr(byte) if 32 <= byte < 127 else "." for byte in block
            )
            lines.append(f"{offset:08X}  {block.hex(' '):47}  {ascii_text}")
        editor.setPlainText("\n".join(lines))
        layout.addWidget(editor)
        dialog.resize(670, 370)
        dialog.exec()

    def load_data(self, data: dict) -> None:
        """Render Hachoir, Binwalk, integrity and overlay inspection output."""
        self.tree_widget.clear()
        self.binwalk_list.clear()
        self.summary_list.clear()
        self._finding_items = []
        result = data.get("structure_analysis", {})
        errors = result.get("errors", [])
        for node in result.get("hachoir_raw", {}).get("structure", []):
            self._add_node(self.tree_widget, node)
        for signature in result.get("binwalk_raw", {}).get("signatures", []):
            self.binwalk_list.addItem(
                f"{signature.get('offset', 0):,} · "
                f"{signature.get('description', '')}"
            )
        media = result.get("mediainfo_raw") or {}
        if media.get("tracks"):
            parent = QTreeWidgetItem(self.tree_widget, [
                "MediaInfo tracks", "", "", "Container and stream summary", "",
            ])
            for track in media["tracks"]:
                QTreeWidgetItem(parent, [
                    str(track.get("@type", "Track")),
                    str(track.get("StreamSize", "")),
                    str(track.get("Format", "")), "", "",
                ])
        overlay = result.get("overlay_analysis", {})
        overlay_item = None
        if overlay.get("exists"):
            overlay_item = QTreeWidgetItem(self.tree_widget, [
                "Post-content overlay", str(overlay.get("size", 0)),
                f"Offset {overlay.get('offset')}", "Bytes after declared content",
                "Suspicious",
            ])
            for column in range(5):
                overlay_item.setForeground(column, QColor("#f43f5e"))
            overlay_item.setData(
                0, Qt.ItemDataRole.UserRole, overlay.get("preview_b64", "")
            )
        for finding in result.get("integrity_anomalies", []):
            self.summary_list.addItem(
                f"{finding.get('type', 'Finding')}: "
                f"{finding.get('detail', '')}"
            )
            self._finding_items.append(
                overlay_item if finding.get("type") == "overlay" else None
            )
        if not self.summary_list.count():
            self.summary_list.addItem(
                "Structure check incomplete."
                if errors else "No structural anomalies detected."
            )
            self._finding_items.append(None)
        self.set_inspection_status(
            "Inspection partial: " + "; ".join(errors) if errors else ""
        )
