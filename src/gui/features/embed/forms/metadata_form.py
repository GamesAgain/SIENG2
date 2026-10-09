"""
Metadata input form: pick a target file, then edit its metadata.

Card "Target File" (drop zone) -> after a file is chosen, switch to its editor (PNG or MP3).
The form never writes the file; the Standalone tab saves get_entries() itself.
(The pipeline's Previous Output is added later.)
"""
from pathlib import Path

from mutagen import MutagenError
from PyQt6.QtCore import QSignalBlocker, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QStackedWidget, QVBoxLayout

from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap
from src.gui.components.widgets.files_drop import FileDropWidget
from src.gui.features.embed.forms.metadata.mp3_form import MP3MetadataForm
from src.gui.features.embed.forms.metadata.png_form import PNGMetadataForm
from src.path import svg_path

ICON_SIZE = 16


class MetadataInputForm(QFrame):

    target_file_changed = pyqtSignal(str)  # path ของไฟล์ที่เปิดอยู่ ("" = ยังไม่ได้เลือก)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_file_path: str | None = None
        self.setup_ui()

    # --- UI construction ---

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 11, 0, 0)

        self.target_card = self.build_target_file_card()
        self.png_form = PNGMetadataForm()
        self.mp3_form = MP3MetadataForm()
        self.forms = {".png": self.png_form, ".mp3": self.mp3_form}  # นามสกุล -> editor
        for form in self.forms.values():
            form.change_file_requested.connect(self.reset_target)

        # หน้าเลือกไฟล์ <-> หน้าแก้ metadata
        self.target_stack = QStackedWidget()
        self.target_stack.addWidget(self.target_card)
        self.target_stack.addWidget(self.png_form)
        self.target_stack.addWidget(self.mp3_form)
        main_layout.addWidget(self.target_stack, 1)

    def build_target_file_card(self) -> QFrame:
        target_card = QFrame()
        target_card.setObjectName("card")
        add_shadow_effect(target_card)

        target_layout = QVBoxLayout(target_card)
        target_layout.setContentsMargins(10, 10, 10, 10)

        title_container = QFrame()
        title_layout = QHBoxLayout(title_container)
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(svg_path("photo-video.svg"), size=ICON_SIZE))
        title_label = QLabel("Target File (PNG, MP3)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.target_drop_zone = FileDropWidget(
            text="Drop PNG or MP3 file here or click to browse",
            sub_text="Opens the file's metadata for editing",
            icon_path=str(svg_path("photo-video.svg")),
            allowed_extensions=[".png", ".mp3"],
            show_preview=False,
        )
        self.target_drop_zone.file_selected.connect(self.on_target_file_selected)

        target_layout.addWidget(title_container)
        target_layout.addWidget(self.target_drop_zone, 1)
        return target_card

    # --- Actions ---

    def on_target_file_selected(self, file_path: str):
        if not file_path or file_path == self.target_file_path:
            return

        form = self.forms.get(Path(file_path).suffix.lower())
        try:
            if form is None:
                raise ValueError("Please select a PNG or MP3 file.")
            form.load_file(file_path)
        except (OSError, ValueError, MutagenError) as error:
            self.reset_target()
            QMessageBox.warning(self, "Cannot read file", str(error))
            return

        self.target_file_path = file_path
        self.target_stack.setCurrentWidget(form)
        self.target_file_changed.emit(file_path)

    def reset_target(self):
        """Back to the drop zone; the edits of the previous file are discarded."""
        self.target_file_path = None
        with QSignalBlocker(self.target_drop_zone):  # clear_all() ส่ง file_selected("") ไม่ต้องรับซ้ำ
            self.target_drop_zone.clear_all()
        for form in self.forms.values():
            form.clear_all()
        self.target_stack.setCurrentWidget(self.target_card)
        self.target_file_changed.emit("")

    # --- Input API ---

    def current_form(self) -> PNGMetadataForm | MP3MetadataForm | None:
        if not self.target_file_path:
            return None
        return self.forms[Path(self.target_file_path).suffix.lower()]

    def get_entries(self) -> dict:
        """Checked values of the open file ({keyword: text} for PNG, {key: MP3Field} for MP3). Raises ValueError."""
        form = self.current_form()
        if form is None:
            raise ValueError("Please select a target PNG or MP3 file.")
        return form.get_entries()

    def key_labels(self, keys: list[str]) -> list[str]:
        """Readable names of saved keys, for messages."""
        form = self.current_form()
        return form.key_labels(keys) if form else list(keys)
