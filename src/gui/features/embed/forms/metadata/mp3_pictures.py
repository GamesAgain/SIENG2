"""
MP3 "Attached Pictures" tab (APIC): picture cards + an Add / Edit picture editor.

Each picture is an MP3Field("APIC", mime, picture_type, desc, data) or, in the pipeline,
a LinkedPicture (a PNG output of an earlier step; its bytes are read when the pipeline runs).
- desc is set from the picture type: 'front-cover', then 'front-cover-2', ... (the user does not type it)
- a picture from the file keeps its own desc until the user changes its type
- type 1 and 2 (file icons) can have one picture each (ID3 spec)
"""
from io import BytesIO
from pathlib import Path

from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout,
)
from PIL import Image, UnidentifiedImageError

from src.core.configurable.drafts import TECHNIQUE_LABELS, LinkedPicture
from src.core.configurable.step_output import StepOutput, StepOutputInfo
from src.core.stego.metadata_handlers.mp3_handler import (
    APIC_TYPES, SINGLE_PICTURE_TYPES, MP3Field, apic_description,
)
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, format_file_size
from src.gui.components.widgets.files_drop import FileDropWidget
from src.gui.components.widgets.selection_toggle import SelectionToggle
from src.gui.features.embed.configurable.widgets.step_output_picker import StepOutputPicker
from src.gui.features.embed.forms.metadata.common import (
    make_badge, make_payload_badge, make_remove_button, make_value_input, set_payload_mark,
)
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
    """Preview, type, description and size of one picture, with Edit and Remove buttons.
    A linked picture has no bytes before the run: it shows where it comes from (source_text) instead."""

    edit_requested = pyqtSignal(object)
    remove_requested = pyqtSignal(object)

    def __init__(self, picture: MP3Field | LinkedPicture, number: int, source_text: str = "", parent=None):
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
        self.payload_badge = make_payload_badge()
        type_row = QHBoxLayout()
        type_row.addWidget(badge)
        type_row.addStretch()
        type_row.addWidget(self.payload_badge)
        preview_layout.addLayout(type_row)

        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        linked = isinstance(picture, LinkedPicture)
        pixmap = QPixmap()
        if not linked:
            pixmap.loadFromData(picture.data)
        if pixmap.isNull():
            pixmap = create_icon_pixmap(svg_path("photo.svg"), size=28)
            image.setToolTip("Preview is available after the pipeline runs." if linked
                             else "Image [pending]; select a new image." if not picture.data
                             else "Preview unavailable; the original image data is kept.")
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
        if linked:
            detail = QLabel(f"{source_text} · PNG · size known after the run")
            detail.setWordWrap(True)
        else:
            detail = QLabel(f"{picture.mime} · {format_file_size(len(picture.data))}" if picture.data
                            else "Image [pending] · select a new image")
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

    def set_payload(self, on: bool) -> None:
        set_payload_mark(self, on)
        self.payload_badge.setVisible(on)


