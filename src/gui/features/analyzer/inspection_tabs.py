"""File Structure and Metadata views adapted from nobit's analyzer cards."""

import base64

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QPlainTextEdit,
    QSplitter, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)


def _card(title, widget):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(15, 15, 15, 15)
    label = QLabel(title)
    label.setObjectName("cardTitle")
    layout.addWidget(label)
    layout.addWidget(widget, 1)
    return frame


class FileStructureTab(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        layout.addWidget(self.status_label)
        self.tree_widget = QTreeWidget()
        self.tree_widget.setObjectName("structureTree")
        self.tree_widget.setHeaderLabels(["Name", "Size", "Value", "Description", "Warnings"])
        self.tree_widget.header().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tree_widget.setColumnWidth(0, 175)
        self.tree_widget.setColumnWidth(1, 80)
        self.tree_widget.setColumnWidth(2, 160)
        self.binwalk_list = QListWidget()
        self.binwalk_list.setObjectName("binwalkList")
        self.summary_list = QListWidget()
        self.summary_list.setObjectName("summaryList")
        split = QSplitter()
        left = QFrame()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(_card("Internal Structure", self.tree_widget), 3)
        left_layout.addWidget(_card("Embedded Signatures", self.binwalk_list), 1)
        split.addWidget(left)
        split.addWidget(_card("Structure Findings", self.summary_list))
        split.setSizes([650, 350])
        layout.addWidget(split, 1)
        self.summary_list.currentRowChanged.connect(self._select_finding)
        self._finding_items = []
        self.tree_widget.itemDoubleClicked.connect(self._preview_overlay)

    def clear_result(self):
        self.tree_widget.clear()
        self.binwalk_list.clear()
        self.summary_list.clear()
        self._finding_items = []
        self.status_label.clear()
        self.status_label.hide()

    def set_status(self, message):
        self.status_label.setText(message)
        self.status_label.setVisible(bool(message))

    def _add_node(self, parent, node):
        item = QTreeWidgetItem(parent, [str(node.get("name", "")),
                                      str(node.get("size_bytes", "")),
                                      str(node.get("value", ""))[:160],
                                      str(node.get("description", ""))[:220], ""])
        for child in node.get("sub_chunks", []):
            self._add_node(item, child)
        return item

    def _select_finding(self, row):
        if 0 <= row < len(self._finding_items):
            item = self._finding_items[row]
            if item:
                self.tree_widget.setCurrentItem(item)
                self.tree_widget.scrollToItem(item)

    def _preview_overlay(self, item, _column):
        encoded = item.data(0, Qt.ItemDataRole.UserRole)
        if not encoded:
            return
        preview = base64.b64decode(encoded)
        dialog = QDialog(self)
        dialog.setWindowTitle("Post-content overlay preview")
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        hex_lines = []
        for offset in range(0, len(preview), 16):
            block = preview[offset:offset + 16]
            ascii_text = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in block)
            hex_lines.append(f"{offset:08X}  {block.hex(' '):47}  {ascii_text}")
        editor.setPlainText("\n".join(hex_lines))
        layout.addWidget(editor)
        dialog.resize(670, 370)
        dialog.exec()

    def load_data(self, data):
        self.clear_result()
        result = data.get("structure_analysis", {})
        errors = result.get("errors", [])
        tree = result.get("hachoir_raw", {})
        for node in tree.get("structure", []):
            self._add_node(self.tree_widget, node)
        for signature in result.get("binwalk_raw", {}).get("signatures", []):
            self.binwalk_list.addItem(f"{signature.get('offset', 0):,}  ·  {signature.get('description', '')}")
        media = result.get("mediainfo_raw") or {}
        if media.get("tracks"):
            media_item = QTreeWidgetItem(self.tree_widget, ["MediaInfo tracks", "", "", "Container and stream summary", ""])
            for track in media["tracks"]:
                QTreeWidgetItem(media_item, [str(track.get("@type", "Track")),
                                             str(track.get("StreamSize", "")),
                                             str(track.get("Format", "")), "", ""])
        overlay = result.get("overlay_analysis", {})
        overlay_item = None
        if overlay.get("exists"):
            overlay_item = QTreeWidgetItem(self.tree_widget, ["Post-content overlay", str(overlay.get("size", 0)),
                                                              f"Offset {overlay.get('offset')}", "Bytes after declared content", "Suspicious"])
            for column in range(5):
                overlay_item.setForeground(column, QColor("#f43f5e"))
            overlay_item.setData(0, Qt.ItemDataRole.UserRole, overlay.get("preview_b64", ""))
        for finding in result.get("integrity_anomalies", []):
            self.summary_list.addItem(f"{finding.get('type', 'Finding')}: {finding.get('detail', '')}")
            self._finding_items.append(overlay_item if finding.get("type") == "overlay" else None)
        if not self.summary_list.count():
            self.summary_list.addItem("No structural anomalies detected." if not errors else "Structure check incomplete.")
            self._finding_items.append(None)
        self.set_status("Inspection partial: " + "; ".join(errors) if errors else "")


class MetadataTab(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        layout.addWidget(self.status_label)
        self.metadata_table = self._table(["Property", "Value"])
        self.anomalies_table = self._table(["Location", "Detail"])
        split = QSplitter()
        split.addWidget(_card("Metadata", self.metadata_table))
        split.addWidget(_card("Anomalies Detected", self.anomalies_table))
        split.setSizes([550, 450])
        layout.addWidget(split, 1)

    @staticmethod
    def _table(headers):
        table = QTableWidget(0, len(headers))
        table.setObjectName("darkTable")
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().hide()
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        return table

    def clear_result(self):
        self.metadata_table.setRowCount(0)
        self.anomalies_table.setRowCount(0)
        self.status_label.clear()
        self.status_label.hide()

    def set_status(self, message):
        self.status_label.setText(message)
        self.status_label.setVisible(bool(message))

    def load_data(self, data):
        self.clear_result()
        result = data.get("metadata_analysis", {})
        error = result.get("error")
        self.set_status(f"Metadata inspection failed: {error}" if error else "")
        raw = result.get("raw_data", {})
        self.metadata_table.setRowCount(len(raw))
        for row, (key, value) in enumerate(raw.items()):
            self.metadata_table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.metadata_table.setItem(row, 1, QTableWidgetItem(str(value)))
        anomalies = [entry for key in ("time_anomalies", "software_anomalies", "text_anomalies")
                     for entry in result.get(key, [])]
        if not anomalies and not error:
            anomalies = [{"tag": "", "message": "No anomalies detected."}]
        self.anomalies_table.setRowCount(len(anomalies))
        for row, entry in enumerate(anomalies):
            self.anomalies_table.setItem(row, 0, QTableWidgetItem(str(entry.get("tag", ""))))
            self.anomalies_table.setItem(row, 1, QTableWidgetItem(str(entry.get("message", ""))))
        self.metadata_table.resizeColumnToContents(0)
        self.anomalies_table.resizeColumnToContents(0)
