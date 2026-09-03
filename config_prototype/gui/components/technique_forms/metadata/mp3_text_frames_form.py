from copy import deepcopy

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFrame,QGridLayout,
    QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QVBoxLayout,QWidget,
)

from config_prototype.gui.components.technique_forms.metadata.mp3_frame_drafts import (
    MP3_COMPLEX_FRAME_CONTRACTS,
    MP3ComplexFrameDraft,
    MP3ComplexFrameInstanceDraft,
    MP3FrameDraft,
    MP3SimpleFrameDraft,
    is_mp3_simple_frame_id,
)
from config_prototype.gui.components.technique_forms.metadata.mp3_metadata_fields import (
    ComplexFrameField,
    TextFrameField,
)
from config_prototype.gui.paths import ICON_DIR
from src.core.stego.metadata_handlers.mp3_handler import (
    FRAME_INFO,
    STANDARD_FRAMES,
)
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap


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


__all__ = ["MP3TextFramesForm"]
