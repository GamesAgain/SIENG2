"""
PNG text metadata editor (Standard / Custom / Add Metadata cards).

The form only holds values; it never writes the file.
- original : text of the file when it was opened (to see what the user added or modified)
- entries  : every keyword/value the user wants the file to have
Standalone saves with MetadataPNGHandler.write_text(); a pipeline draft can keep get_entries() as-is.
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from src.core.stego.metadata_handlers.png_handler import (
    MAX_KEYWORD_LENGTH, PNG_TEXT_KEYWORDS, STANDARD_KEYWORDS, MetadataPNGHandler,
)
from src.gui.components.gui_utils import add_shadow_effect
from src.gui.components.widgets.file_info_bar import FileInfoBar
from src.gui.features.embed.forms.metadata.common import (
    PAYLOAD_REQUIRED, SecretPreview, make_badge, make_card_header, make_payload_badge,
    make_remove_button, make_value_input, set_payload_mark,
)
from src.gui.features.embed.forms.metadata.file_info import get_png_file_info

# keyword มาตรฐานที่ไม่ได้แสดงใน Standard card -> ให้เลือกจาก combo ตอน Add
SUGGESTED_KEYWORDS = [key for key in PNG_TEXT_KEYWORDS if key not in STANDARD_KEYWORDS]


class PNGStandardField(QFrame):
    """A fixed keyword (Title, Author ...) with an editable value. Empty = not saved."""

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
        self.payload_badge = make_payload_badge()
        header.addWidget(self.payload_badge)
        header.addStretch()
        layout.addLayout(header)

        self.value_input = make_value_input()
        layout.addWidget(self.value_input)

    def get_value(self) -> str:
        return self.value_input.text()

    def set_value(self, value: str) -> None:
        self.value_input.setText(value)

    def set_payload(self, on: bool) -> None:
        set_payload_mark(self.value_input, on)
        self.payload_badge.setVisible(on)


class PNGCustomRow(QFrame):
    """An editable keyword/value row with a remove button."""

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
        self.delete_button = make_remove_button("Remove metadata")
        self.delete_button.clicked.connect(lambda: self.removed.emit(self))
        self.payload_badge = make_payload_badge()
        header.addWidget(label)
        header.addWidget(self.payload_badge)
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
        self.value_input = make_value_input("value", value)
        inputs.addWidget(self.keyword_input)
        inputs.addWidget(self.value_input, 1)
        layout.addLayout(inputs)

    def get_keyword(self) -> str:
        return self.keyword_input.text()

    def get_value(self) -> str:
        return self.value_input.text()

    def is_blank(self) -> bool:
        return not self.get_keyword() and not self.get_value()

    def set_payload(self, on: bool) -> None:
        set_payload_mark(self.value_input, on)
        self.payload_badge.setVisible(on)


class PNGMetadataForm(QFrame):
    """PNG file summary + editable text metadata + a preview of what the receiver will see."""

    change_file_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.handler = MetadataPNGHandler()
        self.original: dict[str, str] = {}
        self.standard_fields: dict[str, PNGStandardField] = {}
        self.custom_rows: list[PNGCustomRow] = []
        self.build_ui()
        self.update_preview()

    # --- UI construction ---

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.file_info_bar = FileInfoBar()
        self.file_info_bar.change_file_requested.connect(self.change_file_requested.emit)
        layout.addWidget(self.file_info_bar)

        # field ที่ผู้ใช้เพิ่ม/แก้ = สิ่งที่ฝั่งถอดจะเห็น (คำนวณสดทุกครั้งที่พิมพ์)
        self.secret_preview = SecretPreview()
        layout.addWidget(self.secret_preview)

        content = QWidget()
        content.setObjectName("fileListContainer")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)
        content_layout.addWidget(self.build_standard_card())
        content_layout.addWidget(self.build_custom_card())
        content_layout.addWidget(self.build_add_card())
        content_layout.addStretch()

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("fileListScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(content)
        layout.addWidget(self.scroll_area, 1)

    def build_standard_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        layout.addWidget(make_card_header("Standard Metadata", "tags.svg", "Always shown"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for index, keyword in enumerate(STANDARD_KEYWORDS):
            field = PNGStandardField(keyword)
            field.value_input.textChanged.connect(self.update_preview)
            self.standard_fields[keyword] = field
            row, column = divmod(index, 2)
            grid.addWidget(field, row, column)
        layout.addLayout(grid)
        return card

    def build_custom_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        self.custom_count_badge = make_badge("0")
        layout.addWidget(make_card_header(
            "Custom Metadata", "file-dots.svg", "Other keywords in this file or added by you", self.custom_count_badge,
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

    # --- Custom rows ---

    def add_custom_from_combo(self) -> None:
        keyword = self.add_keyword_combo.currentText().strip()
        self.add_keyword_combo.setCurrentIndex(-1)
        self.add_keyword_combo.clearEditText()

        # keyword ที่มีอยู่แล้ว -> พาไปที่ช่องเดิม แทนการเพิ่มแถวซ้ำ
        existing = self.value_input_of(keyword)
        if existing is not None:
            existing.setFocus()
            return
        row = self.add_custom_row(keyword)
        (row.value_input if keyword else row.keyword_input).setFocus()

    def add_custom_row(self, keyword: str = "", value: str = "") -> PNGCustomRow:
        row = PNGCustomRow(keyword, value)
        row.removed.connect(self.remove_custom_row)
        row.keyword_input.textChanged.connect(self.update_preview)
        row.value_input.textChanged.connect(self.update_preview)
        self.custom_rows.append(row)
        self.custom_rows_layout.addWidget(row)
        self.custom_count_badge.setText(str(len(self.custom_rows)))
        self.update_preview()
        return row

    def remove_custom_row(self, row: PNGCustomRow) -> None:
        if row not in self.custom_rows:
            return
        self.custom_rows.remove(row)
        self.custom_rows_layout.removeWidget(row)
        row.hide()
        row.deleteLater()
        self.custom_count_badge.setText(str(len(self.custom_rows)))
        self.update_preview()

    def value_input_of(self, keyword: str) -> QLineEdit | None:
        """The value box already used by `keyword` (standard or custom), or None."""
        if not keyword:
            return None
        if keyword in self.standard_fields:
            return self.standard_fields[keyword].value_input
        for row in self.custom_rows:
            if row.get_keyword() == keyword:
                return row.value_input
        return None

    # --- Values ---

    def load_file(self, file_path: str) -> None:
        """Read the PNG and fill the form. Raises (OSError / ValueError) if the file cannot be read."""
        info = get_png_file_info(file_path)
        text = self.handler.read_text(file_path)
        hidden_before = list(self.handler.read_secret(file_path))

        self.set_original(text)
        self.set_entries(text)
        self.file_info_bar.update_info(**info)
        self.secret_preview.show_previous_secret(hidden_before)

    def load_empty(self) -> None:
        """No file to read: start with no text (an output made from a JPG / WebP ... is a PNG without text chunks)."""
        self.set_original({})
        self.set_entries({})
        self.secret_preview.show_previous_secret([])

    def set_original(self, original: dict[str, str]) -> None:
        """The values to compare against (what the file has before this edit)."""
        self.original = dict(original)
        self.update_preview()

    def set_entries(self, entries: dict[str, str]) -> None:
        """Replace every value in the form: standard keywords in their fields, the rest as custom rows."""
        for field in self.standard_fields.values():
            field.set_value("")
        for row in list(self.custom_rows):
            self.remove_custom_row(row)
        for keyword, value in entries.items():
            if keyword in self.standard_fields:
                self.standard_fields[keyword].set_value(value)
            else:
                self.add_custom_row(keyword, value)
        self.update_preview()

    def current_entries(self) -> dict[str, str]:
        """What the form shows now, without checking (used for the live preview)."""
        entries = {}
        for keyword, field in self.standard_fields.items():
            if field.get_value():  # ช่องว่าง = ไม่บันทึก keyword นี้ (ลบ)
                entries[keyword] = field.get_value()
        for row in self.custom_rows:
            if row.get_keyword():
                entries[row.get_keyword()] = row.get_value()
        return entries

    def get_entries(self) -> dict[str, str]:
        """Checked keyword/value pairs to save. Raises ValueError and focuses the wrong box."""
        seen = set()
        for row in self.custom_rows:
            if row.is_blank():
                continue  # แถวที่ยังไม่ได้กรอกอะไรเลย ไม่นับ
            keyword = row.get_keyword()
            try:
                self.handler.check_keyword(keyword)
            except ValueError:
                row.keyword_input.setFocus()
                raise
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
        entries = self.current_entries()
        if not self.handler.changed_keys(self.original, entries):
            raise ValueError(PAYLOAD_REQUIRED)
        return entries

    def clear_all(self) -> None:
        self.set_entries({})
        self.set_original({})
        self.secret_preview.show_previous_secret([])
        self.add_keyword_combo.setCurrentIndex(-1)
        self.add_keyword_combo.clearEditText()

    def update_preview(self) -> None:
        """Receiver preview + PAYLOAD marks on the fields that were added or modified."""
        changed = self.handler.changed_keys(self.original, self.current_entries())
        for keyword, field in self.standard_fields.items():
            field.set_payload(keyword in changed)
        for row in self.custom_rows:
            row.set_payload(row.get_keyword() in changed)
        self.secret_preview.show_changes(changed)

    def key_labels(self, keys: list[str]) -> list[str]:
        """PNG keywords are already readable (same API as the MP3 form)."""
        return list(keys)
