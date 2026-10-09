"""
MP3 "Attached Pictures" tab (APIC): picture cards + an Add / Edit picture editor.

Each picture is an MP3Field("APIC", mime, picture_type, desc, data).
- desc is set from the picture type: 'front-cover', then 'front-cover-2', ... (the user does not type it)
- a picture from the file keeps its own desc until the user changes its type
- type 1 and 2 (file icons) can have one picture each (ID3 spec)
"""
from io import BytesIO
from pathlib import Path

from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
)
from PIL import Image, UnidentifiedImageError

from src.core.stego.metadata_handlers.mp3_handler import (
    APIC_TYPES, SINGLE_PICTURE_TYPES, MP3Field, apic_description,
)
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, format_file_size
from src.gui.components.widgets.files_drop import FileDropWidget
from src.gui.features.embed.forms.metadata.common import make_badge, make_remove_button, make_value_input
from src.path import svg_path

TINTS = ["blue", "purple", "green", "orange"]
DEFAULT_TYPE = 3  # ปกหน้า


def read_picture_file(file_path: str) -> tuple[str, bytes]:
    """(mime, bytes) of a PNG or JPEG file. ValueError for anything else."""
    data = Path(file_path).read_bytes()
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValueError(f"'{Path(file_path).name}' is not a valid image file.") from None
    if image_format not in ("PNG", "JPEG"):
        raise ValueError("Select a PNG or JPEG image.")
    return Image.MIME[image_format], data  # ไบต์ภาพเดิมทั้งไฟล์ (ไม่ถอด/บีบอัดใหม่ -> stego อยู่ครบ)


def type_text(picture_type: int) -> str:
    return f"{picture_type} — {APIC_TYPES.get(picture_type, 'Unknown')}"


class PictureCard(QFrame):
    """Preview, type, description and size of one picture, with Edit and Remove buttons."""

    edit_requested = pyqtSignal(object)
    remove_requested = pyqtSignal(object)

    def __init__(self, picture: MP3Field, number: int, parent=None):
        super().__init__(parent)
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
        badge = QLabel(f"Type {type_text(picture.picture_type)}")
        badge.setObjectName("fileInfoBadge")
        badge.setProperty("badgeColor", "blue")
        type_row = QHBoxLayout()
        type_row.addWidget(badge)
        type_row.addStretch()
        preview_layout.addLayout(type_row)

        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap()
        pixmap.loadFromData(picture.data)
        if pixmap.isNull():
            pixmap = create_icon_pixmap(svg_path("photo.svg"), size=28)
            image.setToolTip("Preview unavailable; the original image data is kept.")
        else:
            pixmap = pixmap.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        image.setPixmap(pixmap)
        preview_layout.addWidget(image, 1)
        layout.addWidget(preview)

        body = QFrame()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(10, 8, 10, 10)
        title = QLabel(f'"{picture.desc}"')
        title.setObjectName("fileInfoName")
        title.setToolTip("Description (set from the picture type)")
        body_layout.addWidget(title)
        detail = QLabel(f"{picture.mime} · {format_file_size(len(picture.data))}")
        detail.setObjectName("fileInfoDetail")
        body_layout.addWidget(detail)

        buttons = QHBoxLayout()
        edit_button = QPushButton("Edit / Change Image")
        edit_button.setObjectName("SecondaryBtn")
        edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_button.clicked.connect(lambda: self.edit_requested.emit(self))
        remove_button = make_remove_button("Remove picture")
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        buttons.addWidget(edit_button, 1)
        buttons.addWidget(remove_button)
        body_layout.addLayout(buttons)
        layout.addWidget(body)


