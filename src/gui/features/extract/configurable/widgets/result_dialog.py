"""
View Result of one extracted step.

- Text (LSB++ / Locomotive text): like the Locomotive result card's Text page (Copy / Export .txt)
- Hidden fields (Metadata): like Extract Metadata's View All (FieldRow per field, picture cards for MP3 pictures)
- Files (Locomotive files): like the Locomotive result card's Files page (preview row + Save As, Save All)
"""
import shutil
from pathlib import Path

from PyQt6.QtCore import QFileInfo, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFileIconProvider, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from src.core.configurable.extract_plan import ExtractResult, PlanStep
from src.core.stego.metadata_handlers.mp3_handler import key_label
from src.core.stego.metadata_handlers.png_handler import PNG_TEXT_KEYWORDS
from src.gui.components.gui_utils import format_file_size, truncate_text_middle
from src.gui.features.embed.configurable.constants import TECHNIQUE_DISPLAY
from src.gui.features.extract.forms.metadata_form import FieldRow, PictureResultCard


def make_button(text: str, slot) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("SecondaryBtn")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.clicked.connect(slot)
    return button


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("cardTitle")
    return label


class ResultFileRow(QFrame):
    """A recovered file: preview (or the system icon), name, size, which step uses it, Save As."""

    def __init__(self, name: str, path: Path, used_by: str = "", parent=None):
        super().__init__(parent)
        self.name, self.path = name, path
        self.setObjectName("fileItemRow")
        self.setFixedHeight(64)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        icon = QLabel()
        icon.setFixedSize(40, 40)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview = QPixmap(str(path))
        if not preview.isNull():
            icon.setPixmap(preview.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            icon.setPixmap(QFileIconProvider().icon(QFileInfo(name)).pixmap(32, 32))
        text = QVBoxLayout()
        text.setSpacing(2)
        name_label = QLabel(truncate_text_middle(name, max_length=40))
        name_label.setObjectName("fileItemName")
        name_label.setToolTip(name)
        detail = format_file_size(path.stat().st_size) + (f" · {used_by}" if used_by else "")
        size_label = QLabel(detail)
        size_label.setObjectName("fileItemSize")
        text.addWidget(name_label)
        text.addWidget(size_label)
        layout.addWidget(icon)
        layout.addLayout(text, 1)
        layout.addWidget(make_button("Save As...", self.save_as))

    def save_as(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save extracted file", self.name, "All files (*)")
        if not filename:
            return
        try:
            shutil.copyfile(self.path, filename)  # the exact bytes: a stego file can still be extracted further
        except OSError as error:
            QMessageBox.warning(self, "Save Extracted File", str(error))


class ExtractResultDialog(QDialog):
    """
    step / number: the plan step and the number the receiver sees · result: what extract_step gave
    used_by: recovered file name -> 'Used by Step 4' (the page knows which step needs it)
    """

    def __init__(self, step: PlanStep, number: int, result: ExtractResult, used_by: dict[str, str] | None = None,
                 parent=None):
        super().__init__(parent)
        self.result = result
        self.used_by = used_by or {}
        label = TECHNIQUE_DISPLAY[step.technique]["label"]
        self.setObjectName("metadataViewAllDialog")  # same background as Extract Metadata's View All
        self.setWindowTitle(f"Step {number} · {label} — Result")
        self.resize(720, 560)

        layout = QVBoxLayout(self)
        if step.description:
            note = QLabel(step.description)
            note.setObjectName("hintLabel")
            note.setWordWrap(True)
            layout.addWidget(note)

        content = QWidget()
        content.setObjectName("fileListContainer")
        self.rows_layout = QVBoxLayout(content)
        self.rows_layout.setSpacing(10)
        if result.text is not None:
            self.add_text()
        if result.fields:
            self.add_fields(step)
        pictures = {name: field for name, field in result.pictures.items() if name in result.files}
        if pictures:
            self.add_pictures(pictures)
        files = {name: path for name, path in result.files.items() if name not in pictures}
        if files:
            self.add_files(files)
        if self.rows_layout.count() == 0:
            empty = QLabel("This step gave nothing.")
            empty.setObjectName("hintLabel")
            self.rows_layout.addWidget(empty)
        self.rows_layout.addStretch()

        scroll = QScrollArea()
        scroll.setObjectName("fileListScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        close_button = make_button("Close", self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

    # --- Text: like the Locomotive Text page ---
    def add_text(self):
        self.rows_layout.addWidget(section_title("Text"))
        self.text_area = QPlainTextEdit(self.result.text)
        self.text_area.setObjectName("payloadTextArea")
        self.text_area.setReadOnly(True)
        self.text_area.setMinimumHeight(160)
        self.rows_layout.addWidget(self.text_area)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(make_button("Copy", lambda: QApplication.clipboard().setText(self.result.text)))
        actions.addWidget(make_button("Export .txt", self.export_text))
        self.rows_layout.addLayout(actions)

    def export_text(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Export extracted text", "extracted.txt", "Text files (*.txt)")
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".txt":
            path = path.with_suffix(".txt")
        try:
            path.write_text(self.result.text, encoding="utf-8", newline="")
        except OSError as error:
            QMessageBox.warning(self, "Export Text", str(error))

    # --- Hidden fields: like Extract Metadata's View All (every field here is one the sender hid) ---
    def add_fields(self, step: PlanStep):
        self.rows_layout.addWidget(section_title(f"Hidden Fields ({len(self.result.fields)})"))
        is_mp3 = any(need.file.lower().endswith(".mp3") for need in step.needs)
        for key, value in self.result.fields.items():
            if is_mp3:
                row = FieldRow(key_label(key), key.split(":")[0], value, payload=True)
            else:
                row = FieldRow(PNG_TEXT_KEYWORDS.get(key, (key, ""))[0], key, value, payload=True)
            self.rows_layout.addWidget(row)

    def add_pictures(self, pictures: dict):
        self.rows_layout.addWidget(section_title(f"Attached Pictures ({len(pictures)})"))
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for index, (name, picture) in enumerate(pictures.items()):
            card = PictureResultCard(picture, index + 1, payload=True)
            if name in self.used_by:
                card.setToolTip(f"{name} · {self.used_by[name]}")
            grid.addWidget(card, index // 2, index % 2)
        self.rows_layout.addWidget(holder)

    # --- Files: like the Locomotive Files page ---
    def add_files(self, files: dict[str, Path]):
        header = QHBoxLayout()
        header.addWidget(section_title(f"Files ({len(files)})"))
        header.addStretch()
        if len(files) > 1:
            header.addWidget(make_button("Save All...", lambda: self.save_all(files)))
        self.rows_layout.addLayout(header)
        canvas = QFrame()
        canvas.setObjectName("pipelineCanvas")
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(8, 8, 8, 8)
        canvas_layout.setSpacing(8)
        for name, path in files.items():
            canvas_layout.addWidget(ResultFileRow(name, path, self.used_by.get(name, "")))
        self.rows_layout.addWidget(canvas)

    def save_all(self, files: dict[str, Path]):
        directory = QFileDialog.getExistingDirectory(self, "Save all extracted files")
        if not directory:
            return
        existing = [name for name in files if (Path(directory) / name).exists()]
        if existing and QMessageBox.question(
            self, "Replace files?", f"{', '.join(existing)} already exist. Replace them?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            for name, path in files.items():
                shutil.copyfile(path, Path(directory) / name)
        except OSError as error:
            QMessageBox.warning(self, "Save Extracted Files", str(error))
