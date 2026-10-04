from dataclasses import dataclass, field

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from src.core.stego.metadata_handlers.png_handler import (
    MAX_KEYWORD_LENGTH, PNG_TEXT_KEYWORDS, STANDARD_KEYWORDS, MetadataPNGHandler,
)
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap
from src.gui.components.widgets.file_info_bar import FileInfoBar
from src.gui.features.embed.forms.metadata.file_info import get_png_file_info
from src.path import svg_path


SUGGESTED_KEYWORDS = [key for key in PNG_TEXT_KEYWORDS if key not in STANDARD_KEYWORDS]


@dataclass
class PNGMetadataDraft:
    """Editable PNG text metadata for standalone and configurable forms."""

    entries: dict[str, str] = field(default_factory=dict)


def make_badge(text: str) -> QLabel:
    badge = QLabel(text)
    badge.setObjectName("fileInfoBadge")
    badge.setProperty("badgeColor", "neutral")
    return badge


class PNGStandardField(QFrame):
    """A fixed metadata keyword with an editable value."""

    def __init__(self, keyword: str, parent=None):
        super().__init__(parent)
        self.keyword = keyword
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)
        name, description = PNG_TEXT_KEYWORDS[keyword]
        label = QLabel(name)
        label.setObjectName("formLabel")
        label.setToolTip(description)
        header.addWidget(label)
        header.addWidget(make_badge(keyword))
        header.addStretch()
        layout.addLayout(header)

        self.value_input = QLineEdit()
        self.value_input.setObjectName("formInput")
        layout.addWidget(self.value_input)

    def get_value(self) -> str:
        return self.value_input.text().strip()

    def set_value(self, value: str | None) -> None:
        self.value_input.setText(value or "")


