"""
Metadata input form: pick a target file, then edit its metadata.

Card "Target File" (drop zone) -> after a PNG is chosen, switch to PNGMetadataForm.
The form never writes the file; the Standalone tab saves get_entries() itself.
(MP3 and the pipeline's Previous Output are added later.)
"""
from PyQt6.QtCore import QSignalBlocker, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QStackedWidget, QVBoxLayout

from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap
from src.gui.components.widgets.files_drop import FileDropWidget
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
        self.png_form.change_file_requested.connect(self.reset_target)

        # หน้าเลือกไฟล์ <-> หน้าแก้ metadata
        self.target_stack = QStackedWidget()
        self.target_stack.addWidget(self.target_card)
        self.target_stack.addWidget(self.png_form)
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
        title_icon.setPixmap(create_icon_pixmap(svg_path("photo.svg"), size=ICON_SIZE))
        title_label = QLabel("Target File (PNG)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.target_drop_zone = FileDropWidget(
            text="Drop PNG file here or click to browse",
            sub_text="Opens the file's text metadata for editing",
            icon_path=str(svg_path("photo.svg")),
            allowed_extensions=[".png"],
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

        try:
            self.png_form.load_file(file_path)
        except (OSError, ValueError) as error:
            self.reset_target()
            QMessageBox.warning(self, "Cannot read file", str(error))
            return

        self.target_file_path = file_path
        self.target_stack.setCurrentWidget(self.png_form)
        self.target_file_changed.emit(file_path)

    def reset_target(self):
        """Back to the drop zone; the edits of the previous file are discarded."""
        self.target_file_path = None
        with QSignalBlocker(self.target_drop_zone):  # clear_all() ส่ง file_selected("") ไม่ต้องรับซ้ำ
            self.target_drop_zone.clear_all()
        self.png_form.clear_all()
        self.target_stack.setCurrentWidget(self.target_card)
        self.target_file_changed.emit("")

    # --- Input API ---

    def get_entries(self) -> dict[str, str]:
        """Checked keyword/value pairs of the open file. Raises ValueError."""
        if not self.target_file_path:
            raise ValueError("Please select a target PNG file.")
        return self.png_form.get_entries()
