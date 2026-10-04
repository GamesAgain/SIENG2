from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QStackedWidget, QVBoxLayout

from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap
from src.gui.components.widgets.files_drop import FileDropWidget
from src.gui.components.widgets.selection_toggle import SelectionToggle
from src.gui.features.embed.forms.metadata.mp3_form import MP3MetadataForm
from src.gui.features.embed.forms.metadata.png_form import PNGMetadataForm
from src.path import svg_path


ICON_SIZE = 16


class MetadataInputForm(QFrame):
    """Select a Metadata target and show its format-specific placeholder."""

    target_file_changed = pyqtSignal(str)

    def __init__(self, is_config: bool = False, parent=None):
        super().__init__(parent)
        self.is_config = is_config
        self.target_file_path: str | None = None
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 11, 0, 0)
        self.target_stack = QStackedWidget()
        self.target_card = self.build_target_file_card()
        self.png_form = PNGMetadataForm()
        self.mp3_form = MP3MetadataForm(is_config=self.is_config)
        self.target_stack.addWidget(self.target_card)
        self.target_stack.addWidget(self.png_form)
        self.target_stack.addWidget(self.mp3_form)
        main_layout.addWidget(self.target_stack, 1)

        self.cover_drop_zone.file_selected.connect(self.on_target_file_selected)
        self.png_form.change_file_requested.connect(self.change_target_file)
        self.mp3_form.change_file_requested.connect(self.change_target_file)

    def on_target_file_selected(self, file_path: str) -> None:
        if not file_path:
            self.target_file_path = None
            self.png_form.clear_all()
            self.mp3_form.clear_all()
            self.target_stack.setCurrentWidget(self.target_card)
            self.target_file_changed.emit("")
            return

        extension = Path(file_path).suffix.lower()
        form = {".png": self.png_form, ".mp3": self.mp3_form}.get(extension)
        try:
            if form is None:
                raise ValueError("Please select a PNG or MP3 file.")
            form.load_file(file_path)
        except Exception as error:
            self.change_target_file()
            QMessageBox.warning(self, "Cannot read file", str(error))
            return

        self.target_file_path = file_path
        self.target_stack.setCurrentWidget(form)
        self.target_file_changed.emit(file_path)

    def change_target_file(self) -> None:
        self.target_file_path = None
        self.cover_drop_zone.clear_file()
        self.target_stack.setCurrentWidget(self.target_card)

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

        self.cover_mode_toggle = SelectionToggle([
            {
                "text": "Manual File",
                "value": "Manual",
                "variant": "source",
                "color_checked": "#38BDF8",
            },
            {
                "text": "Previous Output",
                "value": "linked",
                "variant": "source",
                "color_checked": "#38BDF8",
            },
        ])
        self.cover_mode_toggle.setVisible(self.is_config)

        self.cover_drop_zone = FileDropWidget(
            text="Drop PNG or MP3 file here or click to browse",
            sub_text="Supports PNG and MP3 formats only",
            icon_path=str(svg_path("photo-video.svg")),
            allowed_extensions=[".png", ".mp3"],
            show_preview=False,
        )

        target_layout.addWidget(title_container)
        target_layout.addWidget(self.cover_mode_toggle)
        target_layout.addWidget(self.cover_drop_zone, 1)
        return target_card
