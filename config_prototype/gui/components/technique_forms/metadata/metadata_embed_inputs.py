from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

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

from config_prototype.gui.paths import ICON_DIR
from config_prototype.gui.components.technique_forms.metadata.mp3_apic_drafts import (
    ApicImageDraft,
    apic_draft_structure_error,
)
from config_prototype.gui.components.technique_forms.metadata.mp3_frame_drafts import (
    MP3FrameDraft,
)
from config_prototype.gui.components.technique_forms.metadata.mp3_metadata_form import (
    MP3MetadataForm,
)
from config_prototype.gui.components.technique_forms.metadata.png_metadata_form import (
    PNGMetadataForm,
)
from src.gui.components.file_info_bar import FileInfoBar
from src.gui.components.files_drop import FileDropWidget
from src.gui.components.gui_utils import (
    add_shadow_effect,
    create_icon_pixmap,
    format_file_size,
    truncate_text_middle,
)
from src.gui.tabs.metadata_shared import get_file_display_info

@dataclass
class PNGMetadataDraft:
    """Text Chunk metadata configured for a PNG pipeline step."""

    entries: dict[str, str] = field(default_factory=dict)


@dataclass
class MP3MetadataDraft:
    """User-configured ID3 frames and APIC images for an MP3 step.

    Existing raw frames belong to the cover file and are intentionally not
    copied into this payload draft.
    """

    frames: list[MP3FrameDraft] = field(default_factory=list)
    apic_images: list[ApicImageDraft] = field(default_factory=list)


MetadataPayloadDraft = PNGMetadataDraft | MP3MetadataDraft