class PNGCustomRow(QFrame):
    """An editable keyword/value row with a remove action."""

    removed = pyqtSignal(object)

    def __init__(self, keyword: str = "", value: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("fileItemRow")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        label = QLabel("Custom Keyword")
        label.setObjectName("fileItemName")
        self.delete_button = QPushButton()
        self.delete_button.setObjectName("btnRemoveFile")
        self.delete_button.setFixedSize(26, 26)
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.setToolTip("Remove metadata")
        self.delete_button.setIcon(QIcon(create_icon_pixmap(
            svg_path("x.svg"), size=12, color_hex="#F43F5E",
        )))
        self.delete_button.clicked.connect(lambda: self.removed.emit(self))
        header.addWidget(label)
        header.addStretch()
        header.addWidget(self.delete_button)
        layout.addLayout(header)

        inputs = QHBoxLayout()
        inputs.setSpacing(6)
        self.keyword_input = QLineEdit(keyword)
        self.keyword_input.setObjectName("formInput")
        self.keyword_input.setPlaceholderText("keyword")
        self.keyword_input.setMaxLength(MAX_KEYWORD_LENGTH)
        self.keyword_input.setFixedWidth(220)
        self.value_input = QLineEdit(value)
        self.value_input.setObjectName("formInput")
        self.value_input.setPlaceholderText("value")
        inputs.addWidget(self.keyword_input)
        inputs.addWidget(self.value_input, 1)
        layout.addLayout(inputs)

    def get_keyword(self) -> str:
        return self.keyword_input.text().strip()

    def get_value(self) -> str:
        return self.value_input.text().strip()


class PNGMetadataForm(QFrame):
    """PNG file summary and editable metadata controls, before save integration."""

    change_file_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.standard_fields: dict[str, PNGStandardField] = {}
        self.custom_rows: list[PNGCustomRow] = []
        self.build_ui()

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.file_info_bar = FileInfoBar()
        layout.addWidget(self.file_info_bar)
        self.file_info_bar.change_file_requested.connect(self.change_file_requested.emit)

        content = QWidget()
        content.setObjectName("fileListContainer")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)
        self.standard_card = self.build_standard_card()
        self.custom_card = self.build_custom_card()
        self.add_card = self.build_add_card()
        content_layout.addWidget(self.standard_card)
        content_layout.addWidget(self.custom_card)
        content_layout.addWidget(self.add_card)
        content_layout.addStretch()

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("fileListScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(content)
        layout.addWidget(self.scroll_area, 1)

    def _build_card_header(self, title: str, icon: str, hint: str, badge=None) -> QFrame:
        header = QFrame()
        layout = QHBoxLayout(header)
        icon_label = QLabel()
        icon_label.setPixmap(create_icon_pixmap(svg_path(icon), size=16))
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        hint_label = QLabel(hint)
        hint_label.setObjectName("hintLabel")
        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        if badge is not None:
            layout.addWidget(badge)
        layout.addStretch()
        layout.addWidget(hint_label)
        return header

    def build_standard_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        layout.addWidget(self._build_card_header("Standard Metadata", "tags.svg", "Always shown"))

        fields = QGridLayout()
        fields.setHorizontalSpacing(20)
        fields.setVerticalSpacing(12)
        fields.setColumnStretch(0, 1)
        fields.setColumnStretch(1, 1)
        for index, keyword in enumerate(STANDARD_KEYWORDS):
            field = PNGStandardField(keyword)
            self.standard_fields[keyword] = field
            row, column = divmod(index, 2)
            fields.addWidget(field, row, column)
        layout.addLayout(fields)
        return card

    def build_custom_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        self.custom_count_badge = make_badge("0")
        layout.addWidget(self._build_card_header(
            "Custom Metadata", "file-dots.svg", "Keys added manually", self.custom_count_badge,
        ))
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
        self.add_keyword_combo.lineEdit().setPlaceholderText("keyword (pick one or type a custom keyword)")
        self.add_keyword_combo.lineEdit().setMaxLength(MAX_KEYWORD_LENGTH)
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

    def add_custom_row(self, keyword: str = "", value: str = "") -> PNGCustomRow:
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
        self.custom_rows_layout.removeWidget(row)
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
        self.add_keyword_combo.setCurrentIndex(-1)
        self.add_keyword_combo.clearEditText()

    def load_draft(self, draft: PNGMetadataDraft) -> None:
        """Replace editor values, leaving the selected-file summary unchanged."""
        entries = dict(draft.entries)
        self.clear_all()
        for keyword, value in entries.items():
            standard_field = self.standard_fields.get(keyword)
            if standard_field is not None:
                standard_field.set_value(value)
            else:
                self.add_custom_row(keyword, value)

    def get_inputs(self) -> PNGMetadataDraft:
        """Return a new validated draft from current controls."""
        self.validate_inputs()
        entries = {}
        for keyword, standard_field in self.standard_fields.items():
            value = standard_field.get_value()
            if value:
                entries[keyword] = value
        for row in self.custom_rows:
            keyword = row.get_keyword()
            if keyword:
                entries[keyword] = row.get_value()
        return PNGMetadataDraft(entries=entries)

    @staticmethod
    def keyword_validation_error(keyword: str) -> str | None:
        try:
            encoded = keyword.encode("latin-1")
        except UnicodeEncodeError:
            return "PNG keywords must use Latin-1 characters. Values may use Unicode."
        if not 1 <= len(encoded) <= MAX_KEYWORD_LENGTH:
            return f"PNG keywords must contain 1–{MAX_KEYWORD_LENGTH} bytes."
        if any(byte < 32 or 127 <= byte <= 160 for byte in encoded):
            return "PNG keywords contain an invalid character."
        if keyword != keyword.strip(" ") or "  " in keyword:
            return "PNG keywords cannot have leading, trailing, or consecutive spaces."
        return None

    def validate_inputs(self) -> None:
        """Reject incomplete/duplicate rows before converting them to a dict."""
        seen = set()
        for row in self.custom_rows:
            keyword = row.keyword_input.text()
            error = self.keyword_validation_error(keyword)
            if error:
                row.keyword_input.setFocus()
                raise ValueError(error)
            if keyword in self.standard_fields:
                row.keyword_input.setFocus()
                raise ValueError(f"'{keyword}' is a Standard Metadata field. Edit it there.")
            if keyword in seen:
                row.keyword_input.setFocus()
                raise ValueError(f"Metadata keyword '{keyword}' is used more than once.")
            if not row.get_value():
                row.value_input.setFocus()
                raise ValueError(f"Enter a value for '{keyword}'.")
            seen.add(keyword)
        # An empty draft is valid: saving it removes all text metadata.

    def load_file(self, file_path: str) -> None:
        """Read all PNG text metadata and populate Standard/Custom controls."""
        info = get_png_file_info(file_path)
        entries = MetadataPNGHandler().read_itxt_chunk(file_path)
        self.load_draft(PNGMetadataDraft(entries=entries))
        self.file_info_bar.update_info(**info)
