from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config_prototype.gui.components.technique_forms.metadata.mp3_frame_drafts import (
    MP3_COMPLEX_FRAME_CONTRACTS,
    MP3ComplexFrameContract,
    MP3ComplexFrameDraft,
    MP3ComplexFrameInstanceDraft,
    MP3SimpleFrameDraft,
    is_mp3_simple_frame_id,
)
from config_prototype.gui.paths import ICON_DIR
from src.core.stego.metadata_handlers.mp3_handler import FRAME_INFO
from src.gui.components.gui_utils import create_icon_pixmap


def _make_tag_badge(text: str) -> QLabel:
    badge = QLabel(text)
    badge.setObjectName("fileInfoBadge")
    badge.setProperty("badgeColor", "neutral")
    return badge


def _make_delete_button(size: int = 22) -> QPushButton:
    button = QPushButton()
    button.setObjectName("btnRemoveFile")
    button.setFixedSize(size, size)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setIcon(
        QIcon(
            create_icon_pixmap(
                ICON_DIR / "x.svg",
                size=12,
                color_hex="#F43F5E",
            )
        )
    )
    return button


class TextFrameField(QFrame):
    """One scalar text or URL frame with an optional remove action."""

    removed = pyqtSignal(object)

    def __init__(
        self,
        frame_id: str,
        *,
        removable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ensure_simple_frame_id(frame_id)
        self.frame_id = frame_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)

        display_name, _description = FRAME_INFO.get(
            frame_id,
            (frame_id, ""),
        )
        self.name_label = QLabel(display_name)
        self.name_label.setObjectName("formLabel")
        self.frame_badge = _make_tag_badge(frame_id)

        header_layout.addWidget(self.name_label)
        header_layout.addWidget(self.frame_badge)
        header_layout.addStretch()

        self.delete_button: QPushButton | None = None
        if removable:
            self.delete_button = _make_delete_button()
            self.delete_button.clicked.connect(
                lambda: self.removed.emit(self)
            )
            header_layout.addWidget(self.delete_button)

        layout.addLayout(header_layout)

        self.value_input = QLineEdit()
        self.value_input.setObjectName("formInput")
        if frame_id.startswith("W"):
            self.value_input.setPlaceholderText("https://...")
        layout.addWidget(self.value_input)

    @staticmethod
    def _ensure_simple_frame_id(frame_id: str) -> None:
        if not is_mp3_simple_frame_id(frame_id):
            raise ValueError(
                f"'{frame_id}' is not a simple MP3 text or URL frame."
            )

    def get_value(self) -> str:
        return self.value_input.text().strip()

    def set_value(self, value: object | None) -> None:
        self.value_input.setText("" if value is None else str(value))

    def is_empty(self) -> bool:
        return not self.get_value()

    def clear(self) -> None:
        self.value_input.clear()

    def load_draft(self, draft: MP3SimpleFrameDraft) -> None:
        if draft.frame_id != self.frame_id:
            raise ValueError(
                "Cannot load frame "
                f"'{draft.frame_id}' into '{self.frame_id}' field."
            )
        self.set_value(draft.value)

    def export_draft(self) -> MP3SimpleFrameDraft:
        return MP3SimpleFrameDraft(
            frame_id=self.frame_id,
            value=self.get_value(),
        )


