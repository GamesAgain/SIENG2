from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypeAlias

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QImageReader, QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QTabWidget,
    QVBoxLayout, QWidget,
)

from config_prototype.gui.paths import ICON_DIR
from src.core.stego.metadata_handlers.mp3_handler import (
    APIC_TYPES,
    FRAME_INFO,
    STANDARD_FRAMES,
)
from src.gui.components.files_drop import FileDropWidget
from src.gui.components.gui_utils import (
    add_shadow_effect,
    create_icon_pixmap,
    create_icon_state,
    format_file_size,
    truncate_text_middle,
)


MP3ComplexFieldName: TypeAlias = Literal["lang", "desc", "text", "url"]


@dataclass(frozen=True)
class MP3ComplexFrameContract:
    """Fields and UI behavior required by one editable complex frame type."""

    fields: tuple[MP3ComplexFieldName, ...]
    required_fields: tuple[MP3ComplexFieldName, ...] = ()
    identity_fields: tuple[MP3ComplexFieldName, ...] = ()
    multiline: bool = False
    allows_multiple: bool = True


MP3_COMPLEX_FRAME_CONTRACTS: dict[str, MP3ComplexFrameContract] = {
    "COMM": MP3ComplexFrameContract(
        ("lang", "desc", "text"),
        required_fields=("lang", "text"),
        identity_fields=("lang", "desc"),
    ),
    "USLT": MP3ComplexFrameContract(
        ("lang", "desc", "text"),
        required_fields=("lang", "text"),
        identity_fields=("lang", "desc"),
        multiline=True,
    ),
    "USER": MP3ComplexFrameContract(
        ("lang", "text"),
        required_fields=("lang", "text"),
        identity_fields=("lang",),
    ),
    "TXXX": MP3ComplexFrameContract(
        ("desc", "text"),
        required_fields=("text",),
        identity_fields=("desc",),
    ),
    "WXXX": MP3ComplexFrameContract(
        ("desc", "url"),
        required_fields=("url",),
        identity_fields=("desc",),
    ),
}


def is_mp3_simple_frame_id(frame_id: str) -> bool:
    """Return whether an ID can use a scalar text/URL draft value."""

    return (
        len(frame_id) == 4
        and frame_id.startswith(("T", "W"))
        and frame_id not in MP3_COMPLEX_FRAME_CONTRACTS
    )


@dataclass
class MP3SimpleFrameDraft:
    """One editable ID3 text or URL frame with a scalar string value."""

    frame_id: str
    value: str = ""


@dataclass
class MP3ComplexFrameInstanceDraft:
    """One structured value belonging to a complex ID3 frame."""

    lang: str | None = None
    desc: str | None = None
    text: str | None = None
    url: str | None = None


@dataclass
class MP3ComplexFrameDraft:
    """One complex frame type and its ordered user-configured instances."""

    frame_id: str
    instances: list[MP3ComplexFrameInstanceDraft] = field(
        default_factory=list
    )


MP3FrameDraft: TypeAlias = MP3SimpleFrameDraft | MP3ComplexFrameDraft


APIC_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})


@dataclass
class ApicImageDraft:
    """One local image that will become an MP3 attached-picture frame."""

    image_path: str
    picture_type: int = 3
    description: str = ""


def apic_draft_structure_error(drafts: object) -> str | None:
    """Return a structural error without requiring referenced files to exist."""
    if not isinstance(drafts, list):
        return "APIC image drafts must be a list."

    for draft in drafts:
        if not isinstance(draft, ApicImageDraft):
            return "APIC image drafts contain an unsupported item."
        if not isinstance(draft.image_path, str):
            return "APIC image paths must be text."
        if not isinstance(draft.picture_type, int) or isinstance(
            draft.picture_type,
            bool,
        ):
            return "APIC picture types must be integer IDs."
        if draft.picture_type not in APIC_TYPES:
            return f"Unsupported APIC picture type: {draft.picture_type}."
        if not isinstance(draft.description, str):
            return "APIC descriptions must be text."

    return None


