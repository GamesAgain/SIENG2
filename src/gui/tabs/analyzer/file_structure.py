import base64
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QSplitter, QListWidget, QListWidgetItem, QHBoxLayout,
    QScrollArea, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush
from src.gui.tabs.analyzer.zsteg_card import ExtractPreviewDialog

RED = "#f43f5e"
GREEN = "#34D399"
GRAY = "#94A3B8"
NAV_ROLE = Qt.ItemDataRole.UserRole      # summary item -> the tree item it points at
BYTES_ROLE = Qt.ItemDataRole.UserRole + 1  # tree item -> {"b64", "size"} for the hex preview


def _ascii_snippet(data: bytes, n: int = 60) -> str:
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data[:n])


class FileStructureTab(QFrame):
    def __init__(self):
        super().__init__()
        self._suspicious_items = []
        self._overlay_item = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setObjectName("transparentScroll")

        scroll_content = QWidget()
        scroll_content.setObjectName("transparentScrollContent")
        content_layout = QHBoxLayout(scroll_content)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)

        # --- Left: structure tree + binwalk ---
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        tree_frame = QFrame()
        tree_frame.setObjectName("card")
        tree_layout = QVBoxLayout(tree_frame)
        tree_layout.setContentsMargins(15, 15, 15, 15)
        tree_layout.setSpacing(10)

        tree_title = QLabel("Internal Structure")
        tree_title.setObjectName("cardTitle")
        tree_layout.addWidget(tree_title)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setObjectName("structureTree")
        self.tree_widget.setHeaderLabels(["Name", "Size", "Value", "Description", "Warnings"])
        self.tree_widget.setColumnWidth(0, 150)
        self.tree_widget.setColumnWidth(1, 80)
        self.tree_widget.setColumnWidth(2, 150)
        self.tree_widget.setMinimumHeight(350)
        self.tree_widget.itemDoubleClicked.connect(self._on_tree_double_clicked)
        tree_layout.addWidget(self.tree_widget)

        binwalk_frame = QFrame()
        binwalk_frame.setObjectName("card")
        binwalk_layout = QVBoxLayout(binwalk_frame)
        binwalk_layout.setContentsMargins(15, 15, 15, 15)
        binwalk_layout.setSpacing(10)

        binwalk_title = QLabel("Embedded Signatures")
        binwalk_title.setObjectName("cardTitle")
        binwalk_layout.addWidget(binwalk_title)

        self.binwalk_list = QListWidget()
        self.binwalk_list.setObjectName("binwalkList")
        self.binwalk_list.setMinimumHeight(150)
        binwalk_layout.addWidget(self.binwalk_list)

        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.addWidget(tree_frame)
        left_splitter.addWidget(binwalk_frame)
        left_splitter.setSizes([500, 200])
        left_layout.addWidget(left_splitter)

        content_layout.addWidget(left_container, stretch=7)

        # --- Right: anomalies (clickable -> jump to the tree node) ---
        right_container = QFrame()
        right_container.setObjectName("summaryCard")
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(10)

        summary_title = QLabel("Anomalies Detected")
        summary_title.setObjectName("cardTitle")
        right_layout.addWidget(summary_title)

        self.summary_hint = QLabel("Click a finding to locate it in the structure tree.")
        self.summary_hint.setObjectName("hintLabel")
        self.summary_hint.setWordWrap(True)
        right_layout.addWidget(self.summary_hint)

        self.summary_list = QListWidget()
        self.summary_list.setObjectName("summaryList")
        self.summary_list.setWordWrap(True)
        self.summary_list.itemClicked.connect(self._on_summary_clicked)
        self.summary_list.itemActivated.connect(self._on_summary_clicked)
        right_layout.addWidget(self.summary_list)

        content_layout.addWidget(right_container, stretch=3)

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

    # ---------------- data ----------------
    def load_data(self, data: dict):
        self.tree_widget.clear()
        self.binwalk_list.clear()
        self.summary_list.clear()
        self._suspicious_items = []
        self._overlay_item = None

        structure_analysis = data.get("structure_analysis", {})
        if not structure_analysis:
            self.summary_hint.hide()
            return
        self.summary_hint.show()

        hachoir_raw = structure_analysis.get("hachoir_raw", {})
        self._populate_tree(hachoir_raw.get("structure", []), self.tree_widget)
        self.tree_widget.expandAll()

        # Appended data lives *after* the parsed structure, so the tree parser never sees it.
        # Add a synthetic node for it so the user can see (and hex-preview) the hidden bytes.
        overlay_info = structure_analysis.get("overlay_analysis", {})
        if overlay_info.get("has_overlay"):
            self._overlay_item = self._add_overlay_node(overlay_info)

        binwalk_raw = structure_analysis.get("binwalk_raw", {})
        signatures = binwalk_raw.get("signatures", [])
        if not signatures:
            item = QListWidgetItem("No embedded signatures found.")
            item.setForeground(QBrush(QColor(GRAY)))
            self.binwalk_list.addItem(item)
        else:
            for sig in signatures:
                self.binwalk_list.addItem(f"Offset 0x{sig.get('offset', 0):X} : {sig.get('description', 'Unknown')}")

        self._build_summary(structure_analysis)

    def _add_overlay_node(self, overlay_info: dict) -> QTreeWidgetItem:
        size = overlay_info.get("overlay_size_bytes", 0)
        offset = overlay_info.get("overlay_offset")
        b64 = overlay_info.get("preview_b64", "")
        snippet = _ascii_snippet(base64.b64decode(b64)) if b64 else ""

        item = QTreeWidgetItem(self.tree_widget)
        item.setText(0, "[Appended data]")
        item.setText(1, str(size))
        item.setText(2, snippet)
        item.setText(3, f"Bytes after the file's real end (offset 0x{offset:X})" if offset is not None
                     else "Bytes after the file's real end")
        item.setText(4, "Overlay — double-click to preview")
        for col in range(5):
            item.setForeground(col, QBrush(QColor(RED)))
        item.setData(0, BYTES_ROLE, {"b64": b64, "size": size})
        return item

    def _populate_tree(self, chunks: list, parent_item):
        for chunk in chunks:
            value = chunk.get("value", "")
            if len(value) > 100:
                value = value[:100] + "..."

            item = QTreeWidgetItem(parent_item)
            item.setText(0, chunk.get("name", ""))
            item.setText(1, str(chunk.get("size_bytes", "")))
            item.setText(2, value)
            item.setText(3, chunk.get("description", ""))
            item.setText(4, chunk.get("suspicious_reason", ""))

            if chunk.get("is_suspicious", False):
                red = QBrush(QColor(RED))
                for col in range(5):
                    item.setForeground(col, red)
                self._suspicious_items.append(item)

            sub_chunks = chunk.get("sub_chunks", [])
            if isinstance(sub_chunks, list) and sub_chunks:
                self._populate_tree(sub_chunks, item)

    def _build_summary(self, structure_analysis: dict):
        anomaly = False

        overlay_info = structure_analysis.get("overlay_analysis", {})
        if overlay_info.get("has_overlay"):
            size = overlay_info.get("overlay_size_bytes", 0)
            self._add_summary(f"Found {size} bytes of hidden data appended after the file's real end",
                              RED, target=self._overlay_item)
            anomaly = True

        if structure_analysis.get("has_suspicious_chunks"):
            count = structure_analysis.get("suspicious_chunk_count", 0)
            target = self._suspicious_items[0] if self._suspicious_items else None
            self._add_summary(f"Detected {count} non-standard data chunk(s)", RED, target=target)
            anomaly = True

        for a in structure_analysis.get("integrity_anomalies", []):
            self._add_summary(a.get("detail", "Structural integrity anomaly"), RED)
            anomaly = True

        if not anomaly:
            self._add_summary("No structural anomalies detected.", GREEN)

    def _add_summary(self, text: str, color: str, target: QTreeWidgetItem = None):
        prefix = "›  " if target is not None else "•  "
        item = QListWidgetItem(prefix + text)
        item.setForeground(QBrush(QColor(color)))
        if target is not None:
            item.setData(NAV_ROLE, target)
            item.setToolTip("Click to locate in the structure tree")
        self.summary_list.addItem(item)

    # ---------------- interaction ----------------
    def _on_summary_clicked(self, item: QListWidgetItem):
        target = item.data(NAV_ROLE)
        if isinstance(target, QTreeWidgetItem):
            self._navigate_to(target)

    def _navigate_to(self, tree_item: QTreeWidgetItem):
        parent = tree_item.parent()
        while parent:
            parent.setExpanded(True)
            parent = parent.parent()
        self.tree_widget.setCurrentItem(tree_item)
        self.tree_widget.scrollToItem(tree_item, QTreeWidget.ScrollHint.PositionAtCenter)
        self.tree_widget.setFocus()

    def _on_tree_double_clicked(self, item: QTreeWidgetItem, _col: int):
        payload = item.data(0, BYTES_ROLE)
        if payload and payload.get("b64"):
            data = base64.b64decode(payload["b64"])
            ExtractPreviewDialog("Appended data (overlay)", data, payload.get("size", len(data)),
                                 payload.get("size", len(data)) > len(data), self).exec()
