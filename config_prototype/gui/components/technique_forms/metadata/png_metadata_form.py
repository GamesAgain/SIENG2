from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config_prototype.gui.components.technique_forms.metadata.png_metadata_fields import (
    PNGCustomRow,
    PNGStandardField,
)
from config_prototype.gui.paths import ICON_DIR
from src.core.stego.metadata_handlers.png_handler import (
    MAX_KEYWORD_LENGTH,
    PNG_TEXT_KEYWORDS,
    STANDARD_KEYWORDS,
)
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap

if TYPE_CHECKING:
    from config_prototype.gui.components.technique_forms.metadata.metadata_embed_inputs import (
        PNGMetadataDraft,
    )


SUGGESTED_KEYWORDS = [
    keyword
    for keyword in PNG_TEXT_KEYWORDS
    if keyword not in STANDARD_KEYWORDS
]


def _make_count_badge(text: str) -> QLabel:
    badge = QLabel(text)
    badge.setObjectName("fileInfoBadge")
    badge.setProperty("badgeColor", "neutral")
    return badge


class PNGMetadataForm(QFrame):
    """Draft-backed PNG metadata fields without file or backend behavior."""

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.standard_fields: dict[str, PNGStandardField] = {}
        self.custom_rows: list[PNGCustomRow] = []
        self.build_ui()

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(16)

        self.standard_card = self.build_standard_card()
        self.custom_card = self.build_custom_card()
        self.add_card = self.build_add_card()
        self.content_layout.addWidget(self.standard_card)
        self.content_layout.addWidget(self.custom_card)
        self.content_layout.addWidget(self.add_card)
        self.content_layout.addStretch()

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("fileListScroll")
        self.scroll_area.setWidget(content)
        layout.addWidget(self.scroll_area)

    def build_standard_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)

        title_icon = QLabel()
        title_icon.setPixmap(
            create_icon_pixmap(ICON_DIR / "tags.svg", size=16)
        )
        title_label = QLabel("Standard Metadata")
        title_label.setObjectName("cardTitle")
        hint_label = QLabel("Always shown")
        hint_label.setObjectName("hintLabel")

        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(hint_label)
        layout.addWidget(title_container)

        fields_layout = QGridLayout()
        fields_layout.setHorizontalSpacing(20)
        fields_layout.setVerticalSpacing(12)
        for index, keyword in enumerate(STANDARD_KEYWORDS):
            field = PNGStandardField(keyword)
            self.standard_fields[keyword] = field
            row, column = divmod(index, 2)
            fields_layout.addWidget(field, row, column)
        layout.addLayout(fields_layout)
        return card

    def build_custom_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)

        title_icon = QLabel()
        title_icon.setPixmap(
            create_icon_pixmap(ICON_DIR / "file-dots.svg", size=16)
        )
        title_label = QLabel("Custom Metadata")
        title_label.setObjectName("cardTitle")
        self.custom_count_badge = _make_count_badge("0")
        hint_label = QLabel("Keys added manually")
        hint_label.setObjectName("hintLabel")

        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addWidget(self.custom_count_badge)
        title_layout.addStretch()
        title_layout.addWidget(hint_label)
        layout.addWidget(title_container)

        self.custom_rows_layout = QVBoxLayout()
        self.custom_rows_layout.setSpacing(8)
        layout.addLayout(self.custom_rows_layout)
        return card

    def build_add_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QHBoxLayout(card)
        layout.setSpacing(10)

        label = QLabel("Add Metadata")
        label.setObjectName("formLabel")

        self.add_keyword_combo = QComboBox()
        self.add_keyword_combo.setEditable(True)
        self.add_keyword_combo.addItems(SUGGESTED_KEYWORDS)
        self.add_keyword_combo.setCurrentIndex(-1)
        combo_input = self.add_keyword_combo.lineEdit()
        if combo_input is not None:
            combo_input.setPlaceholderText(
                "keyword (pick one or type a custom keyword)"
            )
            combo_input.setMaxLength(MAX_KEYWORD_LENGTH)

        self.add_button = QPushButton("+ Add")
        self.add_button.setObjectName("SecondaryBtn")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.clicked.connect(self.add_custom_from_combo)

        layout.addWidget(label)
        layout.addWidget(self.add_keyword_combo, 1)
        layout.addWidget(self.add_button)
        return card

    def add_custom_from_combo(self) -> None:
        keyword = self.add_keyword_combo.currentText().strip()
        self.add_custom_row(keyword)
        self.add_keyword_combo.setCurrentIndex(-1)
        self.add_keyword_combo.clearEditText()

    def add_custom_row(
        self,
        keyword: str = "",
        value: str = "",
    ) -> PNGCustomRow:
        row = PNGCustomRow(keyword, value)
        row.removed.connect(self.remove_custom_row)
        self.custom_rows.append(row)
        self.custom_rows_layout.addWidget(row)
        self.update_custom_count()
        return row

    def remove_custom_row(self, row: PNGCustomRow) -> None:
        if row not in self.custom_rows:
            return

        self.custom_rows.remove(row)
        row.hide()
        row.deleteLater()
        self.update_custom_count()

    def update_custom_count(self) -> None:
        self.custom_count_badge.setText(str(len(self.custom_rows)))

    def clear_all(self) -> None:
        for field in self.standard_fields.values():
            field.set_value(None)
        for row in list(self.custom_rows):
            self.remove_custom_row(row)

    def load_draft(self, draft: PNGMetadataDraft) -> None:
        entries = deepcopy(draft.entries)
        self.clear_all()

        for keyword, value in entries.items():
            standard_field = self.standard_fields.get(keyword)
            if standard_field is not None:
                standard_field.set_value(value)
            else:
                self.add_custom_row(keyword, value)

    def export_draft(self) -> PNGMetadataDraft:
        from config_prototype.gui.components.technique_forms.metadata.metadata_embed_inputs import (
            PNGMetadataDraft,
        )

        entries: dict[str, str] = {}
        for keyword, field in self.standard_fields.items():
            if not field.is_empty():
                entries[keyword] = field.get_value()

        for row in self.custom_rows:
            if not row.is_empty():
                entries[row.get_keyword()] = row.get_value()

        return PNGMetadataDraft(entries=entries)

    def validate_draft(self) -> bool:
        """Validate current controls before their draft is saved."""
        has_metadata = any(
            not field.is_empty()
            for field in self.standard_fields.values()
        )
        seen_custom_keywords: set[str] = set()

        for row in self.custom_rows:
            keyword = row.get_keyword()
            if not keyword:
                row.keyword_input.setFocus()
                return self.show_validation_warning(
                    "Please enter a keyword for every custom metadata row."
                )

            keyword_error = self.keyword_validation_error(keyword)
            if keyword_error is not None:
                row.keyword_input.setFocus()
                return self.show_validation_warning(keyword_error)

            if keyword in self.standard_fields:
                row.keyword_input.setFocus()
                return self.show_validation_warning(
                    f"'{keyword}' is a standard metadata keyword. "
                    "Use its Standard Metadata field instead."
                )

            if keyword in seen_custom_keywords:
                row.keyword_input.setFocus()
                return self.show_validation_warning(
                    f"Metadata keyword '{keyword}' is used more than once."
                )
            seen_custom_keywords.add(keyword)

            if not row.get_value():
                row.value_input.setFocus()
                return self.show_validation_warning(
                    f"Please enter a value for custom metadata keyword "
                    f"'{keyword}'."
                )
            has_metadata = True

        if not has_metadata:
            return self.show_validation_warning(
                "Please add at least one PNG metadata value."
            )
        return True

    @staticmethod
    def keyword_validation_error(keyword: str) -> str | None:
        """Return a message when a keyword violates PNG text-key rules."""
        try:
            encoded_keyword = keyword.encode("latin-1", "strict")
        except UnicodeEncodeError:
            return (
                f"Metadata keyword '{keyword}' must use Latin-1 "
                "characters."
            )

        if not 1 <= len(encoded_keyword) <= MAX_KEYWORD_LENGTH:
            return (
                "PNG metadata keywords must be between 1 and "
                f"{MAX_KEYWORD_LENGTH} bytes."
            )

        if any(
            byte < 32 or 127 <= byte <= 160
            for byte in encoded_keyword
        ):
            return (
                f"Metadata keyword '{keyword}' contains characters "
                "not allowed by PNG."
            )

        if "  " in keyword:
            return (
                f"Metadata keyword '{keyword}' cannot contain "
                "consecutive spaces."
            )
        return None

    def show_validation_warning(
        self,
        message: str,
        *,
        title: str = "Validation Error",
    ) -> bool:
        QMessageBox.warning(self, title, message)
        return False
