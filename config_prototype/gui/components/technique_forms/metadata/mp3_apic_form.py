from copy import deepcopy
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QImageReader, QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from config_prototype.gui.components.technique_forms.metadata.mp3_apic_drafts import (
    APIC_IMAGE_EXTENSIONS,
    ApicImageDraft,
    apic_draft_structure_error,
)
from config_prototype.gui.paths import ICON_DIR
from src.core.stego.metadata_handlers.mp3_handler import APIC_TYPES
from src.gui.components.files_drop import FileDropWidget
from src.gui.components.gui_utils import (
    add_shadow_effect,
    create_icon_pixmap,
    format_file_size,
    truncate_text_middle,
)


TINT_CYCLE = ("blue", "purple", "green", "orange")


def _make_badge(text: str, color: str = "neutral") -> QLabel:
    badge = QLabel(text)
    badge.setObjectName("fileInfoBadge")
    badge.setProperty("badgeColor", color)
    return badge


class ApicImageCard(QFrame):
    """Preview and actions for one saved APIC image draft."""

    replace_requested = pyqtSignal(object)
    remove_requested = pyqtSignal(object)

    def __init__(
        self,
        draft: ApicImageDraft,
        *,
        tint: str = "blue",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.draft = draft
        self.setObjectName("apicCard")
        self.build_ui(tint)

    def build_ui(self, tint: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        preview = QFrame()
        preview.setObjectName("apicPreview")
        preview.setProperty("tintColor", tint)
        preview.setFixedHeight(120)
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(8, 8, 8, 8)

        type_name = APIC_TYPES[self.draft.picture_type]
        type_row = QHBoxLayout()
        type_row.addWidget(
            _make_badge(
                f"Type {self.draft.picture_type} - {type_name}",
                tint,
            )
        )
        type_row.addStretch()
        preview_layout.addLayout(type_row)

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(self.draft.image_path)
        if pixmap.isNull():
            pixmap = create_icon_pixmap(ICON_DIR / "photo.svg", size=28)
        else:
            pixmap = pixmap.scaled(
                72,
                72,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        image_label.setPixmap(pixmap)
        preview_layout.addWidget(image_label, 1)
        layout.addWidget(preview)

        info = QFrame()
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(10, 8, 10, 10)
        info_layout.setSpacing(4)

        image_path = Path(self.draft.image_path)
        name_label = QLabel(truncate_text_middle(image_path.name, 38))
        name_label.setObjectName("fileInfoName")
        name_label.setToolTip(str(image_path))
        info_layout.addWidget(name_label)

        if image_path.is_file():
            detail = (
                f"{image_path.suffix[1:].upper()} - "
                f"{format_file_size(image_path.stat().st_size)}"
            )
        else:
            detail = "File unavailable"
        detail_label = QLabel(detail)
        detail_label.setObjectName("fileInfoDetail")
        info_layout.addWidget(detail_label)

        if self.draft.description:
            description_label = QLabel(
                f'Description: "{self.draft.description}"'
            )
            description_label.setObjectName("fileInfoDetail")
            description_label.setWordWrap(True)
            info_layout.addWidget(description_label)

        button_row = QHBoxLayout()
        button_row.setSpacing(6)
        self.replace_button = QPushButton("Change Image")
        self.replace_button.setObjectName("SecondaryBtn")
        self.replace_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.replace_button.clicked.connect(
            lambda: self.replace_requested.emit(self)
        )

        self.remove_button = QPushButton()
        self.remove_button.setObjectName("btnRemoveFile")
        self.remove_button.setFixedSize(30, 30)
        self.remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_button.setIcon(
            QIcon(
                create_icon_pixmap(
                    ICON_DIR / "trash.svg",
                    color_hex="#F43F5E",
                    size=14,
                )
            )
        )
        self.remove_button.setToolTip("Remove attached picture")
        self.remove_button.clicked.connect(
            lambda: self.remove_requested.emit(self)
        )

        button_row.addWidget(self.replace_button, 1)
        button_row.addWidget(self.remove_button)
        info_layout.addLayout(button_row)
        layout.addWidget(info)


class MP3ApicImagesForm(QFrame):
    """Own the manual APIC image collection for one MP3 step draft."""

    changed = pyqtSignal()

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("mp3ApicImagesForm")
        self._drafts: list[ApicImageDraft] = []
        self.cards: list[ApicImageCard] = []
        self._pending_image_path: str | None = None
        self.build_ui()

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        self.cards_section = self._build_cards_section()
        self.add_form = self._build_add_form()
        layout.addWidget(self.cards_section)
        layout.addWidget(self.add_form)
        layout.addStretch()
        self._refresh_collection()

    def _build_cards_section(self) -> QFrame:
        section = QFrame()
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(8)

        header = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(
            create_icon_pixmap(ICON_DIR / "photo.svg", size=16)
        )
        title_label = QLabel("Attached Pictures (APIC)")
        title_label.setObjectName("cardTitle")
        self.count_badge = _make_badge("0")
        hint_label = QLabel(
            "Multiple images need different descriptions"
        )
        hint_label.setObjectName("hintLabel")

        header.addWidget(icon_label)
        header.addWidget(title_label)
        header.addWidget(self.count_badge)
        header.addStretch()
        header.addWidget(hint_label)
        section_layout.addLayout(header)

        self.cards_grid = QGridLayout()
        self.cards_grid.setSpacing(12)
        section_layout.addLayout(self.cards_grid)
        return section

    def _build_add_form(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)

        title_row = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(
            create_icon_pixmap(ICON_DIR / "photo.svg", size=16)
        )
        title_label = QLabel("Add New Image")
        title_label.setObjectName("cardTitle")
        title_row.addWidget(icon_label)
        title_row.addWidget(title_label)
        title_row.addStretch()
        layout.addLayout(title_row)

        form_row = QHBoxLayout()
        form_row.setSpacing(16)
        self.image_drop_zone = FileDropWidget(
            "Drop image here or click to browse",
            "JPEG and PNG formats only",
            icon_path=str(ICON_DIR / "upload.svg"),
            allowed_extensions=sorted(APIC_IMAGE_EXTENSIONS),
        )
        self.image_drop_zone.file_selected.connect(
            self.on_image_file_selected
        )
        form_row.addWidget(self.image_drop_zone, 1)

        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(8)

        type_label = QLabel("Picture Type")
        type_label.setObjectName("formLabel")
        self.type_combo = QComboBox()
        for type_id, type_name in APIC_TYPES.items():
            self.type_combo.addItem(f"{type_id} - {type_name}", type_id)
        settings_layout.addWidget(type_label)
        settings_layout.addWidget(self.type_combo)

        description_label = QLabel("Description")
        description_label.setObjectName("formLabel")
        self.description_input = QLineEdit()
        self.description_input.setObjectName("formInput")
        self.description_input.setPlaceholderText(
            "Optional for one image; unique when adding several"
        )
        settings_layout.addWidget(description_label)
        settings_layout.addWidget(self.description_input)
        settings_layout.addStretch()

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("SecondaryBtn")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reset_add_form)
        self.add_button = QPushButton("+ Add Image")
        self.add_button.setObjectName("PrimaryActionBtn")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.clicked.connect(self.confirm_add_image)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.add_button)
        settings_layout.addLayout(button_row)

        form_row.addLayout(settings_layout, 1)
        layout.addLayout(form_row)
        self._reset_picture_type()
        return card

    def _reset_picture_type(self) -> None:
        index = self.type_combo.findData(3)
        self.type_combo.setCurrentIndex(index if index >= 0 else 0)

    def on_image_file_selected(self, image_path: str) -> None:
        self._pending_image_path = image_path or None

    def confirm_add_image(self) -> bool:
        if not self._pending_image_path:
            return self.show_validation_warning(
                "Please select an image first."
            )

        candidate = ApicImageDraft(
            image_path=self._pending_image_path,
            picture_type=int(self.type_combo.currentData()),
            description=self.description_input.text().strip(),
        )
        error = self.draft_validation_error([*self._drafts, candidate])
        if error is not None:
            return self.show_validation_warning(error)

        self._drafts.append(candidate)
        self._refresh_collection()
        self.reset_add_form()
        self.changed.emit()
        return True

    def remove_image(self, card: ApicImageCard) -> None:
        if card.draft not in self._drafts:
            return
        self._drafts.remove(card.draft)
        self._refresh_collection()
        self.changed.emit()

    def replace_image(
        self,
        card: ApicImageCard,
        image_path: str | None = None,
    ) -> bool:
        if card.draft not in self._drafts:
            return False
        if image_path is None:
            patterns = " ".join(
                f"*{suffix}" for suffix in sorted(APIC_IMAGE_EXTENSIONS)
            )
            image_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select replacement image",
                "",
                f"Images ({patterns})",
            )
        if not image_path:
            return False

        replacement = deepcopy(card.draft)
        replacement.image_path = image_path
        candidate_drafts = [
            replacement if draft is card.draft else draft
            for draft in self._drafts
        ]
        error = self.draft_validation_error(candidate_drafts)
        if error is not None:
            return self.show_validation_warning(error)

        index = self._drafts.index(card.draft)
        self._drafts[index] = replacement
        self._refresh_collection()
        self.changed.emit()
        return True

    def reset_add_form(self) -> None:
        self.image_drop_zone.clear_file()
        self.description_input.clear()
        self._reset_picture_type()
        self._pending_image_path = None

    def _refresh_collection(self) -> None:
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

        self.cards = []
        for index, draft in enumerate(self._drafts):
            card = ApicImageCard(
                draft,
                tint=TINT_CYCLE[index % len(TINT_CYCLE)],
            )
            card.replace_requested.connect(self.replace_image)
            card.remove_requested.connect(self.remove_image)
            row, column = divmod(index, 2)
            self.cards_grid.addWidget(card, row, column)
            self.cards.append(card)

        count = len(self._drafts)
        self.count_badge.setText(str(count))
        self.cards_section.setVisible(count > 0)

    def load_draft(self, drafts: list[ApicImageDraft]) -> None:
        loaded_drafts = deepcopy(drafts)
        structure_error = apic_draft_structure_error(loaded_drafts)
        if structure_error is not None:
            raise ValueError(structure_error)

        self._drafts = loaded_drafts
        self.reset_add_form()
        self._refresh_collection()

    def export_draft(self) -> list[ApicImageDraft]:
        return deepcopy(self._drafts)

    def clear_all(self) -> None:
        self._drafts = []
        self.reset_add_form()
        self._refresh_collection()
        self.changed.emit()

    def image_count(self) -> int:
        return len(self._drafts)

    @staticmethod
    def draft_validation_error(
        drafts: list[ApicImageDraft],
    ) -> str | None:
        structure_error = apic_draft_structure_error(drafts)
        if structure_error is not None:
            return structure_error

        descriptions: set[str] = set()
        for draft in drafts:
            image_path = Path(draft.image_path)
            if not draft.image_path.strip():
                return "Each APIC image needs a file."
            if image_path.suffix.lower() not in APIC_IMAGE_EXTENSIONS:
                return "APIC images must use JPEG or PNG format."
            if not image_path.is_file():
                return f"APIC image is unavailable: {image_path.name}"
            if not QImageReader(str(image_path)).canRead():
                return f"APIC image cannot be read: {image_path.name}"

            description = draft.description.strip()
            if description in descriptions:
                return (
                    "APIC descriptions must be unique. Add a description "
                    "when using multiple images."
                )
            descriptions.add(description)

        return None

    def validate_draft(self) -> bool:
        error = self.draft_validation_error(self.export_draft())
        if error is not None:
            return self.show_validation_warning(error)
        return True

    def show_validation_warning(
        self,
        message: str,
        *,
        title: str = "Validation Error",
    ) -> bool:
        QMessageBox.warning(self, title, message)
        return False


__all__ = ["ApicImageCard", "MP3ApicImagesForm"]
