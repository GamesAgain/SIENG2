"""MP3 text/URL frame controls and validated input drafts."""

from copy import deepcopy

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QVBoxLayout,
)

from src.core.stego.metadata_handlers.mp3_handler import FRAME_INFO, STANDARD_FRAMES
from src.gui.features.embed.forms.metadata.mp3_draft import (
    COMPLEX_FIELDS, MP3SimpleFrameDraft, MP3ComplexFrameDraft, MP3FrameInstanceDraft,
    MP3TextFramesDraft, is_simple_frame, validate_text_frames,
)
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap
from src.path import svg_path


def make_badge(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("fileInfoBadge")
    label.setProperty("badgeColor", "neutral")
    return label


def make_remove_button() -> QPushButton:
    button = QPushButton()
    button.setObjectName("btnRemoveFile")
    button.setFixedSize(26, 26)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip("Remove")
    button.setIcon(QIcon(create_icon_pixmap(svg_path("x.svg"), size=12, color_hex="#F43F5E")))
    return button


class TextFrameField(QFrame):
    """A simple frame value, or a collection of structured frame instances."""

    removed = pyqtSignal(object)

    def __init__(self, frame_id: str, removable: bool = False, parent=None):
        super().__init__(parent)
        if frame_id not in COMPLEX_FIELDS and not is_simple_frame(frame_id):
            raise ValueError(f"Unsupported text frame: {frame_id}")
        self.frame_id = frame_id
        self.loaded_values: list[str] = []
        self.loaded_display = ""
        self.instances: list[FrameInstanceRow] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        header = QHBoxLayout()
        name, description = FRAME_INFO[frame_id]
        label = QLabel(name)
        label.setObjectName("formLabel")
        label.setToolTip(description)
        header.addWidget(label)
        header.addWidget(make_badge(frame_id))
        header.addStretch()
        if frame_id in COMPLEX_FIELDS:
            hint = QLabel("Can have multiple instances")
            hint.setObjectName("hintLabel")
            header.addWidget(hint)
        if removable:
            button = make_remove_button()
            button.setToolTip("Remove frame")
            button.clicked.connect(lambda: self.removed.emit(self))
            header.addWidget(button)
        layout.addLayout(header)

        if frame_id in COMPLEX_FIELDS:
            self.instances_layout = QVBoxLayout()
            self.instances_layout.setSpacing(6)
            layout.addLayout(self.instances_layout)
            self.add_instance_button = QPushButton(f"+ Add {frame_id} instance")
            self.add_instance_button.setObjectName("SecondaryBtn")
            self.add_instance_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.add_instance_button.clicked.connect(lambda: self.add_instance())
            layout.addWidget(self.add_instance_button, alignment=Qt.AlignmentFlag.AlignLeft)
            self.add_instance()
        else:
            self.value_input = QLineEdit()
            self.value_input.setObjectName("formInput")
            if frame_id.startswith("W"):
                self.value_input.setPlaceholderText("https://...")
            elif frame_id == "TDRC":
                self.value_input.setPlaceholderText("YYYY or YYYY-MM-DD")
            elif frame_id == "TRCK":
                self.value_input.setPlaceholderText("3/12")
            layout.addWidget(self.value_input)

    def add_instance(self) -> "FrameInstanceRow":
        row = FrameInstanceRow(self.frame_id)
        row.removed.connect(self.remove_instance)
        self.instances.append(row)
        self.instances_layout.addWidget(row)
        return row

    def remove_instance(self, row: "FrameInstanceRow") -> None:
        if row not in self.instances:
            return
        self.instances.remove(row)
        self.instances_layout.removeWidget(row)
        row.hide()
        row.deleteLater()
        if not self.instances:
            self.add_instance()

    def clear(self) -> None:
        if self.frame_id not in COMPLEX_FIELDS:
            self.loaded_values = []
            self.loaded_display = ""
            self.value_input.clear()
            return
        for row in self.instances:
            self.instances_layout.removeWidget(row)
            row.hide()
            row.deleteLater()
        self.instances.clear()
        self.add_instance()

    def load_draft(self, draft: MP3SimpleFrameDraft | MP3ComplexFrameDraft) -> None:
        if draft.frame_id != self.frame_id:
            raise ValueError("Cannot load a different frame into this field.")
        self.clear()
        if isinstance(draft, MP3SimpleFrameDraft):
            self.loaded_values = list(draft.values)
            self.loaded_display = " / ".join(draft.values)
            self.value_input.setText(self.loaded_display)
            self.value_input.setToolTip(
                "Multiple values are saved as one value separated by '/' in ID3v2.3."
                if len(draft.values) > 1 else ""
            )
        else:
            for index, instance in enumerate(draft.instances):
                row = self.instances[0] if index == 0 else self.add_instance()
                row.load_draft(instance)

    def get_draft(self) -> MP3SimpleFrameDraft | MP3ComplexFrameDraft:
        if self.frame_id not in COMPLEX_FIELDS:
            text = self.value_input.text()
            values = list(self.loaded_values) if text == self.loaded_display else [text]
            return MP3SimpleFrameDraft(self.frame_id, values)
        return MP3ComplexFrameDraft(self.frame_id, [row.get_draft() for row in self.instances if not row.is_empty()])


class FrameInstanceRow(QFrame):
    removed = pyqtSignal(object)

    def __init__(self, frame_id: str, parent=None):
        super().__init__(parent)
        self.inputs = {}
        self.loaded_text = None
        self.loaded_text_display = ""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for name in COMPLEX_FIELDS[frame_id]:
            if name == "lang":
                widget = QComboBox()
                widget.setEditable(True)
                widget.addItems(["eng", "tha", "und"])
                widget.setFixedWidth(90)
                widget.lineEdit().setMaxLength(3)
                widget.setToolTip("Language: three-letter code")
            elif name == "text" and frame_id == "USLT":
                widget = QPlainTextEdit()
                widget.setObjectName("payloadTextArea")
                widget.setFixedHeight(70)
                widget.setPlaceholderText("Lyrics...")
            else:
                widget = QLineEdit()
                widget.setObjectName("formInput")
                widget.setPlaceholderText({"desc": "desc (optional)", "text": "Text...", "url": "https://..."}[name])
            self.inputs[name] = widget
            layout.addWidget(widget, 2 if name in {"text", "url"} else 1)
        button = make_remove_button()
        button.setToolTip("Remove instance")
        button.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(button)

    def get_value(self, name: str) -> str:
        widget = self.inputs[name]
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText()
        return widget.text()

    def load_draft(self, draft: MP3FrameInstanceDraft) -> None:
        for name, widget in self.inputs.items():
            value = getattr(draft, name) or ""
            if name == "text":
                self.loaded_text = deepcopy(value)
                self.loaded_text_display = " / ".join(value) if isinstance(value, list) else value
                widget.setToolTip(
                    "Multiple values are saved as one value separated by '/' in ID3v2.3."
                    if isinstance(value, list) and len(value) > 1 else ""
                )
                value = self.loaded_text_display
            if isinstance(widget, QComboBox):
                widget.setCurrentText(value)
            elif isinstance(widget, QPlainTextEdit):
                widget.setPlainText(value)
            else:
                widget.setText(value)

    def is_empty(self) -> bool:
        # A default language alone does not make a blank instance meaningful.
        return not any(self.get_value(name).strip() for name in self.inputs if name != "lang")

    def get_draft(self) -> MP3FrameInstanceDraft:
        values = {name: self.get_value(name) for name in self.inputs}
        if "text" in values and values["text"] == self.loaded_text_display and self.loaded_text is not None:
            values["text"] = deepcopy(self.loaded_text)
        return MP3FrameInstanceDraft(**values)


class MP3TextFramesForm(QFrame):
    """Standard, Other, and Add Frame cards, with local UI actions only."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.standard_fields: dict[str, TextFrameField] = {}
        self.other_fields: list[TextFrameField] = []
        self.setObjectName("fileListContainer")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(16)
        self.standard_card = self.build_standard_card()
        self.other_card = self.build_other_card()
        self.add_card = self.build_add_card()
        layout.addWidget(self.standard_card)
        layout.addWidget(self.other_card)
        layout.addWidget(self.add_card)
        layout.addStretch()

    def _card(self, title: str, icon: str, hint: str, badge=None) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        header = QFrame()
        header_layout = QHBoxLayout(header)
        image = QLabel()
        image.setPixmap(create_icon_pixmap(svg_path(icon), size=16))
        label = QLabel(title)
        label.setObjectName("cardTitle")
        hint_label = QLabel(hint)
        hint_label.setObjectName("hintLabel")
        header_layout.addWidget(image)
        header_layout.addWidget(label)
        if badge is not None:
            header_layout.addWidget(badge)
        header_layout.addStretch()
        header_layout.addWidget(hint_label)
        layout.addWidget(header)
        return card, layout

    def build_standard_card(self) -> QFrame:
        card, layout = self._card("Standard Frames", "tags.svg", "Always shown")
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for index, frame_id in enumerate(key for key in STANDARD_FRAMES if is_simple_frame(key)):
            field = TextFrameField(frame_id)
            self.standard_fields[frame_id] = field
            row, column = divmod(index, 2)
            grid.addWidget(field, row, column)
        layout.addLayout(grid)
        for frame_id in STANDARD_FRAMES:
            if frame_id in COMPLEX_FIELDS:
                field = TextFrameField(frame_id)
                self.standard_fields[frame_id] = field
                layout.addWidget(field)
        return card

    def build_other_card(self) -> QFrame:
        self.other_count_badge = make_badge("0")
        card, layout = self._card("Other Frames", "file-dots.svg", "Additional text and URL frames", self.other_count_badge)
        self.other_layout = QVBoxLayout()
        self.other_layout.setSpacing(12)
        layout.addLayout(self.other_layout)
        return card

    def build_add_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QHBoxLayout(card)
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

    def addable_frame_ids(self) -> list[str]:
        used = {field.frame_id for field in self.other_fields}
        return sorted(key for key in FRAME_INFO if key not in STANDARD_FRAMES and key not in used
                      and (is_simple_frame(key) or key in COMPLEX_FIELDS))

    def refresh_add_options(self) -> None:
        self.add_frame_combo.clear()
        for frame_id in self.addable_frame_ids():
            self.add_frame_combo.addItem(f"{frame_id} — {FRAME_INFO[frame_id][0]}", frame_id)
        self.add_frame_button.setEnabled(self.add_frame_combo.count() > 0)

    def add_selected_frame(self) -> None:
        frame_id = self.add_frame_combo.currentData()
        if not frame_id:
            return
        self.add_frame(frame_id)

    def add_frame(self, frame_id: str) -> TextFrameField:
        if frame_id not in self.addable_frame_ids():
            raise ValueError(f"Cannot add frame '{frame_id}'.")
        field = TextFrameField(frame_id, removable=True)
        field.removed.connect(self.remove_frame)
        self.other_fields.append(field)
        self.other_layout.addWidget(field)
        self.other_count_badge.setText(str(len(self.other_fields)))
        self.refresh_add_options()
        return field

    def remove_frame(self, field: TextFrameField) -> None:
        if field not in self.other_fields:
            return
        self.other_fields.remove(field)
        self.other_layout.removeWidget(field)
        field.hide()
        field.deleteLater()
        self.other_count_badge.setText(str(len(self.other_fields)))
        self.refresh_add_options()

    def clear_all(self) -> None:
        for field in self.standard_fields.values():
            field.clear()
        for field in list(self.other_fields):
            self.remove_frame(field)

    def load_draft(self, draft: MP3TextFramesDraft) -> None:
        frames = deepcopy(draft.frames)
        seen = set()
        for frame in frames:
            if frame.frame_id in seen:
                raise ValueError(f"Duplicate frame: {frame.frame_id}")
            seen.add(frame.frame_id)
            if ((isinstance(frame, MP3SimpleFrameDraft) and not is_simple_frame(frame.frame_id))
                    or (isinstance(frame, MP3ComplexFrameDraft) and frame.frame_id not in COMPLEX_FIELDS)
                    or not isinstance(frame, (MP3SimpleFrameDraft, MP3ComplexFrameDraft))):
                raise ValueError(f"Unsupported frame draft: {frame.frame_id}")
        self.clear_all()
        for frame in frames:
            field = self.standard_fields.get(frame.frame_id)
            if field is None:
                field = self.add_frame(frame.frame_id)
            field.load_draft(frame)

    def get_inputs(self) -> MP3TextFramesDraft:
        frames = []
        for field in [*self.standard_fields.values(), *self.other_fields]:
            draft = field.get_draft()
            empty = (not any(value.strip() for value in draft.values) if isinstance(draft, MP3SimpleFrameDraft)
                     else not draft.instances)
            if empty and field.frame_id in STANDARD_FRAMES:
                continue
            frames.append(draft)
        result = MP3TextFramesDraft(frames)
        validate_text_frames(result)
        return result