class ComplexInstanceRow(QFrame):
    """One editable structured value for a complex MP3 frame."""

    removed = pyqtSignal(object)

    def __init__(
        self,
        frame_id: str,
        *,
        show_delete: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.frame_id = frame_id
        self.contract = self._get_contract(frame_id)
        self.inputs: dict[
            str,
            QComboBox | QLineEdit | QPlainTextEdit,
        ] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        for field_name in self.contract.fields:
            widget = self._create_input(field_name)
            self.inputs[field_name] = widget
            stretch = 2 if field_name in {"text", "url"} else 1
            layout.addWidget(widget, stretch)

        self.delete_button: QPushButton | None = None
        if show_delete:
            self.delete_button = _make_delete_button(26)
            self.delete_button.clicked.connect(
                lambda: self.removed.emit(self)
            )
            layout.addWidget(self.delete_button)

    @staticmethod
    def _get_contract(frame_id: str) -> MP3ComplexFrameContract:
        try:
            return MP3_COMPLEX_FRAME_CONTRACTS[frame_id]
        except KeyError as error:
            raise ValueError(
                f"'{frame_id}' is not a supported complex MP3 frame."
            ) from error

    def _create_input(
        self,
        field_name: str,
    ) -> QComboBox | QLineEdit | QPlainTextEdit:
        if field_name == "lang":
            language_input = QComboBox()
            language_input.setEditable(True)
            language_input.addItems(["eng", "tha"])
            language_input.setCurrentIndex(-1)
            language_input.lineEdit().setPlaceholderText("eng")
            language_input.lineEdit().setMaxLength(3)
            language_input.setFixedWidth(90)
            return language_input

        if field_name == "text" and self.contract.multiline:
            text_input = QPlainTextEdit()
            text_input.setObjectName("payloadTextArea")
            text_input.setFixedHeight(70)
            text_input.setPlaceholderText("Lyrics...")
            return text_input

        value_input = QLineEdit()
        value_input.setObjectName("formInput")
        placeholder = {
            "desc": "desc (optional)",
            "text": "Text...",
            "url": "https://...",
        }[field_name]
        value_input.setPlaceholderText(placeholder)
        return value_input

    def get_value(self, field_name: str) -> str:
        widget = self.inputs[field_name]
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText().strip()
        if isinstance(widget, QComboBox):
            return widget.currentText().strip()
        return widget.text().strip()

    def set_value(self, field_name: str, value: object | None) -> None:
        widget = self.inputs[field_name]
        normalized = "" if value is None else str(value)
        if isinstance(widget, QPlainTextEdit):
            widget.setPlainText(normalized)
        elif isinstance(widget, QComboBox):
            widget.setCurrentText(normalized.strip())
        else:
            widget.setText(normalized)

    def is_empty(self) -> bool:
        main_field = "text" if "text" in self.inputs else "url"
        return not self.get_value(main_field)

    def clear(self) -> None:
        for field_name in self.inputs:
            self.set_value(field_name, None)

    def load_draft(self, draft: MP3ComplexFrameInstanceDraft) -> None:
        self.clear()
        for field_name in self.contract.fields:
            self.set_value(field_name, getattr(draft, field_name))

    def export_draft(self) -> MP3ComplexFrameInstanceDraft:
        values = {
            field_name: self.get_value(field_name)
            for field_name in self.contract.fields
        }
        return MP3ComplexFrameInstanceDraft(**values)


class ComplexFrameField(QFrame):
    """One complex frame type containing one or more editable instances."""

    removed = pyqtSignal(object)

    def __init__(
        self,
        frame_id: str,
        *,
        removable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.frame_id = frame_id
        self.contract = ComplexInstanceRow._get_contract(frame_id)
        self.rows: list[ComplexInstanceRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)

        display_name, _description = FRAME_INFO.get(
            frame_id,
            (frame_id, ""),
        )
        self.name_label = QLabel(display_name)
        self.name_label.setObjectName("formLabel")
        self.frame_badge = _make_tag_badge(frame_id)
        self.multiple_hint = QLabel("Can have multiple instances")
        self.multiple_hint.setObjectName("hintLabel")

        header_layout.addWidget(self.name_label)
        header_layout.addWidget(self.frame_badge)
        header_layout.addStretch()
        header_layout.addWidget(self.multiple_hint)

        self.delete_button: QPushButton | None = None
        if removable:
            self.delete_button = _make_delete_button()
            self.delete_button.clicked.connect(
                lambda: self.removed.emit(self)
            )
            header_layout.addWidget(self.delete_button)

        layout.addLayout(header_layout)

        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(6)
        layout.addLayout(self.rows_layout)

        self.add_instance_button = QPushButton(
            f"+ Add {frame_id} instance"
        )
        self.add_instance_button.setObjectName("LinkBtn")
        self.add_instance_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.add_instance_button.clicked.connect(
            lambda: self.add_instance()
        )
        layout.addWidget(
            self.add_instance_button,
            alignment=Qt.AlignmentFlag.AlignLeft,
        )

        self.add_instance()

    def add_instance(
        self,
        draft: MP3ComplexFrameInstanceDraft | None = None,
    ) -> ComplexInstanceRow:
        row = ComplexInstanceRow(self.frame_id)
        if draft is not None:
            row.load_draft(draft)
        row.removed.connect(self.remove_instance)
        self.rows_layout.addWidget(row)
        self.rows.append(row)
        return row

    def _discard_row(self, row: ComplexInstanceRow) -> None:
        self.rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()

    def remove_instance(self, row: ComplexInstanceRow) -> None:
        if row not in self.rows:
            return
        self._discard_row(row)
        if not self.rows:
            self.add_instance()

    def clear(self) -> None:
        for row in list(self.rows):
            self._discard_row(row)
        self.add_instance()

    def is_empty(self) -> bool:
        return all(row.is_empty() for row in self.rows)

    def load_draft(self, draft: MP3ComplexFrameDraft) -> None:
        if draft.frame_id != self.frame_id:
            raise ValueError(
                "Cannot load frame "
                f"'{draft.frame_id}' into '{self.frame_id}' field."
            )

        for row in list(self.rows):
            self._discard_row(row)
        for instance in draft.instances:
            self.add_instance(instance)
        if not self.rows:
            self.add_instance()

    def export_draft(self) -> MP3ComplexFrameDraft:
        return MP3ComplexFrameDraft(
            frame_id=self.frame_id,
            instances=[
                row.export_draft()
                for row in self.rows
                if not row.is_empty()
            ],
        )


__all__ = [
    "ComplexFrameField",
    "ComplexInstanceRow",
    "TextFrameField",
]
