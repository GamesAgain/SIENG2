"""
Inside of the "Extract Plan" card: the plan file (extract_pipeline.yaml) and the final files the receiver adds.

The page decides what is shown (it reads the plan and matches the files); this widget only shows it and sends
what the user dropped. Same parts as the other pages: FileDropWidget / FileInfoBar / fileItemRow.
"""
from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from src.gui.components.gui_utils import create_icon_pixmap, truncate_text_middle
from src.gui.components.widgets.file_info_bar import FileInfoBar
from src.gui.components.widgets.files_drop import FileDropWidget, MultiFileDropWidget
from src.path import svg_path

NAME_LIMIT = 32  # long pipeline / file names are cut in the middle (the tooltip keeps the full name)

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


class ExtractPlanPanel(QFrame):
    plan_selected = pyqtSignal(str)          # path of the extract_pipeline.yaml the user chose
    change_plan_requested = pyqtSignal()
    final_files_added = pyqtSignal(list)     # paths the user dropped (the page matches them to the plan)
    remove_file_requested = pyqtSignal(str)  # the x on a row: the page decides (it may ask first), then removes it

    def __init__(self, parent=None):
        super().__init__(parent)
        self.build_ui()
        self.clear_plan()

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 16)
        layout.setSpacing(10)

        # 1. Plan file: a drop zone before a plan is read, then its summary with Change
        self.plan_drop = FileDropWidget(
            "Drop extract_pipeline.yaml here or click to browse",
            "Made by Run Pipeline on the sender's side",
            icon_path=str(svg_path("file-import.svg")),
            allowed_extensions=[".yaml", ".yml"],
            show_preview=False,
        )
        self.plan_drop.setFixedHeight(110)
        self.plan_drop.file_selected.connect(lambda path: path and self.plan_selected.emit(path))
        self.plan_bar = FileInfoBar()
        self.plan_bar.change_file_button.setText("Change")
        self.plan_bar.change_file_requested.connect(self.on_change_plan)
        layout.addWidget(self.plan_drop)
        layout.addWidget(self.plan_bar)

        divider = QFrame()
        divider.setObjectName("stepCardDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        layout.addWidget(divider)

        # 2. Final files: one drop zone for all of them, then one row per file of the plan
        header = QHBoxLayout()
        title = QLabel("Final Files")
        title.setObjectName("cardTitle")
        self.files_count = QLabel()
        self.files_count.setObjectName("hintLabel")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.files_count)
        layout.addLayout(header)

        self.files_drop = MultiFileDropWidget(
            "Drop files here or click to browse",
            "PNG / MP3 · matched by content, then by name",
            icon_path=str(svg_path("upload.svg")),
            allowed_extensions=[".png", ".mp3"],
            show_preview=False,  # the rows below show the plan's files instead
        )
        self.files_drop.setFixedHeight(110)
        self.files_drop.files_changed.connect(self.final_files_added.emit)
        layout.addWidget(self.files_drop)

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
        self.files_hint = QLabel("Open an extract plan to see the files you need.")
        self.files_hint.setObjectName("hintLabel")
        self.files_hint.setWordWrap(True)
        layout.addWidget(self.files_hint)

    def on_change_plan(self) -> None:
        """Change = take the plan out: back to the drop zone (the page clears the steps and the files)."""
        self.plan_drop.clear_all()  # so choosing the same file again is still noticed
        self.plan_bar.hide()
        self.plan_drop.show()
        self.change_plan_requested.emit()

    # --- What the page shows ---
    def show_plan(self, file_path: str, name: str, detail: str) -> None:
        """name: the pipeline name (or the file name) · detail: e.g. 'YAML · 4 steps · 3 final files'"""
        self.plan_bar.update_info(file_path, truncate_text_middle(name, NAME_LIMIT), detail, [],
                                  icon_path=str(svg_path("file-text.svg")))
        self.plan_bar.file_name.setToolTip(name)
        self.plan_drop.clear_all()
        self.plan_drop.hide()
        self.plan_bar.show()
        self.files_drop.setEnabled(True)
        self.files_hint.hide()

    def clear_plan(self) -> None:
        self.plan_bar.hide()
        self.plan_drop.show()
        self.files_drop.setEnabled(False)  # nothing to match before a plan is read
        with QSignalBlocker(self.files_drop):  # forget the dropped files without telling the page again
            self.files_drop.clear_all()
        self.set_final_files([])
        self.files_hint.show()

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