@dataclass
class MP3MetadataDraft:
    """User-configured ID3 frames and APIC images for an MP3 step."""

    frames: list[MP3FrameDraft] = field(default_factory=list)
    apic_images: list[ApicImageDraft] = field(default_factory=list)


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


MP3FrameFieldWidget = TextFrameField | ComplexFrameField


def _make_count_badge(text: str) -> QLabel:
    badge = QLabel(text)
    badge.setObjectName("fileInfoBadge")
    badge.setProperty("badgeColor", "neutral")
    return badge


class MP3TextFramesForm(QFrame):
    """Own standard fields and the user-added MP3 frame collection."""

    changed = pyqtSignal()

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("mp3TextFramesForm")
        self.standard_fields: dict[str, MP3FrameFieldWidget] = {}
        self.other_fields: list[MP3FrameFieldWidget] = []

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 12, 0, 0)
        self.main_layout.setSpacing(16)

        self.standard_frames_card = self._build_standard_frames_section()
        self.other_frames_card = self._build_other_frames_section()
        self.add_frame_card = self._build_add_frame_section()

        self.main_layout.addWidget(self.standard_frames_card)
        self.main_layout.addWidget(self.other_frames_card)
        self.main_layout.addWidget(self.add_frame_card)
        self.main_layout.addStretch()

    def _build_standard_frames_section(self) -> QFrame:
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
        title_label = QLabel("Standard Frames")
        title_label.setObjectName("cardTitle")
        hint_label = QLabel("Always shown")
        hint_label.setObjectName("hintLabel")

        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(hint_label)
        layout.addWidget(title_container)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(12)

        simple_frame_ids = [
            frame_id
            for frame_id in STANDARD_FRAMES
            if is_mp3_simple_frame_id(frame_id)
        ]
        for index, frame_id in enumerate(simple_frame_ids):
            field = TextFrameField(frame_id)
            self.standard_fields[frame_id] = field
            row, column = divmod(index, 2)
            grid.addWidget(field, row, column)
        layout.addLayout(grid)

        for frame_id in STANDARD_FRAMES:
            if frame_id not in MP3_COMPLEX_FRAME_CONTRACTS:
                continue
            field = ComplexFrameField(frame_id)
            self.standard_fields[frame_id] = field
            layout.addWidget(field)

        return card

    def _build_other_frames_section(self) -> QFrame:
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
        title_label = QLabel("Other Frames")
        title_label.setObjectName("cardTitle")
        self.other_count_badge = _make_count_badge("0")
        hint_label = QLabel("Additional text and URL frames")
        hint_label.setObjectName("hintLabel")

        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addWidget(self.other_count_badge)
        title_layout.addStretch()
        title_layout.addWidget(hint_label)
        layout.addWidget(title_container)

        self.other_frames_layout = QVBoxLayout()
        self.other_frames_layout.setSpacing(8)
        layout.addLayout(self.other_frames_layout)
        return card

    def _build_add_frame_section(self) -> QFrame:
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
        self.add_frame_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.add_frame_button.clicked.connect(
            lambda: self.add_selected_frame()
        )
        self._refresh_add_frame_options()

        layout.addWidget(label)
        layout.addWidget(self.add_frame_combo, 1)
        layout.addWidget(self.add_frame_button)
        return card

    @staticmethod
    def _is_supported_other_frame(frame_id: str) -> bool:
        return (
            frame_id in FRAME_INFO
            and frame_id != "APIC"
            and frame_id not in STANDARD_FRAMES
            and (
                is_mp3_simple_frame_id(frame_id)
                or frame_id in MP3_COMPLEX_FRAME_CONTRACTS
            )
        )

    def addable_frame_ids(self) -> list[str]:
        used_frame_ids = {field.frame_id for field in self.other_fields}
        return sorted(
            frame_id
            for frame_id in FRAME_INFO
            if self._is_supported_other_frame(frame_id)
            and frame_id not in used_frame_ids
        )

    def _refresh_add_frame_options(self) -> None:
        self.add_frame_combo.clear()
        for frame_id in self.addable_frame_ids():
            display_name, _description = FRAME_INFO[frame_id]
            self.add_frame_combo.addItem(
                f"{frame_id} - {display_name}",
                frame_id,
            )
        self.add_frame_button.setEnabled(self.add_frame_combo.count() > 0)

    def add_selected_frame(self) -> MP3FrameFieldWidget | None:
        frame_id = self.add_frame_combo.currentData()
        if not frame_id:
            return None
        return self.add_other_frame(frame_id)

    def add_other_frame(self, frame_id: str) -> MP3FrameFieldWidget:
        if not self._is_supported_other_frame(frame_id):
            raise ValueError(
                f"'{frame_id}' is not an addable MP3 text frame."
            )
        if any(field.frame_id == frame_id for field in self.other_fields):
            raise ValueError(
                f"Frame '{frame_id}' is already present in Other Frames."
            )

        field = self._append_other_frame(frame_id)
        self._refresh_collection_state()
        self.changed.emit()
        return field

    def _append_other_frame(self, frame_id: str) -> MP3FrameFieldWidget:
        if frame_id in MP3_COMPLEX_FRAME_CONTRACTS:
            field: MP3FrameFieldWidget = ComplexFrameField(
                frame_id,
                removable=True,
            )
        else:
            field = TextFrameField(frame_id, removable=True)

        field.removed.connect(self.remove_other_frame)
        self.other_fields.append(field)
        self.other_frames_layout.addWidget(field)
        return field

    def remove_other_frame(self, field: MP3FrameFieldWidget) -> None:
        if field not in self.other_fields:
            return
        self.other_fields.remove(field)
        self.other_frames_layout.removeWidget(field)
        field.setParent(None)
        field.deleteLater()
        self._refresh_collection_state()
        self.changed.emit()

    def _refresh_collection_state(self) -> None:
        self.other_count_badge.setText(str(len(self.other_fields)))
        self._refresh_add_frame_options()

    def clear_all(self) -> None:
        self._clear_controls()
        self._refresh_collection_state()
        self.changed.emit()

    def _clear_controls(self) -> None:
        for field in self.standard_fields.values():
            field.clear()
        for field in list(self.other_fields):
            self.other_fields.remove(field)
            self.other_frames_layout.removeWidget(field)
            field.setParent(None)
            field.deleteLater()

    def load_draft(self, frames: list[MP3FrameDraft]) -> None:
        loaded_frames = deepcopy(frames)
        structure_error = self.draft_structure_error(loaded_frames)
        if structure_error is not None:
            raise ValueError(structure_error)

        self._clear_controls()
        for frame in loaded_frames:
            field = self.standard_fields.get(frame.frame_id)
            if field is None:
                field = self._append_other_frame(frame.frame_id)
            field.load_draft(frame)
        self._refresh_collection_state()

    def export_draft(self) -> list[MP3FrameDraft]:
        frames: list[MP3FrameDraft] = []
        for field in self.standard_fields.values():
            if not field.is_empty():
                frames.append(field.export_draft())
        for field in self.other_fields:
            if not field.is_empty():
                frames.append(field.export_draft())
        return frames

    @classmethod
    def draft_structure_error(
        cls,
        frames: list[MP3FrameDraft],
    ) -> str | None:
        seen_frame_ids: set[str] = set()
        for frame in frames:
            if not isinstance(
                frame,
                (MP3SimpleFrameDraft, MP3ComplexFrameDraft),
            ):
                return "MP3 text-frame drafts contain an unsupported item."

            frame_id = frame.frame_id
            if not isinstance(frame_id, str):
                return "MP3 frame IDs must be text."
            if frame_id in seen_frame_ids:
                return f"MP3 frame '{frame_id}' is configured more than once."
            seen_frame_ids.add(frame_id)

            is_standard = frame_id in STANDARD_FRAMES
            is_other = cls._is_supported_other_frame(frame_id)
            if not is_standard and not is_other:
                return f"MP3 frame '{frame_id}' is not editable in this form."

            if isinstance(frame, MP3SimpleFrameDraft):
                if not is_mp3_simple_frame_id(frame_id):
                    return (
                        f"MP3 frame '{frame_id}' requires a complex draft."
                    )
                if not isinstance(frame.value, str):
                    return f"MP3 frame '{frame_id}' must contain text."
                continue

            contract = MP3_COMPLEX_FRAME_CONTRACTS.get(frame_id)
            if contract is None:
                return f"MP3 frame '{frame_id}' requires a simple draft."
            if not isinstance(frame.instances, list):
                return f"MP3 frame '{frame_id}' instances must be a list."
            for instance in frame.instances:
                if not isinstance(instance, MP3ComplexFrameInstanceDraft):
                    return (
                        f"MP3 frame '{frame_id}' contains an invalid instance."
                    )
                for field_name in ("lang", "desc", "text", "url"):
                    value = getattr(instance, field_name)
                    if value is not None and not isinstance(value, str):
                        return (
                            f"MP3 frame '{frame_id}' field '{field_name}' "
                            "must contain text."
                        )
                    if (
                        field_name not in contract.fields
                        and value not in (None, "")
                    ):
                        return (
                            f"MP3 frame '{frame_id}' does not use field "
                            f"'{field_name}'."
                        )
        return None

    def validate_draft(self) -> bool:
        """Validate visible frame values before the MP3 draft is saved."""
        for field in self.standard_fields.values():
            if isinstance(field, ComplexFrameField):
                error = self._validate_complex_field(field)
                if error is not None:
                    return self.show_validation_warning(error)

        for field in self.other_fields:
            if isinstance(field, ComplexFrameField):
                error = self._validate_complex_field(field)
                if error is not None:
                    return self.show_validation_warning(error)

        for field in self.other_fields:
            if field.is_empty():
                self._focus_primary_input(field)
                return self.show_validation_warning(
                    f"Please enter a value for frame '{field.frame_id}' "
                    "or remove it."
                )
        return True

    def _validate_complex_field(
        self,
        field: ComplexFrameField,
    ) -> str | None:
        identity_values: set[tuple[str, ...]] = set()
        for row in field.rows:
            if row.is_empty():
                if any(
                    row.get_value(field_name)
                    for field_name in field.contract.fields
                ):
                    self._focus_primary_input(row)
                    primary = (
                        "text" if "text" in row.inputs else "URL"
                    )
                    return (
                        f"Please enter {primary} for frame "
                        f"'{field.frame_id}'."
                    )
                if len(field.rows) > 1:
                    self._focus_primary_input(row)
                    return (
                        f"Remove the empty '{field.frame_id}' instance "
                        "or enter a value."
                    )
                continue

            for field_name in field.contract.required_fields:
                if row.get_value(field_name):
                    continue
                row.inputs[field_name].setFocus()
                return (
                    f"Frame '{field.frame_id}' requires "
                    f"'{field_name}'."
                )

            if "lang" in field.contract.fields:
                language = row.get_value("lang")
                if not (
                    len(language) == 3
                    and language.isascii()
                    and language.isalpha()
                ):
                    row.inputs["lang"].setFocus()
                    return (
                        f"Frame '{field.frame_id}' language must be a "
                        "3-letter code such as 'eng' or 'tha'."
                    )

            identity = tuple(
                row.get_value(field_name)
                for field_name in field.contract.identity_fields
            )
            if identity in identity_values:
                self._focus_primary_input(row)
                return (
                    f"Frame '{field.frame_id}' has duplicate instance "
                    "identity values."
                )
            identity_values.add(identity)
        return None

    @staticmethod
    def _focus_primary_input(
        field: MP3FrameFieldWidget | object,
    ) -> None:
        if isinstance(field, TextFrameField):
            field.value_input.setFocus()
            return
        if isinstance(field, ComplexFrameField):
            field = field.rows[0]
        if hasattr(field, "inputs"):
            inputs = field.inputs
            primary_name = "text" if "text" in inputs else "url"
            inputs[primary_name].setFocus()

    def show_validation_warning(
        self,
        message: str,
        *,
        title: str = "Validation Error",
    ) -> bool:
        QMessageBox.warning(self, title, message)
        return False


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


