from dataclasses import dataclass
from pathlib import Path

from mutagen import MutagenError
from PyQt6.QtCore import QSignalBlocker, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QStackedWidget, QVBoxLayout

from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap
from src.gui.components.widgets.files_drop import FileDropWidget
from src.gui.components.widgets.selection_toggle import SelectionToggle
from src.gui.components.widgets.step_output_picker import StepOutputPicker
from src.core.configurable.step_output import FileSource, StepOutput, StepOutputInfo
from src.gui.features.embed.forms.metadata.file_info import get_mp3_file_info, get_png_file_info
from src.gui.features.embed.forms.metadata.mp3_draft import MP3MetadataDraft
from src.gui.features.embed.forms.metadata.mp3_form import MP3MetadataForm
from src.gui.features.embed.forms.metadata.png_form import PNGMetadataDraft, PNGMetadataForm
from src.path import svg_path


ICON_SIZE = 16


@dataclass
class MetadataInputsDraft:
    """Saved target and format-specific edits for one Metadata pipeline step."""
    cover: FileSource | None = None
    payload: PNGMetadataDraft | MP3MetadataDraft | None = None


class MetadataInputForm(QFrame):
    """Select a PNG/MP3 target and save its configuration as a step draft."""

    target_file_changed = pyqtSignal(str)

    def __init__(self, is_config: bool = False, parent=None):
        super().__init__(parent)
        self.is_config = is_config
        self.target_source: FileSource | None = None
        self.target_media: str | None = None
        self.output_catalog: list[StepOutputInfo] = []
        self.setup_ui()

    @property
    def target_file_path(self) -> str | None:
        # Standalone execution still receives only a real manual file path.
        if isinstance(self.target_source, str):
            return self.target_source
        return None

    @target_file_path.setter
    def target_file_path(self, file_path: str | None):
        self.target_source = file_path
        self.target_media = None
        if file_path:
            self.target_media = Path(file_path).suffix.lower()[1:]

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 11, 0, 0)
        self.target_stack = QStackedWidget()
        self.target_card = self.build_target_file_card()
        self.png_form = PNGMetadataForm()
        self.mp3_form = MP3MetadataForm(is_config=self.is_config)
        self.target_stack.addWidget(self.target_card)
        self.target_stack.addWidget(self.png_form)
        self.target_stack.addWidget(self.mp3_form)
        main_layout.addWidget(self.target_stack, 1)

        self.cover_drop_zone.file_selected.connect(self.on_target_file_selected)
        self.png_form.change_file_requested.connect(self.change_target_file)
        self.mp3_form.change_file_requested.connect(self.change_target_file)

    def on_target_file_selected(self, file_path: str) -> None:
        if self.cover_mode_toggle.mode() == "linked":
            return
        if not file_path:
            self.reset_target()
            return

        if file_path == self.target_source:
            return
        # Metadata edits belong to one target, including switches within PNG/MP3.
        self.png_form.clear_all()
        self.mp3_form.clear_all()

        extension = Path(file_path).suffix.lower()
        form = {".png": self.png_form, ".mp3": self.mp3_form}.get(extension)
        try:
            if form is None:
                raise ValueError("Please select a PNG or MP3 file.")
            form.load_file(file_path)
        except Exception as error:
            self.change_target_file()
            QMessageBox.warning(self, "Cannot read file", str(error))
            return

        self.target_file_path = file_path
        self.target_stack.setCurrentWidget(form)
        self.target_file_changed.emit(file_path)

    def change_target_file(self) -> None:
        self.reset_target()

    def reset_target(self) -> None:
        """Discard target-specific edits before choosing a different PNG/MP3."""
        self.target_file_path = None
        self.cover_mode_toggle.set_mode("Manual")
        self.output_picker.set_selection(None)
        self.cover_source_stack.setCurrentWidget(self.cover_drop_zone)
        with QSignalBlocker(self.cover_drop_zone):
            self.cover_drop_zone.clear_all()
        self.png_form.clear_all()
        self.mp3_form.clear_all()
        self.target_stack.setCurrentWidget(self.target_card)
        self.target_file_changed.emit("")

    def get_inputs(self) -> MetadataInputsDraft:
        if not self.target_source:
            raise ValueError("Please select a target PNG or MP3 file.")
        form = {"png": self.png_form, "mp3": self.mp3_form}.get(self.target_media)
        if form is None:
            raise ValueError("Metadata supports PNG and MP3 targets only.")
        return MetadataInputsDraft(cover=self.target_source, payload=form.get_inputs())

    def load_draft(self, draft: MetadataInputsDraft) -> None:
        """Restore saved edits after reading target info; never save to the file."""
        if draft.payload is not None and not isinstance(draft.payload, (PNGMetadataDraft, MP3MetadataDraft)):
            raise ValueError("Unsupported Metadata payload draft.")
        self.reset_target()
        if isinstance(draft.cover, StepOutput):
            self.cover_mode_toggle.set_mode("linked")
            self.on_cover_mode_changed("linked")
            self.output_picker.set_selection(draft.cover)
            self.on_target_output_selected(draft.cover)
            if self.target_source is None:
                return
            if self.target_media == "png":
                form = self.png_form
                payload_type = PNGMetadataDraft
            else:
                form = self.mp3_form
                payload_type = MP3MetadataDraft
            if draft.payload is not None:
                if not isinstance(draft.payload, payload_type):
                    raise ValueError("Metadata payload does not match the target format.")
                form.load_draft(draft.payload)
            return
        with QSignalBlocker(self.cover_drop_zone):
            self.cover_drop_zone.clear_all()
            if isinstance(draft.cover, str) and Path(draft.cover).is_file():
                self.cover_drop_zone.add_files([draft.cover])
        self.png_form.clear_all()
        self.mp3_form.clear_all()
        self.target_file_path = draft.cover if isinstance(draft.cover, str) else None
        if not self.target_file_path:
            self.target_stack.setCurrentWidget(self.target_card)
            return
        extension = Path(self.target_file_path).suffix.lower()
        form = {".png": self.png_form, ".mp3": self.mp3_form}.get(extension)
        payload_type = {".png": PNGMetadataDraft, ".mp3": MP3MetadataDraft}.get(extension)
        if form is None or (draft.payload is not None and not isinstance(draft.payload, payload_type)):
            raise ValueError("Metadata payload does not match the target format.")
        try:
            form.load_file(self.target_file_path)
        except (MutagenError, OSError, SyntaxError, ValueError):
            # Preserve the saved edits even if the source disappeared or changed.
            form.file_info_bar.update_info(
                file_path=self.target_file_path,
                display_name=Path(self.target_file_path).name,
                detail="Target unavailable or invalid; choose another file before saving.",
                badges=[(extension[1:].upper(), "blue")],
            )
        if draft.payload is not None:
            form.load_draft(draft.payload)
        self.target_stack.setCurrentWidget(form)

    def validate_draft(self) -> bool:
        try:
            if self.cover_mode_toggle.mode() == "linked":
                if not self.is_config or not isinstance(self.target_source, StepOutput):
                    raise ValueError("Please select a previous PNG or MP3 output.")
                if self.output_picker.selection() != self.target_source:
                    raise ValueError("The target output is unavailable. Select another output.")
            else:
                if not self.target_file_path or not Path(self.target_file_path).is_file():
                    raise ValueError("Please select an available target PNG or MP3 file.")
                if self.target_media == "png":
                    get_png_file_info(self.target_file_path)
                elif self.target_media == "mp3":
                    get_mp3_file_info(self.target_file_path)
            if self.target_media == "png":
                self.png_form.validate_inputs()
            elif self.target_media == "mp3":
                self.mp3_form.get_inputs()  # Validates text frames and confirmed APIC edits.
            else:
                raise ValueError("Metadata supports PNG and MP3 targets only.")
        except (MutagenError, OSError, SyntaxError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "Invalid Step Inputs", str(error))
            return False
        return True

    def set_available_outputs(self, outputs: list[StepOutputInfo]):
        self.mp3_form.attached_picture_form.set_available_outputs(outputs)
        self.output_catalog = []
        for output in outputs:
            if output.media_type in {"png", "mp3"}:
                self.output_catalog.append(output)
        self.output_picker.set_outputs(self.output_catalog)
        if isinstance(self.target_source, StepOutput):
            self.output_picker.set_selection(self.target_source)
            self.on_target_output_selected(self.target_source)

    def on_cover_mode_changed(self, mode: str):
        if mode == "linked":
            self.cover_source_stack.setCurrentWidget(self.output_picker)
        else:
            self.cover_source_stack.setCurrentWidget(self.cover_drop_zone)

    def on_target_output_selected(self, reference: StepOutput | None):
        if self.cover_mode_toggle.mode() != "linked":
            return
        output = None
        for item in self.output_catalog:
            if item.reference == reference:
                output = item
                break
        if output is None:
            self.reset_target()
            return

        if reference != self.target_source or output.media_type != self.target_media:
            self.png_form.clear_all()
            self.mp3_form.clear_all()
        self.target_source = reference
        self.target_media = output.media_type
        if self.target_media == "png":
            form = self.png_form
        else:
            form = self.mp3_form

        technique_names = {"lsbpp": "LSB++", "locomotive": "Locomotive", "metadata": "Metadata"}
        technique = technique_names.get(output.technique, output.technique)
        name = output.display_name or "Output"
        display_name = f"From STEP {output.step_number} {technique}, {name}"
        # Only declared media is known; do not read metadata from the preview path.
        form.file_info_bar.update_info(
            file_path="", display_name=display_name,
            detail="Expected output; file details are available when the pipeline runs.",
            badges=[(self.target_media.upper(), "blue")],
            icon_path=str(svg_path("photo-video.svg")),
        )
        form.file_info_bar.file_name.setToolTip(display_name)
        self.target_stack.setCurrentWidget(form)
        self.target_file_changed.emit("")

    def build_target_file_card(self) -> QFrame:
        target_card = QFrame()
        target_card.setObjectName("card")
        add_shadow_effect(target_card)

        target_layout = QVBoxLayout(target_card)
        target_layout.setContentsMargins(10, 10, 10, 10)

        title_container = QFrame()
        title_layout = QHBoxLayout(title_container)
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(svg_path("photo-video.svg"), size=ICON_SIZE))
        title_label = QLabel("Target File (PNG, MP3)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.cover_mode_toggle = SelectionToggle([
            {
                "text": "Manual File",
                "value": "Manual",
                "variant": "source",
                "color_checked": "#38BDF8",
            },
            {
                "text": "Previous Output",
                "value": "linked",
                "variant": "source",
                "color_checked": "#38BDF8",
            },
        ])
        self.cover_mode_toggle.mode_changed.connect(self.on_cover_mode_changed)

        self.cover_drop_zone = FileDropWidget(
            text="Drop PNG or MP3 file here or click to browse",
            sub_text="Supports PNG and MP3 formats only",
            icon_path=str(svg_path("photo-video.svg")),
            allowed_extensions=[".png", ".mp3"],
            show_preview=False,
        )

        target_layout.addWidget(title_container)
        target_layout.addWidget(self.cover_mode_toggle)
        self.cover_mode_toggle.setVisible(self.is_config)
        self.cover_source_stack = QStackedWidget()
        self.cover_source_stack.addWidget(self.cover_drop_zone)
        self.output_picker = StepOutputPicker()
        self.cover_source_stack.addWidget(self.output_picker)
        self.output_picker.selection_changed.connect(self.on_target_output_selected)
        target_layout.addWidget(self.cover_source_stack, 1)
        return target_card