@dataclass
class MetadataInputsDraft:
    """Saved manual inputs for one Metadata pipeline step."""

    cover_path: str | None = None
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
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

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
        self.png_state_widget = self.png_form
        self.mp3_metadata_form = MP3MetadataForm()
        self.mp3_form = self.mp3_metadata_form.text_frames_form
        self.mp3_apic_form = self.mp3_metadata_form.apic_images_form
        self.mp3_state_widget = self.mp3_metadata_form

        self.content_stack.addWidget(self.empty_state_label)
        self.content_stack.addWidget(self.png_state_widget)
        self.content_stack.addWidget(self.mp3_state_widget)

        self.cover_file_stack = QStackedWidget()
        self.cover_card = self.build_cover_card()
        self.selected_cover_widget = self.build_selected_cover_widget()
        self.cover_file_stack.addWidget(self.cover_card)
        self.cover_file_stack.addWidget(self.selected_cover_widget)
        main_layout.addWidget(self.cover_file_stack, 1)

    def build_cover_card(self) -> QFrame:
        """Build the manual PNG/MP3 target selector."""
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

        self.cover_drop_zone = FileDropWidget(
            "Drop PNG or MP3 file here or click to browse",
            "Supports PNG and MP3 formats only",
            icon_path=str(ICON_DIR / "upload.svg"),
            allowed_extensions=[".png", ".mp3"],
        )
        self.cover_drop_zone.file_selected.connect(
            self.on_cover_file_selected
        )

        card_layout.addWidget(title_container)
        card_layout.addWidget(self.cover_drop_zone, 1)
        return card

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
        layout.addWidget(self.content_stack, 1)
        return container

    def on_cover_file_selected(self, file_path: str) -> None:
        """Keep the manual cover selection in the form draft."""
        if self._syncing_cover:
            return

        self._draft.cover_path = file_path or None
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
    def detect_cover_media(file_path: str | None) -> str | None:
        """Return the supported media type for an available manual cover."""
        if not file_path:
            return None

        cover = Path(file_path)
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
        self._cover_media_type = self.detect_cover_media(
            self._draft.cover_path
        )
        state_index = {
            "png": self.PNG_STATE_INDEX,
            "mp3": self.MP3_STATE_INDEX,
        }.get(self._cover_media_type, self.EMPTY_STATE_INDEX)
        self.content_stack.setCurrentIndex(state_index)

        if self._cover_media_type is None:
            self.cover_file_stack.setCurrentIndex(
                self.COVER_DROP_STATE_INDEX
            )
            return

        self.file_info_bar.update_info(self.cover_display_info())
        self.cover_file_stack.setCurrentIndex(
            self.COVER_SELECTED_STATE_INDEX
        )

    def cover_display_info(self) -> dict:
        """Return FileInfoBar data, including a safe unreadable-file state."""
        cover_path = self._draft.cover_path
        if cover_path is None:
            raise ValueError("A cover file is required for display info.")

        try:
            return get_file_display_info(cover_path)
        except Exception:
            cover = Path(cover_path)
            media_label = (self._cover_media_type or cover.suffix[1:]).upper()
            icon_name = (
                "photo.svg"
                if self._cover_media_type == "png"
                else "file-music.svg"
            )
            return {
                "path": cover_path,
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
        """Replace the form state with a detached copy of ``draft``."""
        loaded_draft = deepcopy(draft)
        if isinstance(loaded_draft.payload, MP3MetadataDraft):
            structure_error = self.mp3_form.draft_structure_error(
                loaded_draft.payload.frames
            )
            if structure_error is not None:
                raise ValueError(structure_error)
            structure_error = apic_draft_structure_error(
                loaded_draft.payload.apic_images
            )
            if structure_error is not None:
                raise ValueError(structure_error)
        cover_path = loaded_draft.cover_path

        self._syncing_cover = True
        try:
            self.cover_drop_zone.clear_all()
            if self.detect_cover_media(cover_path) is not None:
                self.cover_drop_zone.add_files([cover_path])
        finally:
            self._syncing_cover = False

        self._draft = loaded_draft
        self.png_form.clear_all()
        mp3_frames: list[MP3FrameDraft] = []
        apic_images: list[ApicImageDraft] = []
        if isinstance(loaded_draft.payload, PNGMetadataDraft):
            self.png_form.load_draft(loaded_draft.payload)
        elif isinstance(loaded_draft.payload, MP3MetadataDraft):
            mp3_frames = loaded_draft.payload.frames
            apic_images = loaded_draft.payload.apic_images
        self.mp3_metadata_form.load_draft(mp3_frames, apic_images)
        self.update_cover_media_state()

    def export_draft(self) -> MetadataInputsDraft:
        """Return a detached copy of the current form state."""
        exported_draft = deepcopy(self._draft)
        if self._cover_media_type == "png":
            exported_draft.payload = self.png_form.export_draft()
        elif self._cover_media_type == "mp3":
            exported_draft.payload = MP3MetadataDraft(
                frames=self.mp3_metadata_form.export_text_frames(),
                apic_images=self.mp3_metadata_form.export_apic_images(),
            )
        return exported_draft

    def validate_draft(self) -> bool:
        """Validate Metadata draft."""
        cover_path = self._draft.cover_path
        if not cover_path:
            return self.show_validation_warning(
                "Please select a target PNG or MP3 file."
            )

        cover = Path(cover_path)
        if not cover.is_file():
            return self.show_validation_warning(
                "The selected target file is unavailable."
            )

        suffix = cover.suffix.lower()
        if suffix not in {".png", ".mp3"}:
            return self.show_validation_warning(
                "Metadata supports PNG and MP3 target files only."
            )

        if suffix == ".png":
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

        frames = self.mp3_form.export_draft()
        apic_images = self.mp3_apic_form.export_draft()
        payload = self._draft.payload
        if (
            not frames
            and not apic_images
            and payload is not None
            and not isinstance(payload, MP3MetadataDraft)
        ):
            return self.show_validation_warning(
                "The metadata payload does not match the MP3 target file."
            )
        if not self.mp3_form.validate_draft():
            return False

        if apic_images and not self.mp3_apic_form.validate_draft():
            return False
        if not frames and not apic_images:
            return self.show_validation_warning(
                "Please add at least one MP3 text frame or APIC image."
            )
        return True

    def show_validation_warning(
        self,
        message: str,
        *,
        title: str = "Validation Error",
    ) -> bool:
        QMessageBox.warning(self, title, message)
        return False
