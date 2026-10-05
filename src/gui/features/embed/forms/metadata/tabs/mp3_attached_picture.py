"""Attached-picture cards and a manual Add/Edit editor."""

from copy import deepcopy

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QStackedWidget, QVBoxLayout,
)

from src.core.stego.metadata_handlers.mp3_handler import APIC_TYPES
from src.gui.components.gui_utils import create_icon_pixmap, format_file_size
from src.gui.components.widgets.files_drop import FileDropWidget
from src.gui.components.widgets.selection_toggle import SelectionToggle
from src.gui.features.embed.forms.metadata.mp3_draft import (
    MP3AttachedPictureDraft, read_attached_picture, validate_attached_pictures,
)
from src.path import svg_path


class AttachedPictureCard(QFrame):
    edit_requested = pyqtSignal(object)
    remove_requested = pyqtSignal(object)

    def __init__(self, picture: MP3AttachedPictureDraft, number: int, parent=None):
        super().__init__(parent)
        self.setObjectName("apicCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        preview = QFrame()
        preview.setObjectName("apicPreview")
        preview.setProperty("tintColor", ["blue", "purple", "green", "orange"][(number - 1) % 4])
        preview.setFixedHeight(120)
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        badge = QLabel(f"Type {picture.picture_type} — {APIC_TYPES.get(picture.picture_type, 'Unknown')}")
        badge.setObjectName("fileInfoBadge")
        badge.setProperty("badgeColor", "blue")
        badge.setWordWrap(False)
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
            image.setToolTip("Preview unavailable; original image data is retained.")
        else:
            pixmap = pixmap.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
        image.setPixmap(pixmap)
        preview_layout.addWidget(image, 1)
        layout.addWidget(preview)
        body = QFrame()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(10, 8, 10, 10)
        title = QLabel(picture.source_name or f"Embedded image {number}")
        title.setObjectName("fileInfoName")
        title.setWordWrap(True)
        body_layout.addWidget(title)
        detail = QLabel(f"{picture.mime} · {format_file_size(len(picture.data))}")
        detail.setObjectName("fileInfoDetail")
        body_layout.addWidget(detail)
        description = QLabel(f'Description: "{picture.description}"')
        description.setObjectName("fileInfoDetail")
        description.setWordWrap(True)
        body_layout.addWidget(description)
        buttons = QHBoxLayout()
        edit = QPushButton("Edit / Change Image")
        edit.setObjectName("SecondaryBtn")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.clicked.connect(lambda: self.edit_requested.emit(self))
        remove = QPushButton()
        remove.setObjectName("btnRemoveFile")
        remove.setFixedSize(30, 30)
        remove.setToolTip("Remove attached picture")
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.setIcon(QIcon(create_icon_pixmap(svg_path("x.svg"), size=14, color_hex="#F43F5E")))
        remove.clicked.connect(lambda: self.remove_requested.emit(self))
        buttons.addWidget(edit, 1)
        buttons.addWidget(remove)
        body_layout.addLayout(buttons)
        layout.addWidget(body)


class MP3AttachedPictureForm(QFrame):
    edit_started = pyqtSignal()
    count_changed = pyqtSignal(int)

    def __init__(self, is_config: bool = False, parent=None):
        super().__init__(parent)
        self.is_config = is_config
        self.pictures: list[MP3AttachedPictureDraft] = []
        self.cards: list[AttachedPictureCard] = []
        self.pending_picture = None
        self.editing_index = None
        self.setObjectName("fileListContainer")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 12, 4, 4)
        layout.setSpacing(12)
        header = QHBoxLayout()
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(svg_path("photo.svg"), size=16))
        header.addWidget(title_icon)
        title = QLabel("Attached Pictures (APIC)")
        title.setObjectName("cardTitle")
        self.count_badge = QLabel("0")
        self.count_badge.setObjectName("fileInfoBadge")
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
        layout = QVBoxLayout(card)
        title_row = QHBoxLayout()
        self.editor_icon = QLabel()
        self.editor_icon.setPixmap(create_icon_pixmap(svg_path("photo.svg"), size=16))
        self.editor_title = QLabel("Add New Image")
        self.editor_title.setObjectName("cardTitle")
        title_row.addWidget(self.editor_icon)
        title_row.addWidget(self.editor_title)
        title_row.addStretch()
        layout.addLayout(title_row)
        self.source_toggle = SelectionToggle([
            {"text": "Manual File", "value": "manual", "variant": "source"},
            {"text": "Previous Output", "value": "linked", "variant": "source"},
        ])
        layout.addWidget(self.source_toggle)
        self.source_toggle.setVisible(self.is_config)
        row = QHBoxLayout()
        row.setSpacing(16)
        self.source_stack = QStackedWidget()
        self.image_drop_zone = FileDropWidget(
            "Drop cover image here or click to browse", "Supports PNG and JPEG",
            str(svg_path("photo.svg")), allowed_extensions=[".png", ".jpg", ".jpeg"],
        )
        self.image_drop_zone.setMinimumHeight(160)
        self.source_stack.addWidget(self.image_drop_zone)
        self.previous_output_placeholder = QLabel("Previous output selection is not available yet.")
        self.previous_output_placeholder.setObjectName("hintLabel")
        self.previous_output_placeholder.setWordWrap(True)
        self.previous_output_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.source_stack.addWidget(self.previous_output_placeholder)
        # TODO: replace placeholder with pipeline output picker and resolve linked image bytes.
        row.addWidget(self.source_stack, 1)
        settings = QVBoxLayout()
        settings.setSpacing(8)
        type_label = QLabel("Picture Type")
        type_label.setObjectName("formLabel")
        settings.addWidget(type_label)
        self.type_combo = QComboBox()
        for picture_type, name in APIC_TYPES.items():
            self.type_combo.addItem(f"{picture_type} — {name}", picture_type)
        settings.addWidget(self.type_combo)
        description_label = QLabel("Description")
        description_label.setObjectName("formLabel")
        settings.addWidget(description_label)
        self.description_input = QLineEdit()
        self.description_input.setObjectName("formInput")
        self.description_input.setPlaceholderText("Unique description for this picture")
        settings.addWidget(self.description_input)
        self.editing_image_label = QLabel()
        self.editing_image_label.setObjectName("hintLabel")
        self.editing_image_label.setWordWrap(True)
        settings.addWidget(self.editing_image_label)
        settings.addStretch()
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("SecondaryBtn")
        self.cancel_button.clicked.connect(self.reset_editor)
        self.confirm_button = QPushButton("+ Add Image")
        self.confirm_button.setObjectName("PrimaryActionBtn")
        self.confirm_button.clicked.connect(self.confirm_picture)
        for button in (self.cancel_button, self.confirm_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(button)
        settings.addLayout(buttons)
        row.addLayout(settings, 1)
        layout.addLayout(row)
        self.image_drop_zone.file_selected.connect(self.on_image_selected)
        self.source_toggle.mode_changed.connect(self.on_source_changed)
        return card

    def on_source_changed(self, mode: str) -> None:
        self.source_stack.setCurrentIndex(1 if mode == "linked" else 0)
        self.confirm_button.setEnabled(mode == "manual")

    def on_image_selected(self, file_path: str) -> None:
        if not file_path:
            self.pending_picture = (deepcopy(self.pictures[self.editing_index])
                                    if self.editing_index is not None else None)
            self.editing_image_label.setText("Current image is retained." if self.editing_index is not None else "")
            return
        try:
            self.pending_picture = read_attached_picture(file_path)
            self.editing_image_label.setText(self.pending_picture.source_name or "")
        except (OSError, ValueError) as error:
            self.image_drop_zone.blockSignals(True)
            self.image_drop_zone.clear_file()
            self.image_drop_zone.blockSignals(False)
            self.on_image_selected("")
            QMessageBox.warning(self, "Attached Picture", str(error))

    def confirm_picture(self) -> None:
        if self.source_toggle.mode() != "manual":
            return  # TODO: enable adding linked sources when pipeline resolution is implemented.
        try:
            if self.pending_picture is None:
                raise ValueError("Select an image first.")
            picture = deepcopy(self.pending_picture)
            picture.picture_type = self.type_combo.currentData()
            picture.description = self.description_input.text()
            candidate = deepcopy(self.pictures)
            if self.editing_index is None:
                candidate.append(picture)
            else:
                candidate[self.editing_index] = picture
            validate_attached_pictures(candidate)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Attached Picture", str(error))
            return
        self.pictures = candidate
        self.refresh_cards()
        self.reset_editor()

    def edit_picture(self, card: AttachedPictureCard) -> None:
        index = self.cards.index(card)
        self.reset_editor()
        self.editing_index = index
        self.pending_picture = deepcopy(self.pictures[index])
        picture_type = self.pending_picture.picture_type
        combo_index = self.type_combo.findData(picture_type)
        if combo_index < 0:
            self.type_combo.addItem(f"{picture_type} — Unknown", picture_type)
            combo_index = self.type_combo.findData(picture_type)
        self.type_combo.setCurrentIndex(combo_index)
        self.description_input.setText(self.pending_picture.description)
        self.editor_title.setText("Edit Picture")
        self.confirm_button.setText("Update Image")
        self.editing_image_label.setText("Current image is retained unless you select a replacement.")
        self.edit_started.emit()

    def remove_picture(self, card: AttachedPictureCard) -> None:
        del self.pictures[self.cards.index(card)]
        self.refresh_cards()
        self.reset_editor()

    def refresh_cards(self) -> None:
        for card in self.cards:
            self.cards_layout.removeWidget(card)
            card.hide()
            card.deleteLater()
        self.cards = []
        for index, picture in enumerate(self.pictures):
            card = AttachedPictureCard(picture, index + 1)
            card.edit_requested.connect(self.edit_picture)
            card.remove_requested.connect(self.remove_picture)
            self.cards.append(card)
            self.cards_layout.addWidget(card, index // 2, index % 2)
        self.count_badge.setText(str(len(self.pictures)))
        self.empty_label.setVisible(not self.pictures)
        self.count_changed.emit(len(self.pictures))

    def reset_editor(self) -> None:
        self.editing_index = None
        self.pending_picture = None
        self.image_drop_zone.blockSignals(True)
        self.image_drop_zone.clear_file()
        self.image_drop_zone.blockSignals(False)
        self.source_toggle.set_mode("manual")
        self.on_source_changed("manual")
        self.type_combo.setCurrentIndex(self.type_combo.findData(3))
        description = APIC_TYPES[3]
        used = {picture.description for picture in self.pictures}
        suffix = 2
        base = description
        while description in used:
            description = f"{base} ({suffix})"
            suffix += 1
        self.description_input.setText(description)
        self.editor_title.setText("Add New Image")
        self.confirm_button.setText("+ Add Image")
        self.editing_image_label.clear()

    def clear_all(self) -> None:
        self.load_draft([])

    def load_draft(self, pictures: list[MP3AttachedPictureDraft]) -> None:
        self.pictures = deepcopy(pictures)
        self.refresh_cards()
        self.reset_editor()

    def get_inputs(self) -> list[MP3AttachedPictureDraft]:
        if self.pending_picture is not None or self.editing_index is not None:
            raise ValueError("Confirm Add/Update Image or Cancel the picture edit before saving.")
        validate_attached_pictures(self.pictures)
        return deepcopy(self.pictures)
