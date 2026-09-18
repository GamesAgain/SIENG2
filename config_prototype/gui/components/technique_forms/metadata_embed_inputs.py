from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config_prototype.core.configurable import (
    FileSource,
    StepOutput,
    StepOutputInfo,
)
from config_prototype.gui.components import LinkedStepToggle, StepOutputPicker
from config_prototype.gui.components.technique_forms.metadata.mp3_form import (
    MP3MetadataDraft,
    MP3MetadataForm,
)
from config_prototype.gui.components.technique_forms.metadata.png_form import (
    PNGMetadataDraft,
    PNGMetadataForm,
)
from config_prototype.gui.paths import ICON_DIR
from src.gui.components.file_info_bar import FileInfoBar
from src.gui.components.files_drop import FileDropWidget
from src.gui.components.gui_utils import (
    add_shadow_effect,
    create_icon_pixmap,
    format_file_size,
    truncate_text_middle,
)
from src.gui.tabs.metadata_shared import get_file_display_info


MetadataPayloadDraft: TypeAlias = PNGMetadataDraft | MP3MetadataDraft


@dataclass
class MetadataInputsDraft:
    """Saved inputs for one Metadata pipeline step."""

    cover: FileSource | None = None
    payload: MetadataPayloadDraft | None = None


class MetadataEmbedInputs(QFrame):
    """Host Metadata inputs without depending on a page or shell variant."""

    COVER_DROP_STATE_INDEX = 0
    COVER_SELECTED_STATE_INDEX = 1
    EMPTY_STATE_INDEX = 0
    PNG_STATE_INDEX = 1
    MP3_STATE_INDEX = 2

    def __init__(
        self,
        *,
        output_catalog: list[StepOutputInfo] | None = None,
        cover_dependency_error: str | None = None,
        apic_output_catalog: list[StepOutputInfo] | None = None,
        apic_dependency_errors: dict[StepOutput, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.output_catalog = [
            output
            for output in (output_catalog or [])
            if output.media_type in {"png", "mp3"}
        ]
        self.cover_dependency_error = cover_dependency_error
        self.apic_output_catalog = [
            output
            for output in (apic_output_catalog or [])
            if output.media_type == "png"
        ]
        self.apic_dependency_errors = dict(apic_dependency_errors or {})
        self._draft = MetadataInputsDraft()
        self._cover_media_type: str | None = None
        self._syncing_cover = False
        self.build_ui()

    def build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        self.content_stack = QStackedWidget()
        self.empty_state_label = QLabel(
            "Select a PNG or MP3 target file to configure metadata."
        )
        self.empty_state_label.setObjectName("pipelineEmpty")
        self.empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_label.setWordWrap(True)

        self.png_form = PNGMetadataForm()
        self.mp3_form = MP3MetadataForm(
            apic_output_catalog=self.apic_output_catalog,
            apic_dependency_errors=self.apic_dependency_errors,
        )

        self.content_stack.addWidget(self.empty_state_label)
        self.content_stack.addWidget(self.png_form)
        self.content_stack.addWidget(self.mp3_form)

        self.cover_file_stack = QStackedWidget()
        self.cover_card = self.build_cover_card()
        self.selected_cover_widget = self.build_selected_cover_widget()
        self.cover_file_stack.addWidget(self.cover_card)
        self.cover_file_stack.addWidget(self.selected_cover_widget)
        main_layout.addWidget(self.cover_file_stack)
        main_layout.addWidget(self.content_stack, 1)
        self.content_stack.hide()
        self._sync_cover_file_stack_height()

    def build_cover_card(self) -> QFrame:
        """Build the manual/linked PNG or MP3 target selector."""
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)

        card_layout = QVBoxLayout(card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)

        title_icon = QLabel()
        title_icon.setPixmap(
            create_icon_pixmap(ICON_DIR / "photo-video.svg", size=16)
        )
        title_label = QLabel("Target File (PNG, MP3)")
        title_label.setObjectName("cardTitle")

        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.cover_mode_toggle = LinkedStepToggle()
        self.cover_mode_toggle.mode_changed.connect(
            self.on_cover_mode_changed
        )

        self.cover_drop_zone = FileDropWidget(
            "Drop PNG or MP3 file here or click to browse",
            "Supports PNG and MP3 formats only",
            icon_path=str(ICON_DIR / "upload.svg"),
            allowed_extensions=[".png", ".mp3"],
        )
        self.cover_drop_zone.file_selected.connect(
            self.on_cover_file_selected
        )

        self.cover_output_picker = StepOutputPicker(self.output_catalog)
        self.cover_output_picker.selection_changed.connect(
            self.on_cover_output_selected
        )

        self.cover_source_stack = QStackedWidget()
        self.cover_source_stack.addWidget(self.cover_drop_zone)
        self.cover_source_stack.addWidget(self.cover_output_picker)
        self.cover_output_picker.minimum_height_changed.connect(
            self.cover_source_stack.setMinimumHeight
        )
        self.cover_output_picker.minimum_height_changed.connect(
            self._sync_cover_file_stack_height
        )
        self.cover_source_stack.setMinimumHeight(
            self.cover_output_picker.minimumHeight()
        )

        card_layout.addWidget(title_container)
        card_layout.addWidget(self.cover_mode_toggle)
        card_layout.addWidget(self.cover_source_stack, 1)
        return card

    def _sync_cover_file_stack_height(self, _height: int = 0) -> None:
        """Keep the active cover page tall enough for its dynamic picker."""
        if not hasattr(self, "cover_file_stack"):
            return
        current_widget = self.cover_file_stack.currentWidget()
        if current_widget is None:
            return
        if current_widget.layout() is not None:
            current_widget.layout().activate()
        self.cover_file_stack.setMinimumHeight(
            current_widget.sizeHint().height()
        )
        if self.layout() is not None:
            self.layout().invalidate()
            self.setMinimumHeight(self.layout().minimumSize().height())
        self.updateGeometry()

    def build_selected_cover_widget(self) -> QWidget:
        """Build the compact selected-file view used before media editors."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.file_info_bar = FileInfoBar()
        self.file_info_bar.change_file_requested.connect(
            self.on_change_cover_requested
        )
        layout.addWidget(self.file_info_bar)
        return container

    def on_cover_mode_changed(self, mode: str) -> None:
        """Switch source kind without inventing a path for linked output."""
        linked = mode == "linked"
        self.cover_source_stack.setCurrentIndex(1 if linked else 0)
        if linked:
            self._draft.cover = self.cover_output_picker.selected_output()
        else:
            self._draft.cover = self.cover_drop_zone.file_path or None
        self.update_cover_media_state()

    def on_cover_output_selected(self, reference: StepOutput) -> None:
        if not self.cover_mode_toggle.is_linked():
            return
        self._draft.cover = reference
        self.cover_dependency_error = None
        self.cover_output_picker.set_unavailable_reason(None)
        self.update_cover_media_state()

    def on_cover_file_selected(self, file_path: str) -> None:
        """Keep the manual cover selection in the form draft."""
        if self._syncing_cover or self.cover_mode_toggle.is_linked():
            return

        self._draft.cover = file_path or None
        self.update_cover_media_state()

    def clear_cover(self) -> None:
        """Clear the manual cover through the drop widget lifecycle."""
        self.cover_drop_zone.clear_file()

    def on_change_cover_requested(self) -> None:
        """Return to the manual drop state and clear only the cover."""
        self.clear_cover()

    @property
    def cover_media_type(self) -> str | None:
        return self._cover_media_type

    @staticmethod
    def detect_cover_media(source: FileSource | None) -> str | None:
        """Return the supported media type for an available manual cover."""
        if not isinstance(source, str) or not source:
            return None

        cover = Path(source)
        if not cover.is_file():
            return None

        suffix = cover.suffix.lower()
        if suffix == ".png":
            return "png"
        if suffix == ".mp3":
            return "mp3"
        return None

    def update_cover_media_state(self) -> None:
        """Synchronize the cover selector, file bar, and media host page."""
        self._cover_media_type = self.cover_media_for_source(self._draft.cover)
        current_form = {
            "png": self.png_form,
            "mp3": self.mp3_form,
        }.get(self._cover_media_type, self.empty_state_label)
        self.content_stack.setCurrentWidget(current_form)
        self.content_stack.setVisible(self._cover_media_type is not None)

        if isinstance(self._draft.cover, StepOutput):
            self.cover_file_stack.setCurrentIndex(self.COVER_DROP_STATE_INDEX)
            self._sync_cover_file_stack_height()
            return

        if self._cover_media_type is None:
            self.cover_file_stack.setCurrentIndex(
                self.COVER_DROP_STATE_INDEX
            )
            self._sync_cover_file_stack_height()
            return

        self.file_info_bar.update_info(self.cover_display_info())
        self.cover_file_stack.setCurrentIndex(
            self.COVER_SELECTED_STATE_INDEX
        )
        self._sync_cover_file_stack_height()

    def cover_media_for_source(self, source: FileSource | None) -> str | None:
        if isinstance(source, str) or source is None:
            return self.detect_cover_media(source)

        output_info = next(
            (
                output
                for output in self.output_catalog
                if output.reference == source
            ),
            None,
        )
        if output_info is not None:
            return output_info.media_type
        if isinstance(self._draft.payload, PNGMetadataDraft):
            return "png"
        if isinstance(self._draft.payload, MP3MetadataDraft):
            return "mp3"
        return None

    def cover_display_info(self) -> dict:
        """Return FileInfoBar data, including a safe unreadable-file state."""
        cover_source = self._draft.cover
        if not isinstance(cover_source, str):
            raise ValueError("A cover file is required for display info.")

        try:
            return get_file_display_info(cover_source)
        except Exception:
            cover = Path(cover_source)
            media_label = (self._cover_media_type or cover.suffix[1:]).upper()
            icon_name = (
                "photo.svg"
                if self._cover_media_type == "png"
                else "file-music.svg"
            )
            return {
                "path": cover_source,
                "icon": str(ICON_DIR / icon_name),
                "name": truncate_text_middle(cover.name, 110),
                "detail": (
                    f"{format_file_size(cover.stat().st_size)} - "
                    "Unable to read media details"
                ),
                "badges": [
                    (media_label, "blue"),
                    ("Unreadable details", "red"),
                ],
            }

    def load_draft(self, draft: MetadataInputsDraft) -> None:
        """Replace the form state with a detached copy of the draft."""
        loaded_draft = deepcopy(draft)
        if isinstance(loaded_draft.payload, MP3MetadataDraft):
            structure_error = self.mp3_form.draft_structure_error(
                loaded_draft.payload
            )
            if structure_error is not None:
                raise ValueError(structure_error)
        cover_source = loaded_draft.cover

        self._syncing_cover = True
        try:
            self.cover_drop_zone.clear_all()
            self.cover_output_picker.clear_selection()
            if (
                isinstance(cover_source, str)
                and self.detect_cover_media(cover_source) is not None
            ):
                self.cover_mode_toggle.set_mode("manual")
                self.cover_source_stack.setCurrentIndex(0)
                self.cover_drop_zone.add_files([cover_source])
            elif isinstance(cover_source, StepOutput):
                self.cover_mode_toggle.set_mode("linked")
                self.cover_source_stack.setCurrentIndex(1)
                self.cover_output_picker.set_selected_output(cover_source)
                self.cover_output_picker.set_unavailable_reason(
                    self.cover_dependency_error
                )
            else:
                self.cover_mode_toggle.set_mode("manual")
                self.cover_source_stack.setCurrentIndex(0)
        finally:
            self._syncing_cover = False

        self._draft = loaded_draft
        self.png_form.clear_all()
        self.mp3_form.clear_all()
        if isinstance(loaded_draft.payload, PNGMetadataDraft):
            self.png_form.load_draft(loaded_draft.payload)
        elif isinstance(loaded_draft.payload, MP3MetadataDraft):
            self.mp3_form.load_draft(loaded_draft.payload)
        self.update_cover_media_state()

    def export_draft(self) -> MetadataInputsDraft:
        """Return a detached copy of the current form state."""
        exported_draft = deepcopy(self._draft)
        if self._cover_media_type == "png":
            exported_draft.payload = self.png_form.export_draft()
        elif self._cover_media_type == "mp3":
            exported_draft.payload = self.mp3_form.export_draft()
        return exported_draft

    def validate_draft(self) -> bool:
        """Validate the selected cover and its active format form."""
        cover_source = self._draft.cover
        if cover_source is None:
            return self.show_validation_warning(
                "Please select a target PNG or MP3 file."
            )

        if isinstance(cover_source, str):
            cover = Path(cover_source)
            if not cover.is_file():
                return self.show_validation_warning(
                    "The selected target file is unavailable."
                )
            if cover.suffix.lower() not in {".png", ".mp3"}:
                return self.show_validation_warning(
                    "Metadata supports PNG and MP3 target files only."
                )

        if self._cover_media_type == "png":
            png_draft = self.png_form.export_draft()
            if (
                not png_draft.entries
                and self._draft.payload is not None
                and not isinstance(self._draft.payload, PNGMetadataDraft)
            ):
                return self.show_validation_warning(
                    "The metadata payload does not match the PNG target file."
                )
            return self.png_form.validate_draft()

        if self._cover_media_type != "mp3":
            return self.show_validation_warning(
                "The linked output media type is unavailable."
            )

        mp3_draft = self.mp3_form.export_draft()
        if (
            not mp3_draft.frames
            and not mp3_draft.apic_images
            and self._draft.payload is not None
            and not isinstance(self._draft.payload, MP3MetadataDraft)
        ):
            return self.show_validation_warning(
                "The metadata payload does not match the MP3 target file."
            )
        return self.mp3_form.validate_draft()

    def show_validation_warning(
        self,
        message: str,
        *,
        title: str = "Validation Error",
    ) -> bool:
        QMessageBox.warning(self, title, message)
        return False


__all__ = [
    "MetadataEmbedInputs",
    "MetadataInputsDraft",
    "MetadataPayloadDraft",
]
