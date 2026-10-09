"""
MP3 metadata editor: file summary + receiver preview + "Text Frames" / "Attached Pictures" tabs.

Same API as PNGMetadataForm, but the values are {key: MP3Field}:
- original : frames of the file when it was opened (to see what the user added or modified)
- entries  : every frame the user wants the file to have (frames outside the editor are kept by the core)
"""
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QScrollArea, QTabWidget, QVBoxLayout

from src.core.stego.metadata_handlers.mp3_handler import MetadataMP3Handler, MP3Field, key_label
from src.gui.components.gui_utils import create_icon_state
from src.gui.components.widgets.file_info_bar import FileInfoBar
from src.gui.features.embed.forms.metadata.common import PAYLOAD_REQUIRED, SecretPreview
from src.gui.features.embed.forms.metadata.file_info import get_mp3_file_info
from src.gui.features.embed.forms.metadata.mp3_pictures import MP3PicturesForm
from src.gui.features.embed.forms.metadata.mp3_text_frames import MP3TextFramesForm
from src.path import svg_path


def make_scroll(widget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName("fileListScroll")
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(widget)
    return scroll


class MP3MetadataForm(QFrame):

    change_file_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.handler = MetadataMP3Handler()
        self.original: dict[str, MP3Field] = {}
        self.build_ui()
        self.update_preview()

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.file_info_bar = FileInfoBar()
        self.file_info_bar.change_file_requested.connect(self.change_file_requested.emit)
        layout.addWidget(self.file_info_bar)

        self.secret_preview = SecretPreview()
        layout.addWidget(self.secret_preview)

        self.text_form = MP3TextFramesForm()
        self.pictures_form = MP3PicturesForm()
        self.text_form.changed.connect(self.update_preview)
        self.pictures_form.changed.connect(self.update_preview)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("siengTabs")
        self.tabs.setIconSize(QSize(16, 16))
        self.tabs.addTab(make_scroll(self.text_form), create_icon_state(str(svg_path("text-size.svg"))), "Text Frames")
        picture_scroll = make_scroll(self.pictures_form)
        self.tabs.addTab(picture_scroll, create_icon_state(str(svg_path("photo.svg"))), "Attached Pictures [0]")
        self.pictures_form.count_changed.connect(lambda count: self.tabs.setTabText(1, f"Attached Pictures [{count}]"))
        # กด Edit ที่การ์ด -> เลื่อนลงไปที่ editor ด้านล่าง
        self.pictures_form.edit_started.connect(lambda: picture_scroll.ensureWidgetVisible(self.pictures_form.editor_title))
        layout.addWidget(self.tabs, 1)

    # --- Values ---

    def load_file(self, file_path: str) -> None:
        """Read the MP3 and fill the form. Raises (OSError / ValueError) if the file cannot be read."""
        info = get_mp3_file_info(file_path)
        fields = self.handler.read_frames(file_path)
        hidden_before = list(self.handler.read_secret(file_path))

        self.set_original(fields)
        self.set_entries(fields)
        self.file_info_bar.update_info(**info)
        self.secret_preview.show_previous_secret(self.key_labels(hidden_before))
        self.tabs.setCurrentIndex(0)

    def set_original(self, original: dict[str, MP3Field]) -> None:
        """The frames to compare against (what the file has before this edit)."""
        self.original = dict(original)
        self.update_preview()

    def set_entries(self, entries: dict[str, MP3Field]) -> None:
        self.text_form.set_fields([field for field in entries.values() if field.frame_id != "APIC"])
        self.pictures_form.set_pictures([field for field in entries.values() if field.frame_id == "APIC"])
        self.update_preview()

    def current_entries(self) -> dict[str, MP3Field]:
        """What the form shows now, without checking (used for the live preview)."""
        fields = self.text_form.get_fields() + self.pictures_form.current_pictures()
        return {field.key: field for field in fields}

    def get_entries(self) -> dict[str, MP3Field]:
        """Checked frames to save. Raises ValueError with a message for the user."""
        fields = self.text_form.get_fields() + self.pictures_form.get_pictures()
        entries = {}
        for field in fields:
            if field.key in entries:
                raise ValueError(f"{key_label(field.key)} is used more than once. Change its description or language.")
            self.handler.check_field(field.key, field)
            entries[field.key] = field
        if not self.handler.changed_keys(self.original, entries):
            raise ValueError(PAYLOAD_REQUIRED)
        return entries

    def clear_all(self) -> None:
        self.set_entries({})
        self.set_original({})
        self.secret_preview.show_previous_secret([])
        self.tabs.setCurrentIndex(0)

    # --- Messages ---

    def update_preview(self) -> None:
        """Receiver preview + PAYLOAD marks on the frames / pictures that were added or modified."""
        changed = self.handler.changed_keys(self.original, self.current_entries())
        self.text_form.mark_payload(set(changed))
        self.pictures_form.mark_payload(set(changed))
        self.secret_preview.show_changes(self.key_labels(changed))

    def key_labels(self, keys: list[str]) -> list[str]:
        """'COMM:note:eng' -> 'Comment "note" (eng)'"""
        return [key_label(key) for key in keys]
