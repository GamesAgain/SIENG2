"""
MP3 "Text Frames" tab: Standard Frames / Other Frames / Add Frame cards.

Every value is an MP3Field, the same object the core saves.
- simple text frame (T***)  -> one text box
- frame that can repeat     -> one row per MP3Field:
  TXXX (desc + text) · WXXX (desc + URL) · COMM / USLT (lang + desc + text) · W*** (URL)
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from src.core.stego.metadata_handlers.mp3_handler import FRAME_INFO, STANDARD_FRAMES, MetadataMP3Handler, MP3Field
from src.gui.components.gui_utils import add_shadow_effect
from src.gui.features.embed.forms.metadata.common import (
    make_badge, make_card_header, make_remove_button, make_value_input,
)

# ช่องกรอกของ frame ที่มีได้หลายตัว (1 แถว = 1 MP3Field)
ROW_INPUTS = {
    "TXXX": ("desc", "text"),
    "WXXX": ("desc", "text"),
    "COMM": ("lang", "desc", "text"),
    "USLT": ("lang", "desc", "text"),
}
LANGUAGES = ["eng", "tha", "und"]
PLACEHOLDERS = {"TDRC": "YYYY or YYYY-MM-DD", "TDOR": "YYYY", "TRCK": "3/12", "TPOS": "1/2"}


def row_inputs(frame_id: str) -> tuple[str, ...] | None:
    """Inputs of one row, or None for a simple text frame (one text box)."""
    if frame_id in ROW_INPUTS:
        return ROW_INPUTS[frame_id]
    if frame_id.startswith("W"):
        return ("text",)  # URL frame (WOAR ...) มีได้หลายตัว แยกกันด้วย url
    return None


class FrameRow(QFrame):
    """One instance of a repeatable frame = one MP3Field."""

    removed = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, frame_id: str, parent=None):
        super().__init__(parent)
        self.frame_id = frame_id
        self.loaded_text = None  # เนื้อเพลง (USLT) จากไฟล์: กล่องหลายบรรทัดเปลี่ยน \r\n เป็น \n
        self.inputs = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for name in row_inputs(frame_id):
            if name == "lang":
                widget = QComboBox()
                widget.setEditable(True)
                widget.addItems(LANGUAGES)
                widget.setFixedWidth(90)
                widget.lineEdit().setMaxLength(3)
                widget.setToolTip("Language: three-letter code")
                widget.currentTextChanged.connect(self.changed.emit)
            elif name == "text" and frame_id == "USLT":
                widget = QPlainTextEdit()
                widget.setObjectName("payloadTextArea")
                widget.setFixedHeight(70)
                widget.setPlaceholderText("Lyrics...")
                widget.textChanged.connect(self.changed.emit)
            else:
                if name == "desc":
                    placeholder = "description (optional)"
                elif frame_id.startswith("W"):
                    placeholder = "https://..."
                else:
                    placeholder = "text"
                widget = make_value_input(placeholder)
                widget.textChanged.connect(self.changed.emit)
            self.inputs[name] = widget
            layout.addWidget(widget, 2 if name == "text" else 1)

        remove_button = make_remove_button()
        remove_button.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(remove_button, 0, Qt.AlignmentFlag.AlignTop)

    def value(self, name: str) -> str:
        widget = self.inputs[name]
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, QPlainTextEdit):
            text = widget.toPlainText()
            # ยังไม่ได้แก้ -> คืนข้อความเดิม (ไม่ให้นับเป็น "แก้" เพราะ \r\n หายไป)
            if self.loaded_text is not None and text == self.loaded_text.replace("\r\n", "\n").replace("\r", "\n"):
                return self.loaded_text
            return text
        return widget.text()

    def set_field(self, field: MP3Field) -> None:
        for name, widget in self.inputs.items():
            value = getattr(field, name)
            if isinstance(widget, QComboBox):
                widget.setCurrentText(value)
            elif isinstance(widget, QPlainTextEdit):
                self.loaded_text = value
                widget.setPlainText(value)
            else:
                widget.setText(value)

    def to_field(self) -> MP3Field:
        return MP3Field(self.frame_id, **{name: self.value(name) for name in self.inputs})

    def is_blank(self) -> bool:
        # ภาษาที่ตั้งไว้ให้อย่างเดียว ไม่นับว่ากรอกแล้ว
        return not any(self.value(name) for name in self.inputs if name != "lang")

    def focus(self) -> None:
        name = "desc" if "desc" in self.inputs else "text"
        self.inputs[name].setFocus()


class FrameField(QFrame):
    """One frame ID: a text box (simple frame) or a list of rows (repeatable frame)."""

    removed = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, frame_id: str, removable: bool = False, parent=None):
        super().__init__(parent)
        self.frame_id = frame_id
        self.rows: list[FrameRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        name, description = FRAME_INFO.get(frame_id, (frame_id, ""))
        label = QLabel(name)
        label.setObjectName("formLabel")
        label.setToolTip(description)
        header.addWidget(label)
        header.addWidget(make_badge(frame_id))
        header.addStretch()
        if row_inputs(frame_id):
            hint = QLabel("Can have multiple")
            hint.setObjectName("hintLabel")
            header.addWidget(hint)
        if removable:
            remove_button = make_remove_button("Remove frame")
            remove_button.clicked.connect(lambda: self.removed.emit(self))
            header.addWidget(remove_button)
        layout.addLayout(header)

        if row_inputs(frame_id):
            self.rows_layout = QVBoxLayout()
            self.rows_layout.setSpacing(6)
            layout.addLayout(self.rows_layout)
            add_button = QPushButton(f"+ Add {frame_id}")
            add_button.setObjectName("SecondaryBtn")
            add_button.setCursor(Qt.CursorShape.PointingHandCursor)
            add_button.clicked.connect(lambda: self.add_row().focus())
            layout.addWidget(add_button, alignment=Qt.AlignmentFlag.AlignLeft)
            self.add_row()
        else:
            self.value_input = make_value_input(PLACEHOLDERS.get(frame_id, ""))
            self.value_input.textChanged.connect(self.changed.emit)
            layout.addWidget(self.value_input)

    def has_rows(self) -> bool:
        return row_inputs(self.frame_id) is not None

    def add_row(self, field: MP3Field | None = None) -> FrameRow:
        row = FrameRow(self.frame_id)
        if field is not None:
            row.set_field(field)
        row.removed.connect(self.remove_row)
        row.changed.connect(self.changed.emit)
        self.rows.append(row)
        self.rows_layout.addWidget(row)
        self.changed.emit()
        return row

    def remove_row(self, row: FrameRow) -> None:
        if row not in self.rows:
            return
        self.rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.hide()
        row.deleteLater()
        if not self.rows:
            self.add_row()  # เหลือแถวว่างไว้ 1 แถวให้กรอกเสมอ
        self.changed.emit()

    def set_fields(self, fields: list[MP3Field]) -> None:
        if not self.has_rows():
            self.value_input.setText(fields[-1].text if fields else "")
            return
        for row in list(self.rows):
            self.rows.remove(row)
            self.rows_layout.removeWidget(row)
            row.hide()
            row.deleteLater()
        for field in fields:
            self.add_row(field)
        if not self.rows:
            self.add_row()

    def get_fields(self) -> list[MP3Field]:
        """Filled values only: an empty box / blank row = the frame is not saved."""
        if self.has_rows():
            return [row.to_field() for row in self.rows if not row.is_blank()]
        text = self.value_input.text()
        return [MP3Field(self.frame_id, text=text)] if text else []

    def focus(self) -> None:
        if self.has_rows():
            self.rows[0].focus()
        else:
            self.value_input.setFocus()


class MP3TextFramesForm(QFrame):
    """Standard Frames (always shown), Other Frames (from the file or added) and Add Frame."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.handler = MetadataMP3Handler()
        self.standard_fields: dict[str, FrameField] = {}
        self.other_fields: dict[str, FrameField] = {}

        self.setObjectName("fileListContainer")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self.build_standard_card())
        layout.addWidget(self.build_other_card())
        layout.addWidget(self.build_add_card())
        layout.addStretch()

    # --- UI construction ---

    def build_standard_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        layout.addWidget(make_card_header("Standard Frames", "tags.svg", "Always shown"))

        # frame ข้อความธรรมดา 2 คอลัมน์ / frame ที่มีหลายแถว (COMM) เต็มความกว้างด้านล่าง
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        simple_ids = [frame_id for frame_id in STANDARD_FRAMES if not row_inputs(frame_id)]
        for index, frame_id in enumerate(simple_ids):
            row, column = divmod(index, 2)
            grid.addWidget(self.new_standard_field(frame_id), row, column)
        layout.addLayout(grid)
        for frame_id in STANDARD_FRAMES:
            if row_inputs(frame_id):
                layout.addWidget(self.new_standard_field(frame_id))
        return card

    def new_standard_field(self, frame_id: str) -> FrameField:
        field = FrameField(frame_id)
        field.changed.connect(self.changed.emit)
        self.standard_fields[frame_id] = field
        return field

    def build_other_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        self.other_count_badge = make_badge("0")
        layout.addWidget(make_card_header(
            "Other Frames", "file-dots.svg", "Other text and URL frames in this file or added by you",
            self.other_count_badge,
        ))
        self.other_layout = QVBoxLayout()
        self.other_layout.setSpacing(12)
        layout.addLayout(self.other_layout)
        return card

    def build_add_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QHBoxLayout(card)
        layout.setSpacing(10)
        label = QLabel("Add Frame")
        label.setObjectName("formLabel")
        self.add_frame_combo = QComboBox()
        self.add_frame_button = QPushButton("+ Add")
        self.add_frame_button.setObjectName("SecondaryBtn")
        self.add_frame_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_frame_button.clicked.connect(self.add_selected_frame)
        layout.addWidget(label)
        layout.addWidget(self.add_frame_combo, 1)
        layout.addWidget(self.add_frame_button)
        self.refresh_add_options()
        return card

    # --- Other frames ---

    def addable_frame_ids(self) -> list[str]:
        """Text/URL frames from FRAME_INFO that are not on the page yet (APIC has its own tab)."""
        return sorted(
            frame_id for frame_id in FRAME_INFO
            if self.handler.is_editable(frame_id) and frame_id != "APIC"
            and frame_id not in STANDARD_FRAMES and frame_id not in self.other_fields
        )

    def refresh_add_options(self) -> None:
        self.add_frame_combo.clear()
        for frame_id in self.addable_frame_ids():
            self.add_frame_combo.addItem(f"{frame_id} — {FRAME_INFO[frame_id][0]}", frame_id)
        self.add_frame_button.setEnabled(self.add_frame_combo.count() > 0)

    def add_selected_frame(self) -> None:
        frame_id = self.add_frame_combo.currentData()
        if frame_id:
            self.add_other_field(frame_id).focus()

    def add_other_field(self, frame_id: str) -> FrameField:
        # frame จากไฟล์ที่ไม่มีใน FRAME_INFO (เช่น TCMP) ก็เพิ่มได้ ใช้รหัส frame เป็นชื่อ
        field = FrameField(frame_id, removable=True)
        field.removed.connect(self.remove_other_field)
        field.changed.connect(self.changed.emit)
        self.other_fields[frame_id] = field
        self.other_layout.addWidget(field)
        self.other_count_badge.setText(str(len(self.other_fields)))
        self.refresh_add_options()
        self.changed.emit()
        return field

    def remove_other_field(self, field: FrameField) -> None:
        if self.other_fields.get(field.frame_id) is not field:
            return
        del self.other_fields[field.frame_id]
        self.other_layout.removeWidget(field)
        field.hide()
        field.deleteLater()
        self.other_count_badge.setText(str(len(self.other_fields)))
        self.refresh_add_options()
        self.changed.emit()

    # --- Values ---

    def set_fields(self, fields: list[MP3Field]) -> None:
        """Show these fields: standard frames in their boxes, the rest under Other Frames."""
        groups: dict[str, list[MP3Field]] = {}
        for field in fields:
            groups.setdefault(field.frame_id, []).append(field)

        for frame_id, standard_field in self.standard_fields.items():
            standard_field.set_fields(groups.pop(frame_id, []))
        for field in list(self.other_fields.values()):
            self.remove_other_field(field)
        for frame_id, group in groups.items():
            self.add_other_field(frame_id).set_fields(group)
        self.changed.emit()

    def get_fields(self) -> list[MP3Field]:
        fields = []
        for field in [*self.standard_fields.values(), *self.other_fields.values()]:
            fields.extend(field.get_fields())
        return fields