class MP3MetadataForm(QFrame):
    """Combine MP3 text frames and APIC images without page coupling."""

    changed = pyqtSignal()

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("techTabs")
        self.tabs.setIconSize(QSize(16, 16))

        self.text_frames_form = MP3TextFramesForm()
        self.apic_images_form = MP3ApicImagesForm()
        self.text_frames_form.changed.connect(self.changed.emit)
        self.apic_images_form.changed.connect(self._on_apic_changed)

        self.text_scroll = self._make_scroll_area(self.text_frames_form)
        self.apic_scroll = self._make_scroll_area(self.apic_images_form)
        self.tabs.addTab(
            self.text_scroll,
            create_icon_state(str(ICON_DIR / "text-size.svg")),
            "Text Frames",
        )
        self.tabs.addTab(
            self.apic_scroll,
            create_icon_state(str(ICON_DIR / "photo.svg")),
            "Attached Pictures [0]",
        )
        layout.addWidget(self.tabs)

    @staticmethod
    def _make_scroll_area(widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("mp3MetadataScroll")
        scroll.viewport().setObjectName("mp3MetadataViewport")
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll

    def _on_apic_changed(self) -> None:
        self.refresh_tab_labels()
        self.changed.emit()

    def refresh_tab_labels(self) -> None:
        self.tabs.setTabText(
            1,
            f"Attached Pictures [{self.apic_images_form.image_count()}]",
        )

    @staticmethod
    def draft_structure_error(draft: object) -> str | None:
        if not isinstance(draft, MP3MetadataDraft):
            return "MP3 metadata payload has an unsupported type."

        frame_error = MP3TextFramesForm.draft_structure_error(draft.frames)
        if frame_error is not None:
            return frame_error
        return apic_draft_structure_error(draft.apic_images)

    def load_draft(self, draft: MP3MetadataDraft) -> None:
        loaded_draft = deepcopy(draft)
        structure_error = self.draft_structure_error(loaded_draft)
        if structure_error is not None:
            raise ValueError(structure_error)

        self.text_frames_form.load_draft(loaded_draft.frames)
        self.apic_images_form.load_draft(loaded_draft.apic_images)
        self.refresh_tab_labels()
        self.tabs.setCurrentIndex(
            1 if loaded_draft.apic_images and not loaded_draft.frames else 0
        )

    def export_draft(self) -> MP3MetadataDraft:
        return MP3MetadataDraft(
            frames=self.text_frames_form.export_draft(),
            apic_images=self.apic_images_form.export_draft(),
        )

    def validate_draft(self) -> bool:
        draft = self.export_draft()
        if not self.text_frames_form.validate_draft():
            return False
        if draft.apic_images and not self.apic_images_form.validate_draft():
            return False
        if not draft.frames and not draft.apic_images:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please add at least one MP3 text frame or APIC image.",
            )
            return False
        return True

    def clear_all(self) -> None:
        self.text_frames_form.clear_all()
        self.apic_images_form.clear_all()
        self.refresh_tab_labels()


__all__ = [
    "APIC_IMAGE_EXTENSIONS",
    "ApicImageCard",
    "ApicImageDraft",
    "ComplexFrameField",
    "ComplexInstanceRow",
    "MP3_COMPLEX_FRAME_CONTRACTS",
    "MP3ApicImagesForm",
    "MP3ComplexFieldName",
    "MP3ComplexFrameContract",
    "MP3ComplexFrameDraft",
    "MP3ComplexFrameInstanceDraft",
    "MP3FrameDraft",
    "MP3MetadataDraft",
    "MP3MetadataForm",
    "MP3SimpleFrameDraft",
    "MP3TextFramesForm",
    "TextFrameField",
    "apic_draft_structure_error",
    "is_mp3_simple_frame_id",
]
