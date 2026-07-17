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
YELLOW = "#f59e0b"
GREEN = "#10B981"
GRAY = "#94A3B8"
NAV_ROLE = Qt.ItemDataRole.UserRole       # summary item -> the tree item it points at
BYTES_ROLE = Qt.ItemDataRole.UserRole + 1  # tree item -> {"b64", "size"} for the hex preview


def _ascii_snippet(data: bytes, n: int = 60) -> str:
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data[:n])


class StructDiffTab(QFrame):
    """Structural cover-vs-stego diff. LSB embedding re-encodes the pixel stream, so every image
    -data block differs at the byte level - a naive per-block diff would scream "hundreds of
    modified chunks" for any re-saved file. This tab ignores that re-encode noise and reports only
    container-level changes that actually indicate hidden data."""

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

        # --- Left: stego structure tree + embedded signatures ---
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        tree_frame = QFrame()
        tree_frame.setObjectName("card")
        tree_layout = QVBoxLayout(tree_frame)
        tree_layout.setContentsMargins(15, 15, 15, 15)
        tree_layout.setSpacing(10)

        tree_title = QLabel("Internal Structure (Stego File)")
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

        binwalk_title = QLabel("Embedded Signatures (Stego File)")
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

        # --- Right: verdict + meaningful findings ---
        right_container = QFrame()
        right_container.setObjectName("summaryCard")
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(10)

        summary_title = QLabel("Structural Comparison")
        summary_title.setObjectName("cardTitle")
        right_layout.addWidget(summary_title)

        self.verdict_banner = QLabel("Run a comparison to diff the two files' structure.")
        self.verdict_banner.setWordWrap(True)
        self._style_banner(GRAY)
        right_layout.addWidget(self.verdict_banner)

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

    def _style_banner(self, color: str):
        c = QColor(color)
        self.verdict_banner.setStyleSheet(
            f"padding: 10px 12px; border-radius: 6px; "
            f"background: rgba({c.red()},{c.green()},{c.blue()},0.12); color: {color};")

    def load_data(self, struct_diff: dict):
        self.tree_widget.clear()
        self.binwalk_list.clear()
        self.summary_list.clear()

        self._suspicious_items = []
        self._overlay_item = None

        if not struct_diff:
            self._style_banner(GRAY)
            self.verdict_banner.setText("Run a comparison to diff the two files' structure.")
            self.summary_hint.hide()
            return
        self.summary_hint.show()

        orig_res = struct_diff.get("original", {})
        stego_res = struct_diff.get("stego", {})

        stego_chunks = stego_res.get("hachoir_raw", {}).get("structure", [])
        # highlight only chunks the analyzer itself flags as non-standard/suspicious, not re-encoded blocks
        self._populate_tree(stego_chunks, self.tree_widget)
        self.tree_widget.expandAll()

        # Appended data lives after the parsed structure - add a synthetic node so the user can see
        # (and hex-preview) the hidden bytes, but only when it's new/grown vs the cover.
        s_ov, o_ov = stego_res.get("overlay_analysis", {}), orig_res.get("overlay_analysis", {})
        if s_ov.get("has_overlay") and s_ov.get("overlay_size_bytes", 0) > o_ov.get("overlay_size_bytes", 0):
            self._overlay_item = self._add_overlay_node(s_ov)

        orig_sigs = orig_res.get("binwalk_raw", {}).get("signatures", [])
        stego_sigs = stego_res.get("binwalk_raw", {}).get("signatures", [])
        self._populate_binwalk(stego_sigs, orig_sigs, self.binwalk_list)

        self._build_summary(orig_res, stego_res)

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
            name = chunk.get("name", "")
            size = str(chunk.get("size_bytes", ""))
            value = chunk.get("value", "")
            desc = chunk.get("description", "")
            reason = chunk.get("suspicious_reason", "")

            if len(value) > 100:
                value = value[:100] + "..."

            item = QTreeWidgetItem(parent_item)
            item.setText(0, name)
            item.setText(1, size)
            item.setText(2, value)
            item.setText(3, desc)
            item.setText(4, reason)

            if chunk.get("is_suspicious"):
                brush = QBrush(QColor(RED))
                for col in range(5):
                    item.setForeground(col, brush)
                self._suspicious_items.append(item)

            sub = chunk.get("sub_chunks", [])
            if isinstance(sub, list) and sub:
                self._populate_tree(sub, item)

    def _populate_binwalk(self, stego_sigs, orig_sigs, list_widget):
        if not stego_sigs:
            item = QListWidgetItem("No embedded signatures found.")
            item.setForeground(QBrush(QColor(GRAY)))
            list_widget.addItem(item)
            return
        orig_offsets = {s.get("offset", 0) for s in orig_sigs}
        for sig in stego_sigs:
            offset = sig.get("offset", 0)
            desc = sig.get("description", "Unknown")
            item = QListWidgetItem(f"Offset 0x{offset:X} : {desc}")
            if offset not in orig_offsets:
                item.setForeground(QBrush(QColor(RED)))  # signature only in the stego file
            list_widget.addItem(item)

    def _build_summary(self, orig_res: dict, stego_res: dict):
        findings = []  # (text, color, target_tree_item_or_None)
        first_susp = self._suspicious_items[0] if self._suspicious_items else None

        # 1. Overlay / appended data
        o_ov, s_ov = orig_res.get("overlay_analysis", {}), stego_res.get("overlay_analysis", {})
        if s_ov.get("has_overlay") and not o_ov.get("has_overlay"):
            findings.append((f"{s_ov.get('overlay_size_bytes', 0)} bytes appended after the file's "
                             f"real end (only in stego)", RED, self._overlay_item))
        elif s_ov.get("has_overlay") and o_ov.get("has_overlay"):
            so, ss = o_ov.get("overlay_size_bytes", 0), s_ov.get("overlay_size_bytes", 0)
            if ss > so:
                findings.append((f"overlay grew from {so} to {ss} bytes (+{ss - so})", YELLOW,
                                 self._overlay_item))

        # 2. Non-standard / suspicious chunks the analyzer flagged (stego gained some). This is the
        #    analyzer's own vetted signal - it already knows tEXt/zTXt/injected chunks from image
        #    data, so we trust it instead of byte-diffing the re-encoded chunk stream ourselves.
        o_susp = orig_res.get("suspicious_chunk_count", 0)
        s_susp = stego_res.get("suspicious_chunk_count", 0)
        if s_susp > o_susp:
            findings.append((f"{s_susp - o_susp} non-standard chunk(s) added in stego", RED, first_susp))

        # 3. Integrity anomalies present in stego but not cover
        o_int = {a.get("detail") for a in orig_res.get("integrity_anomalies", [])}
        for a in stego_res.get("integrity_anomalies", []):
            if a.get("detail") not in o_int:
                findings.append((a.get("detail", "integrity anomaly"), RED, None))

        # 4. New embedded-file signatures
        o_sig = len(orig_res.get("binwalk_raw", {}).get("signatures", []))
        s_sig = len(stego_res.get("binwalk_raw", {}).get("signatures", []))
        if s_sig > o_sig:
            findings.append((f"{s_sig - o_sig} new embedded file signature(s) in stego", RED, None))

        # verdict + list
        if findings:
            self.verdict_banner.setText("<b>Container-level anomaly found</b> — the stego file's "
                                        "structure differs from the original in a meaningful way.")
            self._style_banner(RED)
            for text, color, target in findings:
                self._add_summary(text, color, target)
        else:
            self.verdict_banner.setText("<b>Structure matches the original</b> — no container-level "
                                        "anomaly. (Pixel data was re-encoded, which is expected and "
                                        "not shown as a difference.)")
            self._style_banner(GREEN)
            self._add_summary("No appended data, new chunks, or integrity anomalies.", GREEN)

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
