"""
Metadata extract: open a PNG / MP3 and show the fields the sender added or modified (the SIENG2 field list).
View All shows every field in the file; the ones the sender hid are marked PAYLOAD.
Metadata is plain text (no password), so the result shows as soon as a file is chosen.
"""
import mimetypes
from pathlib import Path

from mutagen import MutagenError
from PyQt6.QtCore import QSignalBlocker, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from src.core.stego.metadata_handlers.mp3_handler import (
    APIC_TYPES, FRAME_INFO, MetadataMP3Handler, MP3Field, key_label,
)
from src.core.stego.metadata_handlers.png_handler import PNG_TEXT_KEYWORDS, MetadataPNGHandler
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, format_file_size
from src.gui.components.widgets.file_info_bar import FileInfoBar
from src.gui.components.widgets.files_drop import FileDropWidget
from src.gui.features.embed.forms.metadata.common import (
    make_badge, make_card_header, make_payload_badge, make_value_input, set_payload_mark,
)
from src.gui.features.embed.forms.metadata.file_info import get_mp3_file_info, get_png_file_info
from src.path import svg_path

ICON_SIZE = 16
TINTS = ["blue", "purple", "green", "orange"]


def picture_summary(picture: MP3Field) -> str:
    return f"Type {picture.picture_type} {APIC_TYPES.get(picture.picture_type, 'Unknown')} · {picture.mime} · {format_file_size(len(picture.data))}"


class FieldRow(QFrame):
    """Read-only field: name + key badge (+ PAYLOAD in View All) + value + Copy."""

    def __init__(self, name: str, key: str, value: str, payload: bool = False, copyable: bool = True, parent=None):
        super().__init__(parent)
        self.value = value
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)
        label = QLabel(name)
        label.setObjectName("formLabel")
        header.addWidget(label)
        header.addWidget(make_badge(key))
        payload_badge = make_payload_badge()
        payload_badge.setVisible(payload)
        header.addWidget(payload_badge)
        header.addStretch()
        copy_button = QPushButton("Copy")
        copy_button.setObjectName("SecondaryBtn")
        copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.value))
        copy_button.setVisible(copyable)  # แถวสรุปรูปภาพไม่มีอะไรให้คัดลอก
        header.addWidget(copy_button)
        layout.addLayout(header)

        # ข้อความหลายบรรทัด (เช่นเนื้อเพลง) ใช้กล่องหลายบรรทัด ที่เหลือใช้ช่องบรรทัดเดียว
        if "\n" in value:
            box = QPlainTextEdit(value)
            box.setObjectName("payloadTextArea")
            box.setFixedHeight(80)
        else:
            box = make_value_input(text=value)
            box.setCursorPosition(0)
        box.setReadOnly(True)
        set_payload_mark(box, payload)
        layout.addWidget(box)


