from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QIcon, QTransform
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView
)
from src.gui.components.gui_utils import create_icon_pixmap

ICON_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "svg"

RED = "#EF4444"
YELLOW = "#EAB308"
GREEN = "#10B981"
GRAY = "#94A3B8"


def _is_filesystem(key: str) -> bool:
    """File-system / derived attributes that change on ANY re-save (size, dates, permissions,
    computed composites) - not where a payload hides. Kept out of the signal by default."""
    k = key.lower()
    return k.startswith(("file:", "system:", "composite:")) or k in ("sourcefile", "directory")


class MetaDiffTab(QFrame):
    """Metadata cover-vs-stego diff. Leads with the genuine signal - embedded fields that were
    added / changed / removed - and hides the re-save noise (filesystem dates/size, unchanged
    fields) behind a toggle, so a real hidden-in-metadata payload isn't buried in a wall of rows."""

    def __init__(self):
        super().__init__()
        self._rows = []          # (property, cover, stego, status, color, category)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(15, 15, 15, 15)
        card_layout.setSpacing(10)

        title = QLabel("Metadata Comparison")
        title.setObjectName("cardTitle")
        card_layout.addWidget(title)

        self.verdict_banner = QLabel("Run a comparison to diff the two files' metadata.")
        self.verdict_banner.setWordWrap(True)
        self._style_banner(GRAY)
        card_layout.addWidget(self.verdict_banner)

        self._chevron = create_icon_pixmap(str(ICON_DIR / "chevron-down.svg"), "#818D9F", size=14)
        self.toggle = QPushButton("Show unchanged / filesystem fields")
        self.toggle.setObjectName("SecondaryBtn")
        self.toggle.setCheckable(True)
        self.toggle.setIcon(QIcon(self._chevron))
        self.toggle.toggled.connect(self._on_toggle)
        card_layout.addWidget(self.toggle, alignment=Qt.AlignmentFlag.AlignLeft)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName("darkTable")
        self.table.setHorizontalHeaderLabels(
            ["Property", "Original (Cover)", "Suspicious (Stego)", "Status"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        card_layout.addWidget(self.table)

        layout.addWidget(card)

    def _style_banner(self, color: str):
        c = QColor(color)
        self.verdict_banner.setStyleSheet(
            f"padding: 10px 12px; border-radius: 6px; "
            f"background: rgba({c.red()},{c.green()},{c.blue()},0.12); color: {color};")

    def _on_toggle(self, checked: bool):
        pix = self._chevron.transformed(QTransform().rotate(180)) if checked else self._chevron
        self.toggle.setIcon(QIcon(pix))
        self._render()

    def load_data(self, meta_diff: dict):
        self._rows = []
        changed = meta_diff.get("changed", {})
        added = meta_diff.get("added", {})
        removed = meta_diff.get("removed", {})
        unchanged = meta_diff.get("unchanged", {})

        signal = 0  # genuine embedded-metadata changes (the thing that matters)

        for k, v in changed.items():
            if _is_filesystem(k):
                self._rows.append((k, str(v.get("original", "")), str(v.get("stego", "")),
                                   "changed (re-save)", GRAY, "fs"))
            else:
                self._rows.append((k, str(v.get("original", "")), str(v.get("stego", "")),
                                   "CHANGED", YELLOW, "signal"))
                signal += 1
        for k, v in added.items():
            cat = "fs" if _is_filesystem(k) else "signal"
            self._rows.append((k, "—", str(v), "added (re-save)" if cat == "fs" else "ADDED",
                               GRAY if cat == "fs" else RED, cat))
            if cat == "signal":
                signal += 1
        for k, v in removed.items():
            cat = "fs" if _is_filesystem(k) else "signal"
            self._rows.append((k, str(v), "—", "removed (re-save)" if cat == "fs" else "REMOVED",
                               GRAY if cat == "fs" else RED, cat))
            if cat == "signal":
                signal += 1
        for k, v in unchanged.items():
            if _is_filesystem(k):
                continue
            self._rows.append((k, str(v), str(v), "unchanged", None, "unchanged"))

        # verdict
        if signal:
            self.verdict_banner.setText(
                f"<b>{signal} embedded metadata field(s) differ</b> — a payload may be hidden in "
                f"the file's metadata. Filesystem dates/size were excluded (they change on any re-save).")
            self._style_banner(RED)
        else:
            self.verdict_banner.setText(
                "<b>No embedded-metadata differences</b> — only filesystem attributes changed, "
                "which is expected on any re-save.")
            self._style_banner(GREEN)

        self._render()

    def _render(self):
        show_all = self.toggle.isChecked()
        self.table.clearSpans()
        self.table.setRowCount(0)
        for prop, cover, stego, status, color, cat in sorted(self._rows, key=self._sort_key):
            if cat in ("fs", "unchanged") and not show_all:
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            for col, text in enumerate((prop, cover, stego, status)):
                item = QTableWidgetItem(text)
                if color:
                    item.setForeground(QBrush(QColor(color)))
                self.table.setItem(r, col, item)

        if self.table.rowCount() == 0:
            self.table.insertRow(0)
            empty = QTableWidgetItem("No embedded-metadata changes.")
            empty.setForeground(QBrush(QColor(GREEN)))
            self.table.setItem(0, 0, empty)
            self.table.setSpan(0, 0, 1, 4)

    @staticmethod
    def _sort_key(row):
        # signal rows first, then filesystem, then unchanged; alphabetical within each
        order = {"signal": 0, "fs": 1, "unchanged": 2}
        return (order.get(row[5], 3), row[0].lower())
