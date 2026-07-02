
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget
from pathlib import Path

from src.gui.components.file_drop import FileDropWidget
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap
from src.gui.tabs.embed.metadata_mp3_editor import MP3MetadataEditor
from src.gui.tabs.embed.metadata_png_editor import PNGMetadataEditor
from src.gui.tabs.metadata_shared import FileInfoBar, get_file_display_info

ICON_DIR = Path(__file__).parent.parent.parent / "assets" / "svg"
ICON_SIZE = 14

class MetadataEmbedTab(QFrame):
    def __init__(self):
        super().__init__()

        self.cover_file = None

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 11, 4, 4)

        self.cover_file_stack = QStackedWidget()
        cover_dropfile_card = self.build_cover_file_card()
        cover_file_selected_card = self.build_cover_file_selected_card()

        self.cover_file_stack.addWidget(cover_dropfile_card)
        self.cover_file_stack.addWidget(cover_file_selected_card)
        main_layout.addWidget(self.cover_file_stack)

    def build_cover_file_card(self):
        card_frame = QFrame()
        card_frame.setObjectName("card")
        add_shadow_effect(card_frame)

        main_layout = QVBoxLayout(card_frame)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)

        # Icon
        title_icon = QLabel()
        photo_icon = create_icon_pixmap(ICON_DIR / "photo-video.svg", size=16)
        title_icon.setPixmap(photo_icon)

        # Text: Cover File (PNG, MP3)
        title_label = QLabel("Target File (PNG, MP3)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.drop_zone = FileDropWidget("Drop PNG, MP3 files here or click to browse", "Supports PNG, MP3 format only", allowed_extensions=[".png", ".mp3"])
        self.drop_zone.file_selected.connect(self.on_cover_file_selected)

        main_layout.addWidget(title_container, 0) # top
        main_layout.addWidget(self.drop_zone, 1) # Stretch factor

        return card_frame

    def build_cover_file_selected_card(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.file_info_bar = FileInfoBar()
        self.file_info_bar.change_file_requested.connect(self.on_change_file_clicked)
        layout.addWidget(self.file_info_bar)

        # MP3: ตัว editor เต็มรูปแบบ (Text Frames / Images tab)
        self.mp3_editor = MP3MetadataEditor()
        self.mp3_editor.hide()
        layout.addWidget(self.mp3_editor)

        # PNG: editor สำหรับ iTXt text chunks (Standard / Custom metadata)
        self.png_editor = PNGMetadataEditor()
        self.png_editor.hide()
        layout.addWidget(self.png_editor)

        return container

    # --- Event Handler ---
    def on_cover_file_selected(self, file_path: str):
        self.cover_file = file_path
        info = get_file_display_info(file_path)
        self.file_info_bar.update_info(info)

        is_mp3 = Path(file_path).suffix.lower() == ".mp3"
        self.mp3_editor.setVisible(is_mp3)
        self.png_editor.setVisible(not is_mp3)
        if is_mp3:
            self.mp3_editor.load_file(file_path)
        else:
            self.png_editor.load_file(file_path)

        self.cover_file_stack.setCurrentIndex(1)

    def on_change_file_clicked(self):
        self.drop_zone.clear_file()
        self.cover_file = None
        self.cover_file_stack.setCurrentIndex(0)
