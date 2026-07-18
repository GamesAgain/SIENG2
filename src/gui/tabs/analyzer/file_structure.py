import base64
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QSplitter, QListWidget, QListWidgetItem, QHBoxLayout,
    QScrollArea, QWidget, QAbstractItemView, QLineEdit, QSpinBox,
    QCheckBox, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QProgressBar, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush
from src.core.analyzer.docker_bridge import strings_scan, carve
from src.gui.tabs.analyzer.zsteg_card import ExtractPreviewDialog
from src.gui.components.strings_scan import is_interesting
from src.gui.components.worker import FuncWorker

RED = "#f43f5e"
GREEN = "#34D399"
GRAY = "#94A3B8"
BLUE = "#38BDF8"
STR_MAX_ROWS = 2000  # cap the strings table so a huge file doesn't build a giant widget

# GNU strings `-e` encodings, as (label, value) for the picker.
STR_ENCODINGS = [
    ("ASCII (7-bit)", "ascii"),
    ("8-bit / UTF-8", "8bit"),
    ("UTF-16 LE", "utf16le"),
    ("UTF-16 BE", "utf16be"),
]
NAV_ROLE = Qt.ItemDataRole.UserRole      # summary item -> the tree item it points at
BYTES_ROLE = Qt.ItemDataRole.UserRole + 1  # tree item -> {"b64", "size"} for the hex preview


def _ascii_snippet(data: bytes, n: int = 60) -> str:
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data[:n])