class MP3PicturesForm(QFrame):

    changed = pyqtSignal()
    count_changed = pyqtSignal(int)
    edit_started = pyqtSignal()

    def __init__(self, is_config: bool = False, parent=None):
        super().__init__(parent)
        self.is_config = is_config  # pipeline: a picture can also be a PNG output of an earlier step
        self.pictures: list[MP3Field | LinkedPicture] = []
        self.cards: list[PictureCard] = []
        self.editing_index: int | None = None       # None = เพิ่มภาพใหม่
        self.new_image: tuple[str, bytes] | None = None  # (mime, data) ของภาพที่เลือกใน editor
        self.new_image_path: str = ""
        self.new_link: StepOutput | None = None          # output ที่เลือกใน picker ของ editor
        self.picture_choices: list[StepOutputInfo] = []  # PNG outputs ที่ใช้เป็นภาพได้ (หน้า pipeline ส่งมา)

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

        # Pipeline only: the picture comes from a file (Manual) or from an earlier step's PNG (Previous Output)
        self.source_toggle = SelectionToggle([
            {"text": "Manual File", "value": "manual", "variant": "source"},
            {"text": "Previous Output", "value": "previous", "variant": "source"},
        ])
        self.source_toggle.mode_changed.connect(self.on_source_changed)
        self.source_toggle.setVisible(self.is_config)
        layout.addWidget(self.source_toggle)

        row = QHBoxLayout()
        row.setSpacing(16)
        self.image_drop_zone = FileDropWidget(
            "Drop a picture here or click to browse", "Supports PNG and JPEG",
            str(svg_path("photo.svg")), allowed_extensions=[".png", ".jpg", ".jpeg"],
        )
        self.image_drop_zone.setMinimumHeight(160)
        self.image_drop_zone.file_selected.connect(self.on_image_selected)
        self.output_picker = StepOutputPicker()
        self.output_picker.setMinimumHeight(160)
        self.output_picker.selection_changed.connect(self.on_output_selected)
        self.source_stack = QStackedWidget()
        self.source_stack.addWidget(self.image_drop_zone)
        self.source_stack.addWidget(self.output_picker)
        row.addWidget(self.source_stack, 1)

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
            self.new_image_path = ""
            return
        try:
            self.new_image = read_picture_file(file_path)
            self.new_image_path = file_path
        except (OSError, ValueError) as error:
            self.new_image = None
            self.new_image_path = ""
            with QSignalBlocker(self.image_drop_zone):
                self.image_drop_zone.clear_all()
            QMessageBox.warning(self, "Attached Picture", str(error))

    def on_source_changed(self, mode: str) -> None:
        self.source_stack.setCurrentIndex(0 if mode == "manual" else 1)

    def on_output_selected(self, reference: StepOutput | None) -> None:
        self.new_link = reference

    def source_mode(self) -> str:
        return self.source_toggle.mode() if self.is_config else "manual"

    def source_text(self, link: StepOutput) -> str:
        """Where a linked picture comes from, e.g. 'From Step 2 Locomotive, a.png' (or that it is gone)."""
        info = next((choice for choice in self.picture_choices if choice.reference == link), None)
        if info is None:
            return "Unavailable output: select another one"
        return f"From Step {info.step_number} {TECHNIQUE_LABELS.get(info.technique, info.technique)}, {info.display_name}"

    def refresh_picker(self) -> None:
        """The outputs no other picture of this step uses (the one being edited keeps its own)."""
        used = {picture.source for index, picture in enumerate(self.pictures)
                if isinstance(picture, LinkedPicture) and index != self.editing_index}
        self.output_picker.set_outputs([choice for choice in self.picture_choices if choice.reference not in used])

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

    def picture_from_editor(self) -> MP3Field | LinkedPicture:
        """The picture the editor describes. Editing without picking a new image/output keeps the old one."""
        picture_type = self.selected_type()
        if picture_type in SINGLE_PICTURE_TYPES and any(
                picture.picture_type == picture_type
                for index, picture in enumerate(self.pictures) if index != self.editing_index):
            raise ValueError(f"Only one picture of type {type_text(picture_type)} is allowed.")
        old = self.pictures[self.editing_index] if self.editing_index is not None else None
        desc = self.planned_description()

        if self.source_mode() == "previous":
            link = self.new_link or (old.source if isinstance(old, LinkedPicture) else None)
            if link is None:
                raise ValueError("Select an output first.")
            return LinkedPicture(link, picture_type, desc)

        if self.new_image is not None:
            mime, data = self.new_image
            path = self.new_image_path
        elif isinstance(old, MP3Field):
            mime, data = old.mime, old.data  # แก้แค่ type -> ใช้ภาพเดิม
            path = old.path
        else:
            raise ValueError("Select a picture first.")
        if not data:
            raise ValueError("Select a new image for this pending picture.")
        return MP3Field("APIC", mime=mime, picture_type=picture_type, desc=desc, data=data, path=path)

    def confirm_picture(self) -> None:
        try:
            picture = self.picture_from_editor()
        except ValueError as error:
            QMessageBox.warning(self, "Attached Picture", str(error))
            return

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
        picture = self.pictures[index]
        picture_type = picture.picture_type
        if self.type_combo.findData(picture_type) < 0:  # type แปลก ๆ จากไฟล์อื่น (> 20)
            self.type_combo.addItem(type_text(picture_type), picture_type)
        self.type_combo.setCurrentIndex(self.type_combo.findData(picture_type))
        if isinstance(picture, LinkedPicture):
            self.source_toggle.set_mode("previous")  # set_mode does not emit mode_changed
            self.on_source_changed("previous")
            self.refresh_picker()
            self.output_picker.set_selection(picture.source)
        self.editor_title.setText(f'Edit Picture "{picture.desc}" (pick a new image or output to replace it)')
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
        self.new_image_path = ""
        self.new_link = None
        with QSignalBlocker(self.image_drop_zone):
            self.image_drop_zone.clear_all()
        self.source_toggle.set_mode("manual")
        self.on_source_changed("manual")
        self.refresh_picker()
        self.output_picker.set_selection(None)
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
            source_text = self.source_text(picture.source) if isinstance(picture, LinkedPicture) else ""
            card = PictureCard(picture, index + 1, source_text)
            card.edit_requested.connect(self.edit_picture)
            card.remove_requested.connect(self.remove_picture)
            self.cards.append(card)
            self.cards_layout.addWidget(card, index // 2, index % 2)
        self.count_badge.setText(str(len(self.pictures)))
        self.empty_label.setVisible(not self.pictures)
        self.update_description()
        self.count_changed.emit(len(self.pictures))

    # --- Values ---

    def set_pictures(self, pictures: list[MP3Field | LinkedPicture]) -> None:
        self.pictures = list(pictures)
        self.reset_editor()
        self.refresh_cards()

    def set_picture_choices(self, choices: list[StepOutputInfo]) -> None:
        """Pipeline: the PNG outputs a picture may come from (the page gives them before the draft is loaded)."""
        self.picture_choices = list(choices)
        self.refresh_picker()
        self.refresh_cards()

    def mark_payload(self, changed: set[str]) -> None:
        for card, picture in zip(self.cards, self.pictures):
            # a linked picture is always new for the receiver
            card.set_payload(isinstance(picture, LinkedPicture) or picture.key in changed)

    def current_pictures(self) -> list[MP3Field]:
        """The confirmed pictures from files (used for the live preview and the step entries)."""
        return [picture for picture in self.pictures if isinstance(picture, MP3Field)]

    def linked_pictures(self) -> list[LinkedPicture]:
        """The confirmed pictures from earlier steps (pipeline)."""
        return [picture for picture in self.pictures if isinstance(picture, LinkedPicture)]

    def get_pictures(self) -> list[MP3Field]:
        """Pictures from files to save. Raises ValueError while a picture is still open in the editor, or when
        a linked picture's output is no longer available (it is kept, not removed, until the user picks another)."""
        if self.editing_index is not None or self.new_image is not None or self.new_link is not None:
            raise ValueError("Finish the picture first: click Add/Update Picture or Cancel.")
        available = {choice.reference for choice in self.picture_choices}
        for picture in self.linked_pictures():
            if picture.source not in available:
                raise ValueError(f'The output of picture "{picture.desc}" is unavailable. Edit it and select another output.')
        for picture in self.current_pictures():
            if not picture.data:
                raise ValueError(f'Picture "{picture.desc}" is [pending]; select a new image or remove it.')
        return self.current_pictures()
