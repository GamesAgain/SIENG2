"""
Inside of the "Extract Plan" card: the plan file (extract_pipeline.yaml) and the final files the receiver adds.

The page decides what is shown (it reads the plan and matches the files); this widget only shows it and sends
what the user dropped. Same parts as the other pages: FileDropWidget / FileInfoBar / fileItemRow.
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

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
}


class FinalFileRow(QFrame):
    """One final file of the plan: icon by state, name, and how it was matched."""

    def __init__(self, name: str, state: str, detail: str, parent=None):
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


class ExtractPlanPanel(QFrame):
    plan_selected = pyqtSignal(str)          # path of the extract_pipeline.yaml the user chose
    change_plan_requested = pyqtSignal()
    final_files_added = pyqtSignal(list)     # paths the user dropped (the page matches them to the plan)

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
        self.plan_bar.change_file_requested.connect(self.change_plan_requested.emit)
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

        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(6)
        layout.addLayout(self.rows_layout)
        self.files_hint = QLabel("Open an extract plan to see the files you need.")
        self.files_hint.setObjectName("hintLabel")
        self.files_hint.setWordWrap(True)
        layout.addWidget(self.files_hint)
        layout.addStretch()

    # --- What the page shows ---
    def show_plan(self, file_path: str, name: str, detail: str) -> None:
        """name: the pipeline name (or the file name) · detail: e.g. 'YAML · 4 steps · 3 final files'"""
        self.plan_bar.update_info(file_path, truncate_text_middle(name, NAME_LIMIT), detail, [],
                                  icon_path=str(svg_path("file-text.svg")))
        self.plan_bar.file_name.setToolTip(name)
        self.plan_drop.hide()
        self.plan_bar.show()
        self.files_drop.setEnabled(True)
        self.files_hint.hide()

    def clear_plan(self) -> None:
        self.plan_bar.hide()
        self.plan_drop.show()
        self.files_drop.setEnabled(False)  # nothing to match before a plan is read
        self.set_final_files([])
        self.files_hint.show()

    def set_final_files(self, files: list[tuple[str, str, str]]) -> None:
        """files: (name, state, detail) per final file of the plan; state is a key of FILE_STATES."""
        while self.rows_layout.count():
            row = self.rows_layout.takeAt(0).widget()
            if row is not None:
                row.hide()
                row.deleteLater()
        for name, state, detail in files:
            self.rows_layout.addWidget(FinalFileRow(name, state, detail))
        found = sum(state != "missing" for _, state, _ in files)
        self.files_count.setText(f"{found} of {len(files)}" if files else "")