class PictureResultCard(QFrame):
    """A hidden picture (APIC): preview, type, description, size and Save Image (the exact bytes, never re-encoded)."""

    def __init__(self, picture: MP3Field, number: int, parent=None):
        super().__init__(parent)
        self.picture = picture
        self.setObjectName("apicCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        preview = QFrame()
        preview.setObjectName("apicPreview")
        preview.setProperty("tintColor", TINTS[(number - 1) % len(TINTS)])
        preview.setFixedHeight(120)
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        badge = QLabel(f"Type {picture.picture_type} — {APIC_TYPES.get(picture.picture_type, 'Unknown')}")
        badge.setObjectName("fileInfoBadge")
        badge.setProperty("badgeColor", "blue")
        type_row = QHBoxLayout()
        type_row.addWidget(badge)
        type_row.addStretch()
        preview_layout.addLayout(type_row)
        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap()
        if pixmap.loadFromData(picture.data):
            pixmap = pixmap.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        else:
            pixmap = create_icon_pixmap(svg_path("photo.svg"), size=28)
        image.setPixmap(pixmap)
        preview_layout.addWidget(image, 1)
        layout.addWidget(preview)

        body = QFrame()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(10, 8, 10, 10)
        title = QLabel(f'"{picture.desc}"')
        title.setObjectName("fileInfoName")
        body_layout.addWidget(title)
        detail = QLabel(f"{picture.mime} · {format_file_size(len(picture.data))}")
        detail.setObjectName("fileInfoDetail")
        body_layout.addWidget(detail)
        save_button = QPushButton("Save Image")
        save_button.setObjectName("SecondaryBtn")
        save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        save_button.clicked.connect(self.save_image)
        body_layout.addWidget(save_button)
        layout.addWidget(body)

    def save_image(self):
        # ไบต์ภาพเดิมทุกไบต์: ถ้าเป็น PNG stego ก็นำไปถอด LSB++ / Locomotive ต่อได้
        extension = mimetypes.guess_extension(self.picture.mime) or ".bin"
        default_name = f"{self.picture.desc or 'picture'}{extension}"
        filename, _ = QFileDialog.getSaveFileName(self, "Save Image", default_name, f"Image (*{extension})")
        if not filename:
            return
        try:
            Path(filename).write_bytes(self.picture.data)
        except OSError as error:
            QMessageBox.warning(self, "Save Image", str(error))


class ViewAllDialog(QDialog):
    """Every field in the file (not only the hidden ones). The fields the sender hid are marked PAYLOAD."""

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.setObjectName("metadataViewAllDialog")
        self.setWindowTitle(f"All Metadata — {Path(file_path).name}")
        self.resize(720, 600)
        layout = QVBoxLayout(self)

        note = QLabel("Every field in this file, including the ones that were already there. "
                      "PAYLOAD = a field the sender added or modified.")
        note.setObjectName("hintLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        content = QWidget()
        content.setObjectName("fileListContainer")
        self.rows_layout = QVBoxLayout(content)
        self.rows_layout.setSpacing(10)
        if Path(file_path).suffix.lower() == ".mp3":
            self.add_mp3_rows(file_path)
        else:
            self.add_png_rows(file_path)
        if self.rows_layout.count() == 0:
            empty = QLabel("This file has no metadata.")
            empty.setObjectName("hintLabel")
            self.rows_layout.addWidget(empty)
        self.rows_layout.addStretch()

        scroll = QScrollArea()
        scroll.setObjectName("fileListScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        close_button = QPushButton("Close")
        close_button.setObjectName("SecondaryBtn")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

    def add_png_rows(self, file_path: str):
        handler = MetadataPNGHandler()
        hidden = handler.read_secret(file_path)
        for keyword, value in handler.read_text(file_path).items():
            name = PNG_TEXT_KEYWORDS.get(keyword, (keyword, ""))[0]
            self.rows_layout.addWidget(FieldRow(name, keyword, value, payload=keyword in hidden))

    def add_mp3_rows(self, file_path: str):
        handler = MetadataMP3Handler()
        hidden = handler.read_secret(file_path)
        for key, field in handler.read_frames(file_path).items():
            is_picture = field.frame_id == "APIC"
            value = picture_summary(field) if is_picture else field.text
            self.rows_layout.addWidget(FieldRow(key_label(key), field.frame_id, value, payload=key in hidden, copyable=not is_picture))
        # frame ที่ editor ไม่ได้แก้ (PRIV, POPM ...) แสดงไว้ดูเฉย ๆ
        for key, value in handler.read_other_frames(file_path).items():
            frame_id = key.split(":")[0].split(" ")[0]
            name = FRAME_INFO.get(frame_id, (frame_id, ""))[0]
            self.rows_layout.addWidget(FieldRow(name, key, value))


class MetadataExtractForm(QFrame):
    """Stego file card (drop zone) <-> result page (file info, hidden fields, hidden pictures)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_path: str | None = None
        self.setup_ui()

    # --- UI construction ---

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 11, 0, 0)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.build_stego_file_card())
        self.stack.addWidget(self.build_result_page())
        layout.addWidget(self.stack, 1)

    def build_stego_file_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)

        title_container = QFrame()
        title_layout = QHBoxLayout(title_container)
        icon = QLabel()
        icon.setPixmap(create_icon_pixmap(svg_path("photo-video.svg"), size=ICON_SIZE))
        title = QLabel("Stego File (PNG, MP3)")
        title.setObjectName("cardTitle")
        title_layout.addWidget(icon)
        title_layout.addWidget(title)
        title_layout.addStretch()

        self.stego_drop_zone = FileDropWidget(
            text="Drop PNG or MP3 file here or click to browse",
            sub_text="Shows the fields the sender added or modified",
            icon_path=str(svg_path("photo-video.svg")),
            allowed_extensions=[".png", ".mp3"],
            show_preview=False,
        )
        self.stego_drop_zone.file_selected.connect(self.on_file_selected)
        layout.addWidget(title_container)
        layout.addWidget(self.stego_drop_zone, 1)
        return card

    def build_result_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.file_info_bar = FileInfoBar()
        self.file_info_bar.change_file_requested.connect(self.reset)
        self.view_all_button = self.file_info_bar.add_extra_button("View All")
        self.view_all_button.clicked.connect(self.open_view_all)
        layout.addWidget(self.file_info_bar)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("metadataPreview")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        content = QWidget()
        content.setObjectName("fileListContainer")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        # Hidden fields (PNG text / MP3 text frames)
        self.fields_card = QFrame()
        self.fields_card.setObjectName("card")
        add_shadow_effect(self.fields_card)
        fields_layout = QVBoxLayout(self.fields_card)
        self.fields_count = make_badge("0")
        fields_layout.addWidget(make_card_header("Hidden Fields", "tags.svg", "Added or modified by the sender", self.fields_count))
        self.fields_layout = QVBoxLayout()
        self.fields_layout.setSpacing(12)
        fields_layout.addLayout(self.fields_layout)
        self.fields_empty = QLabel("No hidden fields in this file.")
        self.fields_empty.setObjectName("hintLabel")
        fields_layout.addWidget(self.fields_empty)
        content_layout.addWidget(self.fields_card)

        # Hidden pictures (MP3 APIC only)
        self.pictures_card = QFrame()
        self.pictures_card.setObjectName("card")
        add_shadow_effect(self.pictures_card)
        pictures_layout = QVBoxLayout(self.pictures_card)
        self.pictures_count = make_badge("0")
        pictures_layout.addWidget(make_card_header("Hidden Pictures", "photo.svg", "Save Image keeps the exact bytes", self.pictures_count))
        self.pictures_grid = QGridLayout()
        self.pictures_grid.setSpacing(12)
        self.pictures_grid.setColumnStretch(0, 1)
        self.pictures_grid.setColumnStretch(1, 1)
        pictures_layout.addLayout(self.pictures_grid)
        content_layout.addWidget(self.pictures_card)
        content_layout.addStretch()

        scroll = QScrollArea()
        scroll.setObjectName("fileListScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return page

    # --- Actions ---

    def on_file_selected(self, file_path: str):
        if not file_path or file_path == self.file_path:
            return
        try:
            self.load_file(file_path)
        except (OSError, ValueError, MutagenError) as error:
            self.reset()
            QMessageBox.warning(self, "Cannot read file", str(error))

    def load_file(self, file_path: str):
        """Read the hidden fields of a PNG / MP3. Raises (OSError / ValueError / MutagenError) if it cannot be read."""
        if Path(file_path).suffix.lower() == ".mp3":
            info = get_mp3_file_info(file_path)
            hidden = MetadataMP3Handler().read_secret(file_path)
            fields = [(key_label(key), field.frame_id, field.text) for key, field in hidden.items() if field.frame_id != "APIC"]
            pictures = [field for field in hidden.values() if field.frame_id == "APIC"]
        else:
            info = get_png_file_info(file_path)
            hidden = MetadataPNGHandler().read_secret(file_path)
            fields = [(PNG_TEXT_KEYWORDS.get(key, (key, ""))[0], key, value) for key, value in hidden.items()]
            pictures = []

        self.clear_result()
        for name, key, value in fields:
            self.fields_layout.addWidget(FieldRow(name, key, value))
        for index, picture in enumerate(pictures):
            self.pictures_grid.addWidget(PictureResultCard(picture, index + 1), index // 2, index % 2)

        self.fields_count.setText(str(len(fields)))
        self.fields_empty.setVisible(not fields)
        self.pictures_count.setText(str(len(pictures)))
        self.pictures_card.setVisible(bool(pictures))
        total = len(fields) + len(pictures)
        if total:
            self.summary_label.setText(f"The sender added or modified {total} field(s) in this file.")
        else:
            self.summary_label.setText("This file has no SIENG2 field list: nothing was hidden in its metadata. "
                                       "View All shows the metadata it has.")
        self.file_info_bar.update_info(**info)
        self.file_path = file_path
        self.stack.setCurrentIndex(1)

    def clear_result(self):
        for layout in (self.fields_layout, self.pictures_grid):
            while layout.count():
                widget = layout.takeAt(0).widget()
                if widget is not None:
                    widget.hide()
                    widget.deleteLater()

    def reset(self):
        """Change File: back to the drop zone."""
        self.file_path = None
        self.clear_result()
        with QSignalBlocker(self.stego_drop_zone):  # clear_all() ส่ง file_selected("") ไม่ต้องรับซ้ำ
            self.stego_drop_zone.clear_all()
        self.setFocus()  # the focused Change File button is hidden by the page switch (same as the embed form)
        self.stack.setCurrentIndex(0)

    def open_view_all(self):
        if not self.file_path:
            return
        try:
            dialog = ViewAllDialog(self.file_path, parent=self)
        except (OSError, ValueError, MutagenError) as error:
            QMessageBox.warning(self, "View All", str(error))
            return
        dialog.exec()