class MP3PicturesForm(QFrame):

    changed = pyqtSignal()
    count_changed = pyqtSignal(int)
    edit_started = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pictures: list[MP3Field] = []
        self.cards: list[PictureCard] = []
        self.editing_index: int | None = None       # None = เพิ่มภาพใหม่
        self.new_image: tuple[str, bytes] | None = None  # (mime, data) ของภาพที่เลือกใน editor

        self.setObjectName("fileListContainer")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 12, 4, 4)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(svg_path("photo.svg"), size=16))
        title = QLabel("Attached Pictures (APIC)")
        title.setObjectName("cardTitle")
        self.count_badge = make_badge("0")
        header.addWidget(title_icon)
        header.addWidget(title)
        header.addWidget(self.count_badge)
        header.addStretch()
        layout.addLayout(header)

        self.empty_label = QLabel("No attached pictures")
        self.empty_label.setObjectName("hintLabel")
        layout.addWidget(self.empty_label)

        self.cards_layout = QGridLayout()
        self.cards_layout.setSpacing(12)
        self.cards_layout.setColumnStretch(0, 1)
        self.cards_layout.setColumnStretch(1, 1)
        layout.addLayout(self.cards_layout)
        layout.addWidget(self.build_editor())
        layout.addStretch()
        self.reset_editor()

    def build_editor(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)

        title_row = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(create_icon_pixmap(svg_path("photo.svg"), size=16))
        self.editor_title = QLabel()
        self.editor_title.setObjectName("cardTitle")
        title_row.addWidget(icon)
        title_row.addWidget(self.editor_title)
        title_row.addStretch()
        layout.addLayout(title_row)

        row = QHBoxLayout()
        row.setSpacing(16)
        self.image_drop_zone = FileDropWidget(
            "Drop a picture here or click to browse", "Supports PNG and JPEG",
            str(svg_path("photo.svg")), allowed_extensions=[".png", ".jpg", ".jpeg"],
        )
        self.image_drop_zone.setMinimumHeight(160)
        self.image_drop_zone.file_selected.connect(self.on_image_selected)
        row.addWidget(self.image_drop_zone, 1)

        settings = QVBoxLayout()
        settings.setSpacing(8)
        type_label = QLabel("Picture Type")
        type_label.setObjectName("formLabel")
        self.type_combo = QComboBox()
        for picture_type in APIC_TYPES:
            self.type_combo.addItem(type_text(picture_type), picture_type)
        self.type_combo.currentIndexChanged.connect(self.update_description)
        description_label = QLabel("Description (read-only, set from the type)")
        description_label.setObjectName("formLabel")
        self.description_value = make_value_input()
        self.description_value.setReadOnly(True)  # desc ตั้งจาก type ผู้ใช้ไม่ต้องพิมพ์
        self.description_value.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        settings.addWidget(type_label)
        settings.addWidget(self.type_combo)
        settings.addWidget(description_label)
        settings.addWidget(self.description_value)
        settings.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("SecondaryBtn")
        self.cancel_button.clicked.connect(self.reset_editor)
        self.confirm_button = QPushButton()
        self.confirm_button.setObjectName("PrimaryActionBtn")
        self.confirm_button.clicked.connect(self.confirm_picture)
        for button in (self.cancel_button, self.confirm_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(button)
        settings.addLayout(buttons)
        row.addLayout(settings, 1)
        layout.addLayout(row)
        return card

    # --- Editor ---

    def on_image_selected(self, file_path: str) -> None:
        if not file_path:
            self.new_image = None
            return
        try:
            self.new_image = read_picture_file(file_path)
        except (OSError, ValueError) as error:
            self.new_image = None
            with QSignalBlocker(self.image_drop_zone):
                self.image_drop_zone.clear_all()
            QMessageBox.warning(self, "Attached Picture", str(error))

    def selected_type(self) -> int:
        return self.type_combo.currentData()

    def planned_description(self) -> str:
        """desc for the picture in the editor: kept while editing with the same type, else set from the type."""
        picture_type = self.selected_type()
        if self.editing_index is not None:
            old = self.pictures[self.editing_index]
            if old.picture_type == picture_type:
                return old.desc
        taken = {picture.desc for index, picture in enumerate(self.pictures) if index != self.editing_index}
        return apic_description(picture_type, taken)

    def update_description(self) -> None:
        self.description_value.setText(self.planned_description())

    def confirm_picture(self) -> None:
        picture_type = self.selected_type()
        try:
            if self.editing_index is None and self.new_image is None:
                raise ValueError("Select a picture first.")
            if picture_type in SINGLE_PICTURE_TYPES and any(
                    picture.picture_type == picture_type
                    for index, picture in enumerate(self.pictures) if index != self.editing_index):
                raise ValueError(f"Only one picture of type {type_text(picture_type)} is allowed.")
        except ValueError as error:
            QMessageBox.warning(self, "Attached Picture", str(error))
            return

        if self.new_image is not None:
            mime, data = self.new_image
        else:
            old = self.pictures[self.editing_index]  # แก้แค่ type -> ใช้ภาพเดิม
            mime, data = old.mime, old.data
        picture = MP3Field("APIC", mime=mime, picture_type=picture_type, desc=self.planned_description(), data=data)

        if self.editing_index is None:
            self.pictures.append(picture)
        else:
            self.pictures[self.editing_index] = picture
        self.refresh_cards()
        self.reset_editor()
        self.changed.emit()

    def edit_picture(self, card: PictureCard) -> None:
        index = self.cards.index(card)
        self.reset_editor()
        self.editing_index = index
        picture_type = self.pictures[index].picture_type
        if self.type_combo.findData(picture_type) < 0:  # type แปลก ๆ จากไฟล์อื่น (> 20)
            self.type_combo.addItem(type_text(picture_type), picture_type)
        self.type_combo.setCurrentIndex(self.type_combo.findData(picture_type))
        self.editor_title.setText(f'Edit Picture "{self.pictures[index].desc}" (drop a new image to replace it)')
        self.confirm_button.setText("Update Picture")
        self.update_description()
        self.edit_started.emit()

    def remove_picture(self, card: PictureCard) -> None:
        del self.pictures[self.cards.index(card)]
        self.reset_editor()  # index ของภาพที่กำลังแก้อาจเลื่อน จึงเริ่ม editor ใหม่
        self.refresh_cards()
        self.changed.emit()

    def reset_editor(self) -> None:
        self.editing_index = None
        self.new_image = None
        with QSignalBlocker(self.image_drop_zone):
            self.image_drop_zone.clear_all()
        self.type_combo.setCurrentIndex(self.type_combo.findData(DEFAULT_TYPE))
        self.editor_title.setText("Add New Picture")
        self.confirm_button.setText("+ Add Picture")
        self.update_description()

    def refresh_cards(self) -> None:
        for card in self.cards:
            self.cards_layout.removeWidget(card)
            card.hide()
            card.deleteLater()
        self.cards = []
        for index, picture in enumerate(self.pictures):
            card = PictureCard(picture, index + 1)
            card.edit_requested.connect(self.edit_picture)
            card.remove_requested.connect(self.remove_picture)
            self.cards.append(card)
            self.cards_layout.addWidget(card, index // 2, index % 2)
        self.count_badge.setText(str(len(self.pictures)))
        self.empty_label.setVisible(not self.pictures)
        self.update_description()
        self.count_changed.emit(len(self.pictures))

    # --- Values ---

    def set_pictures(self, pictures: list[MP3Field]) -> None:
        self.pictures = list(pictures)
        self.reset_editor()
        self.refresh_cards()

    def current_pictures(self) -> list[MP3Field]:
        """The confirmed pictures (used for the live preview)."""
        return list(self.pictures)

    def get_pictures(self) -> list[MP3Field]:
        """Pictures to save. Raises ValueError while a picture is still open in the editor."""
        if self.editing_index is not None or self.new_image is not None:
            raise ValueError("Finish the picture first: click Add/Update Picture or Cancel.")
        return list(self.pictures)
