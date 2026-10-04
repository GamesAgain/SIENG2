from copy import deepcopy

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QScrollArea, QTabWidget, QVBoxLayout

from src.gui.components.widgets.file_info_bar import FileInfoBar
from src.gui.features.embed.forms.metadata.file_info import get_mp3_file_info
from src.gui.features.embed.forms.metadata.mp3_draft import MP3MetadataDraft, read_mp3_draft
from src.gui.features.embed.forms.metadata.tabs.mp3_text_frames import MP3TextFramesForm
from src.gui.features.embed.forms.metadata.tabs.mp3_attached_picture import MP3AttachedPictureForm
from src.gui.components.gui_utils import create_icon_state
from src.path import svg_path


class MP3MetadataForm(QFrame):
    """MP3 summary, Text Frames and Attached Picture controls."""

    change_file_requested = pyqtSignal()

    def __init__(self, parent=None, *, is_config: bool = False):
        super().__init__(parent)
        self.loaded_draft = MP3MetadataDraft()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.file_info_bar = FileInfoBar()
        layout.addWidget(self.file_info_bar)
        self.file_info_bar.change_file_requested.connect(self.change_file_requested.emit)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("siengTabs")
        self.tabs.setIconSize(QSize(16, 16))
        self.text_frames_form = MP3TextFramesForm()
        self.text_scroll = QScrollArea()
        self.text_scroll.setObjectName("fileListScroll")
        self.text_scroll.setWidgetResizable(True)
        self.text_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_scroll.setWidget(self.text_frames_form)
        self.attached_picture_form = MP3AttachedPictureForm(is_config=is_config)
        self.picture_scroll = QScrollArea()
        self.picture_scroll.setObjectName("fileListScroll")
        self.picture_scroll.setWidgetResizable(True)
        self.picture_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.picture_scroll.setWidget(self.attached_picture_form)
        self.attached_picture_form.edit_started.connect(
            lambda: self.picture_scroll.ensureWidgetVisible(self.attached_picture_form.editor_title)
        )
        self.tabs.addTab(self.text_scroll, create_icon_state(str(svg_path("text-size.svg"))), "Text Frames")
        self.tabs.addTab(self.picture_scroll, create_icon_state(str(svg_path("photo.svg"))), "Attached Picture")
        layout.addWidget(self.tabs, 1)

    def clear_all(self) -> None:
        self.loaded_draft = MP3MetadataDraft()
        self.text_frames_form.clear_all()
        self.attached_picture_form.clear_all()
        self.tabs.setCurrentIndex(0)

    def load_file(self, file_path: str) -> None:
        info = get_mp3_file_info(file_path)
        draft = read_mp3_draft(file_path)
        self.load_draft(draft)
        self.file_info_bar.update_info(**info)

    def load_draft(self, draft: MP3MetadataDraft) -> None:
        self.text_frames_form.load_draft(draft.text_frames)
        self.attached_picture_form.load_draft(draft.attached_pictures)
        self.loaded_draft = deepcopy(draft)
        self.tabs.setCurrentIndex(0)

    def get_inputs(self) -> MP3MetadataDraft:
        draft = deepcopy(self.loaded_draft)
        draft.text_frames = self.text_frames_form.get_inputs()
        draft.attached_pictures = self.attached_picture_form.get_inputs()
        return draft
