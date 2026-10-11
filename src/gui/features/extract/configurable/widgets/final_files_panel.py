"""
Inside of the "Stego Files" card: the final embed outputs the receiver adds, and one row per file of the plan.

The page decides what is shown (it matches the files to the plan); this widget only shows it and sends
what the user dropped. The count ("2 of 3") is a label the page puts in the card's title row.
"""
from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from src.gui.components.gui_utils import create_icon_pixmap, truncate_text_middle
from src.gui.components.widgets.files_drop import MultiFileDropWidget
from src.path import svg_path

NAME_LIMIT = 32  # long file names are cut in the middle (the tooltip keeps the full name)

# state of a final file -> (icon, colour of the icon and the detail)
FILE_STATES = {
    "matched": ("check.svg", "#4ADE80"),   # same content as the sender's file
    "renamed": ("check.svg", "#4ADE80"),   # same content, another name
    "changed": ("check.svg", "#F59E0F"),   # same name, other content (used with a warning)
    "missing": ("file.svg", "#64748B"),    # not added yet
    "unknown": ("x.svg", "#64748B"),       # a dropped file that is not in the plan (not used)
    "replaced": ("x.svg", "#64748B"),      # a dropped file with a plan file's name, while a better match is used
}
UNUSED_STATES = ("unknown", "replaced")    # rows of dropped files that are not the plan's files


class FinalFileRow(QFrame):
    """One final file: icon by state, name, how it was matched, and a remove button when a real file is behind it."""

    remove_requested = pyqtSignal(str)  # path of the dropped file

    def __init__(self, name: str, state: str, detail: str, path: str | None = None, parent=None):
        super().__init__(parent)
        icon_name, color = FILE_STATES[state]
        self.setObjectName("fileItemRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        icon = QLabel()
        icon.setPixmap(create_icon_pixmap(svg_path(icon_name), color, 16))
        text = QVBoxLayout()
        text.setSpacing(1)
        name_label = QLabel(truncate_text_middle(name, NAME_LIMIT))
        name_label.setObjectName("fileItemName")
        name_label.setToolTip(name)
        detail_label = QLabel(detail)
        detail_label.setObjectName("fileItemSize")
        detail_label.setStyleSheet(f"color: {color};")
        detail_label.setWordWrap(True)
        text.addWidget(name_label)
        text.addWidget(detail_label)
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text, 1)
        if path:  # a plan file that is not added yet has nothing to remove
            self.remove_button = QPushButton()
            self.remove_button.setObjectName("btnRemoveFile")
            self.remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.remove_button.setFixedSize(28, 28)
            self.remove_button.setIcon(QIcon(create_icon_pixmap(svg_path("x.svg"), "#f43f5e", 14)))
            self.remove_button.setToolTip("Remove this file")
            self.remove_button.clicked.connect(lambda: self.remove_requested.emit(path))
            layout.addWidget(self.remove_button, 0, Qt.AlignmentFlag.AlignVCenter)