class FileStructureTab(QFrame):
    def __init__(self):
        super().__init__()
        self._suspicious_items = []
        self._overlay_item = None
        self._file_path = None
        self._all_strings = []
        self._str_encoding = "ascii"
        self._str_worker = None
        self._carve_worker = None
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
        outer = QVBoxLayout(scroll_content)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        top_row = QWidget()
        content_layout = QHBoxLayout(top_row)
        content_layout.setContentsMargins(0, 0, 0, 0)
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
        # QTreeWidget headers default to left-aligned text, unlike QTableWidget's centered
        # default - center here so the header row matches every other table in the app.
        self.tree_widget.header().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
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

        # Carving: the list above only reports that files are embedded - this pulls them out.
        carve_row = QHBoxLayout()
        self.carve_btn = QPushButton("Extract Embedded Files…")
        self.carve_btn.setObjectName("SecondaryBtn")
        self.carve_btn.setEnabled(False)
        self.carve_btn.clicked.connect(self._on_carve_clicked)
        carve_row.addWidget(self.carve_btn)

        self.carve_progress = QProgressBar()
        self.carve_progress.setRange(0, 0)
        self.carve_progress.setTextVisible(False)
        self.carve_progress.setFixedSize(90, 6)
        self.carve_progress.hide()
        carve_row.addWidget(self.carve_progress)

        self.carve_status = QLabel("")
        self.carve_status.setObjectName("hintLabel")
        carve_row.addWidget(self.carve_status)
        carve_row.addStretch()
        binwalk_layout.addLayout(carve_row)

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
        # NoSelection: clicking still fires itemClicked (to navigate) but never selects the row,
        # so a finding's red/green foreground is never overwritten by the selection highlight.
        self.summary_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.summary_list.itemClicked.connect(self._on_summary_clicked)
        right_layout.addWidget(self.summary_list)

        content_layout.addWidget(right_container, stretch=3)

        outer.addWidget(top_row)
        outer.addWidget(self._build_strings_card())

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

    def _build_strings_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(15, 15, 15, 15)
        lay.setSpacing(10)

        title = QLabel("Strings")
        title.setObjectName("cardTitle")
        lay.addWidget(title)

        hint = QLabel("GNU <b>strings</b> over the raw bytes — finds plaintext hidden in an appended "
                      "overlay, a metadata chunk, or padding. Compressed pixel data yields mostly "
                      "coincidental runs, so raise <b>Min length</b> or use the filters to find real text.")
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        # `-n` / `-e` are scan parameters, so they only take effect on an explicit Scan - running
        # the tool on every spinner tick fired a Docker call per keystroke.
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Min length:"))
        self.str_minlen = QSpinBox()
        self.str_minlen.setRange(1, 64)
        self.str_minlen.setValue(6)
        self.str_minlen.setFixedWidth(60)
        controls.addWidget(self.str_minlen)

        self.str_enc = QComboBox()
        for label, _value in STR_ENCODINGS:
            self.str_enc.addItem(label)
        controls.addWidget(self.str_enc)

        self.str_scan_btn = QPushButton("Scan")
        self.str_scan_btn.setObjectName("PrimaryActionBtn")
        self.str_scan_btn.clicked.connect(self._fetch_strings)
        controls.addWidget(self.str_scan_btn)

        self.str_progress = QProgressBar()
        self.str_progress.setRange(0, 0)  # indeterminate
        self.str_progress.setTextVisible(False)
        self.str_progress.setFixedSize(90, 6)
        self.str_progress.hide()
        controls.addWidget(self.str_progress)

        self.str_search = QLineEdit()
        self.str_search.setObjectName("formInput")
        self.str_search.setPlaceholderText("Filter strings…")
        self.str_search.textChanged.connect(self._render_strings)
        controls.addWidget(self.str_search, 1)

        self.str_interesting = QCheckBox("Interesting only")
        self.str_interesting.toggled.connect(self._render_strings)
        controls.addWidget(self.str_interesting)

        self.str_count = QLabel("")
        self.str_count.setObjectName("hintLabel")
        controls.addWidget(self.str_count)
        lay.addLayout(controls)

        self.str_table = QTableWidget(0, 3)
        self.str_table.setObjectName("darkTable")
        self.str_table.setHorizontalHeaderLabels(["Offset", "Enc", "String"])
        self.str_table.verticalHeader().setVisible(False)
        self.str_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        h = self.str_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.str_table.setMinimumHeight(220)
        lay.addWidget(self.str_table)

        return card

    def set_target_file(self, file_path: str):
        """Point the Strings scanner at the current file. Scanning is user-triggered (Scan) -
        it's a separate Docker call and can be slow on large files, so it doesn't ride along
        with Run Analysis."""
        self._file_path = file_path
        self._all_strings = []
        self.str_table.setRowCount(0)
        self.str_scan_btn.setEnabled(bool(file_path))
        self.str_count.setText("Click Scan to search the file for text" if file_path else "")
        self.carve_btn.setEnabled(bool(file_path))
        self.carve_status.setText("")

    # ---------------- carving ----------------
    def _on_carve_clicked(self):
        if not self._file_path or (self._carve_worker and self._carve_worker.isRunning()):
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Extract embedded files to…")
        if not out_dir:
            return
        self._set_carve_busy(True)
        self._carve_worker = FuncWorker(carve, self._file_path, out_dir)
        self._carve_worker.done.connect(lambda res, d=out_dir: self._on_carve_done(res, d))
        self._carve_worker.start()

    def _set_carve_busy(self, busy: bool):
        self.carve_btn.setEnabled(not busy)
        self.carve_progress.setVisible(busy)
        if busy:
            self.carve_status.setText("Extracting…")

    def _on_carve_done(self, result: dict, out_dir: str):
        self._set_carve_busy(False)
        if not isinstance(result, dict) or result.get("error"):
            self.carve_status.setText("")
            QMessageBox.critical(self, "Extraction Failed",
                                 result.get("error", "Unknown error") if isinstance(result, dict)
                                 else "Unknown error")
            return
        files = result.get("extracted", [])
        if not files:
            self.carve_status.setText("Nothing extractable found")
            return
        self.carve_status.setText(f"{len(files)} file(s) extracted")
        listing = "\n".join(f"  {f['name']}  ({f['size']} bytes)" for f in files[:20])
        more = f"\n  … and {len(files) - 20} more" if len(files) > 20 else ""
        QMessageBox.information(self, "Files Extracted",
                                f"{len(files)} file(s) written to:\n{out_dir}\n\n{listing}{more}")

    def _fetch_strings(self):
        """Run GNU strings in the analyzer container, off the UI thread."""
        if not self._file_path or (self._str_worker and self._str_worker.isRunning()):
            return
        self._str_encoding = STR_ENCODINGS[self.str_enc.currentIndex()][1]
        self._set_strings_busy(True)
        self._str_worker = FuncWorker(strings_scan, self._file_path,
                                      min_len=self.str_minlen.value(), encoding=self._str_encoding)
        self._str_worker.done.connect(self._on_strings_done)
        self._str_worker.start()

    def _set_strings_busy(self, busy: bool):
        for w in (self.str_minlen, self.str_enc, self.str_scan_btn):
            w.setEnabled(not busy)
        self.str_progress.setVisible(busy)
        if busy:
            self.str_count.setText("Scanning…")

    def _on_strings_done(self, result: dict):
        self._set_strings_busy(False)
        if not isinstance(result, dict) or result.get("error"):
            self._all_strings = []
            self.str_table.setRowCount(0)
            self.str_count.setText((result or {}).get("error", "strings failed")
                                   if isinstance(result, dict) else "strings failed")
            return
        self._all_strings = result.get("strings", [])
        self._str_truncated = result.get("truncated", False)
        self._render_strings()

    def _render_strings(self):
        query = self.str_search.text().lower()
        only_interesting = self.str_interesting.isChecked()
        rows = []
        for entry in self._all_strings:
            text = entry.get("text", "")
            if only_interesting and not is_interesting(text):
                continue
            if query and query not in text.lower():
                continue
            rows.append((entry.get("offset", 0), text))
            if len(rows) >= STR_MAX_ROWS:
                break

        self.str_table.setRowCount(len(rows))
        for i, (off, text) in enumerate(rows):
            self.str_table.setRowHeight(i, 24)
            self.str_table.setItem(i, 0, QTableWidgetItem(f"0x{off:X}"))
            self.str_table.setItem(i, 1, QTableWidgetItem(self._str_encoding))
            item = QTableWidgetItem(text)
            if is_interesting(text):
                item.setForeground(QBrush(QColor(BLUE)))
            self.str_table.setItem(i, 2, item)

        total = len(self._all_strings)
        note = " (capped)" if len(rows) >= STR_MAX_ROWS or getattr(self, "_str_truncated", False) else ""
        self.str_count.setText(f"{len(rows)} shown / {total} total{note}")

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
        """Label the appended bytes as a single red, previewable node. hachoir usually already
        emits a trailing raw[] node for the same bytes - reuse it instead of adding a duplicate."""
        size = overlay_info.get("overlay_size_bytes", 0)
        offset = overlay_info.get("overlay_offset")
        b64 = overlay_info.get("preview_b64", "")
        snippet = _ascii_snippet(base64.b64decode(b64)) if b64 else ""

        item = None
        root = self.tree_widget.invisibleRootItem()
        if root.childCount():
            last = root.child(root.childCount() - 1)
            if last.text(0).startswith("raw") and last.text(1) == str(size):
                item = last  # hachoir's own trailing raw[] node for the appended bytes
        if item is None:
            item = QTreeWidgetItem(self.tree_widget)
            item.setText(2, snippet)

        item.setText(0, "[Appended data]")
        item.setText(1, str(size))
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
            # skip hachoir's parser-artifact placeholder rows (optional fields that are absent)
            if value == "<MissingField>" and not chunk.get("sub_chunks"):
                continue
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