class FinalFilesPanel(QFrame):
    final_files_added = pyqtSignal(list)     # paths the user dropped (the page matches them to the plan)
    remove_file_requested = pyqtSignal(str)  # the x on a row: the page decides (it may ask first), then removes it

    def __init__(self, parent=None):
        super().__init__(parent)
        self.build_ui()
        self.clear()

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 16)
        layout.setSpacing(8)

        self.files_count = QLabel()  # "2 of 3": the page puts it in the card's title row
        self.files_count.setObjectName("hintLabel")

        # One drop zone for all of them, then one row per file of the plan
        self.files_drop = MultiFileDropWidget(
            "Drop stego files here or click to browse",
            "Supports one or multiple PNG or MP3 files",
            icon_path=str(svg_path("upload.svg")),
            allowed_extensions=[".png", ".mp3"],
            show_preview=False,  # the rows below show the plan's files instead
        )
        self.files_drop.main_label.setWordWrap(True)
        self.files_drop.sub_label.setWordWrap(True)
        self.files_drop.drop_layout.setAlignment(self.files_drop.main_label, Qt.AlignmentFlag.AlignVCenter)
        self.files_drop.drop_layout.setAlignment(self.files_drop.sub_label, Qt.AlignmentFlag.AlignVCenter)
        self.files_drop.setFixedHeight(120)
        self.files_drop.files_changed.connect(self.final_files_added.emit)
        layout.addWidget(self.files_drop)

        self.files_empty = QFrame()
        self.files_empty.setObjectName("extractFilesEmpty")
        self.files_empty.setMinimumHeight(100)
        empty_layout = QVBoxLayout(self.files_empty)
        empty_layout.setContentsMargins(10, 10, 10, 10)
        empty_layout.setSpacing(4)
        empty_layout.addStretch()
        empty_icon = QLabel()
        empty_icon.setPixmap(create_icon_pixmap(svg_path("file-dots.svg"), "#64748B", 20))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)
        empty_title = QLabel("No files added yet")
        empty_title.setObjectName("extractFilesEmptyTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title.setWordWrap(True)
        empty_layout.addWidget(empty_title)
        empty_detail = QLabel("Added files will appear here after you select them.")
        empty_detail.setObjectName("hintLabel")
        empty_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_detail.setWordWrap(True)
        empty_layout.addWidget(empty_detail)
        empty_layout.addStretch()
        layout.addWidget(self.files_empty, 1)

        # The rows scroll inside the card when the plan has many files
        rows = QWidget()
        rows.setObjectName("transparentScrollContent")
        self.rows_layout = QVBoxLayout(rows)
        self.rows_layout.setContentsMargins(0, 0, 4, 0)  # room for the scrollbar
        self.rows_layout.setSpacing(6)
        self.rows_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.rows_scroll = QScrollArea()
        self.rows_scroll.setObjectName("transparentScroll")
        self.rows_scroll.setWidgetResizable(True)
        self.rows_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rows_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.rows_scroll.setWidget(rows)
        layout.addWidget(self.rows_scroll, 1)
        self.files_hint_frame = QFrame()
        self.files_hint_frame.setObjectName("extractFilesHint")
        hint_layout = QHBoxLayout(self.files_hint_frame)
        hint_layout.setContentsMargins(10, 4, 10, 4)
        hint_layout.setSpacing(8)
        hint_icon = QLabel()
        hint_icon.setPixmap(create_icon_pixmap(svg_path("file-search.svg"), "#94A3B8", 16))
        hint_layout.addWidget(hint_icon)
        self.files_hint = QLabel("File requirements will appear after loading a plan.")
        self.files_hint.setObjectName("hintLabel")
        self.files_hint.setWordWrap(True)
        hint_layout.addWidget(self.files_hint, 1)
        layout.addWidget(self.files_hint_frame)

    # --- What the page shows ---
    def set_plan_open(self, is_open: bool) -> None:
        """Nothing to match before a plan is read. Only the drop zone is disabled: the page's busy lock uses setEnabled on this panel."""
        self.files_drop.setEnabled(is_open)
        self.files_hint_frame.setVisible(not is_open)

    def clear(self) -> None:
        with QSignalBlocker(self.files_drop):  # forget the dropped files without telling the page again
            self.files_drop.clear_all()
        self.set_final_files([])
        self.set_plan_open(False)

    def set_final_files(self, files: list[tuple[str, str, str, str | None]]) -> None:
        """files: (name, state, detail, path) per row: the plan's files, then the dropped files that are not used.
        state is a key of FILE_STATES; path = the dropped file (None for a plan file that is not added yet)."""
        while self.rows_layout.count():
            row = self.rows_layout.takeAt(0).widget()
            if row is not None:
                row.hide()
                row.deleteLater()
        for name, state, detail, path in files:
            row = FinalFileRow(name, state, detail, path)
            row.remove_requested.connect(self.remove_file_requested.emit)
            self.rows_layout.addWidget(row)
        needed = [state for _, state, _, _ in files if state not in UNUSED_STATES]  # the plan's files only
        found = sum(state != "missing" for state in needed)
        self.files_count.setText(f"{found} of {len(needed)}" if needed else "")
        self.files_empty.setVisible(not files)
        self.rows_scroll.setVisible(bool(files))
