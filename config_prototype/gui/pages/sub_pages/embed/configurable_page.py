from dataclasses import dataclass
from functools import partial
from pathlib import Path
from uuid import uuid4

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QWidget, QDialog, QFrame, QVBoxLayout, QHBoxLayout,
    QScrollArea, QLabel, QComboBox, QMessageBox, QPushButton, QButtonGroup,
    QProgressBar,
)

from config_prototype.core.configurable import StepOutput, StepOutputInfo
from config_prototype.gui.components.step_card import (
    CARD_HEIGHT,
    TECHNIQUE_DISPLAY,
    StepCard,
    make_arrow,
)
from config_prototype.gui.components.step_output_picker import (
    output_display_name,
)
from config_prototype.gui.components.technique_forms import (
    ApicImageDraft,
    LSBEmbedInputs,
    LSBInputsDraft,
    LocomotiveEmbedInputs,
    LocomotiveInputsDraft,
    MetadataEmbedInputs,
    MetadataInputsDraft,
    MP3ComplexFrameDraft,
    MP3MetadataDraft,
    MP3SimpleFrameDraft,
    PNGMetadataDraft,
)
from config_prototype.gui.components.step_config_shell import (
    StepConfigShellDialog,
    StepConfigShellPanel,
)
from config_prototype.gui.paths import ICON_DIR
from src.core.stego.metadata_handlers.mp3_handler import APIC_TYPES, FRAME_INFO
from src.gui.components.flow_layout import FlowLayout
from src.gui.components.gui_utils import (
    add_shadow_effect,
    create_icon_pixmap,
    format_file_size,
)
from src.gui.services.key_registry import KeyRegistry

ICON_SIZE = 16
CHIP_ICON_SIZE = 12
TECHNIQUE_CHIPS = ["lsbpp", "locomotive", "metadata"]
CLEAR_CHIP_COLOR = "#f43f5e"
CANVAS_MARGIN = 16
FLOW_SPACING = 8
VISIBLE_CANVAS_ROWS = 2
MAX_VISIBLE_FLOW_HEIGHT = (CARD_HEIGHT * VISIBLE_CANVAS_ROWS + FLOW_SPACING * (VISIBLE_CANVAS_ROWS - 1))
STEP_KEY_HEX_LENGTH = 5


@dataclass
class PipelineStepDraft:
    key: str
    technique: str
    description: str
    guidenote: str = ""
    technique_inputs: (
        LSBInputsDraft
        | LocomotiveInputsDraft
        | MetadataInputsDraft
        | None
    ) = None


class EmbedConfigurablePage(QFrame):

    def __init__(
        self,
        key_registry: KeyRegistry | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.key_registry = key_registry
        self.pipeline_steps: list[PipelineStepDraft] = []
        self.used_step_keys: set[str] = set()
        self.step_cards: list[StepCard] = []
        self.technique_buttons: dict[str, QPushButton] = {}
        self.config_variant = "popup"
        self.active_step_index: int | None = None
        self.active_step_key: str | None = None
        self.active_step_dialog: StepConfigShellDialog | None = None
        self.active_step_panel: StepConfigShellPanel | None = None
        self.setup_ui()
        self.render_step_cards()

    def setup_ui(self):
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("pipelineScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("pipelineScrollContent")
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(4, 11, 4, 4)
        main_layout.setSpacing(10)
        self.page_content = content
        self.page_content_layout = main_layout

        # -- Pipeline Builder Card --
        self.pipeline_builder_card = self.build_pipeline_builder_card()
        main_layout.addWidget(self.pipeline_builder_card)

        # -- Inline Panel --
        self.inline_slot = QVBoxLayout()
        main_layout.addLayout(self.inline_slot)

        main_layout.addStretch()

        scroll.setWidget(content)
        self.page_scroll = scroll
        page_layout.addWidget(scroll)

        # -- execution bar --
        execution_wrap = QVBoxLayout()
        execution_wrap.setContentsMargins(4, 0, 4, 4)
        execution_wrap.addLayout(self.build_execution_bar())
        page_layout.addLayout(execution_wrap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "canvas_scroll"):
            QTimer.singleShot(0, self.refresh_canvas_height)


    # --- การ์ด Pipeline Builder ---
    def build_pipeline_builder_card(self):
        card_frame = QFrame()
        card_frame.setObjectName("card")
        add_shadow_effect(card_frame)

        main_layout = QVBoxLayout(card_frame)
        main_layout.setSpacing(10)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)

        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(ICON_DIR / "git-branch.svg", size=ICON_SIZE))
        title_label = QLabel("Pipeline Builder")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        main_layout.addWidget(title_container)
        main_layout.addLayout(self.build_template_row())
        main_layout.addLayout(self.build_technique_chip_row())
        main_layout.addWidget(self.build_canvas())
        main_layout.addLayout(self.build_step_ui_row())

        return card_frame


    def build_template_row(self):
        template_row = QHBoxLayout()
        template_row.setSpacing(8)

        self.template_combo = QComboBox()
        self.template_combo.addItem("Select a Pipeline Example (Template)", "")
        # for i, (label, fname) in enumerate(PIPELINE_TEMPLATES, 1):
        #     self.template_combo.addItem(f"{i}. {label}", fname)
        # self.template_combo.currentIndexChanged.connect(self.on_template_selected)
        template_row.addWidget(self.template_combo, 1)

        self.import_config_btn = QPushButton(" Import Config")
        self.import_config_btn.setObjectName("SecondaryBtn")
        self.import_config_btn.setProperty("textColor", "white")
        self.import_config_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_config_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "file-import.svg", color_hex="#FFFFFF", size=ICON_SIZE)))
        # self.import_config_btn.clicked.connect(self.on_import_config) TODO
        template_row.addWidget(self.import_config_btn)

        self.export_config_btn = QPushButton(" Export Config")
        self.export_config_btn.setObjectName("SecondaryBtn")
        self.export_config_btn.setProperty("textColor", "white")
        self.export_config_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_config_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "file-export.svg", color_hex="#FFFFFF", size=ICON_SIZE)))
        # self.export_config_btn.clicked.connect(self.on_export_config) TODO
        template_row.addWidget(self.export_config_btn)

        return template_row


    def build_technique_chip_row(self):
        chip_row = QHBoxLayout()
        chip_row.setSpacing(8)

        for step_tech in TECHNIQUE_CHIPS:
            meta = TECHNIQUE_DISPLAY[step_tech]
            btn = QPushButton(f" {meta['label']}")
            btn.setObjectName("ChipBtn")
            btn.setProperty("accentColor", meta["accent"])
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "plus.svg", color_hex=meta["hex"], size=CHIP_ICON_SIZE)))
            btn.clicked.connect(
                lambda checked=False, technique=step_tech: self.add_pipeline_step(
                    technique
                )
            )
            self.technique_buttons[step_tech] = btn
            chip_row.addWidget(btn)

        chip_row.addStretch()

        self.clear_pipeline_btn = QPushButton(" Clear")
        self.clear_pipeline_btn.setObjectName("ChipBtn")
        self.clear_pipeline_btn.setProperty("accentColor", "red")
        self.clear_pipeline_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_pipeline_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "trash.svg", color_hex=CLEAR_CHIP_COLOR, size=CHIP_ICON_SIZE)))
        self.clear_pipeline_btn.clicked.connect(self.confirm_clear_pipeline)
        chip_row.addWidget(self.clear_pipeline_btn)

        return chip_row


    def build_canvas(self):
        canvas = QFrame()
        canvas.setObjectName("pipelineCanvas")

        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(
            CANVAS_MARGIN,
            CANVAS_MARGIN,
            CANVAS_MARGIN,
            CANVAS_MARGIN,
        )

        self.empty_canvas_label = QLabel(
            "Add a technique above to create the first pipeline step."
        )
        self.empty_canvas_label.setObjectName("pipelineEmpty")
        self.empty_canvas_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_canvas_label.setWordWrap(True)
        canvas_layout.addWidget(self.empty_canvas_label)

        self.canvas_scroll = QScrollArea()
        self.canvas_scroll.setObjectName("pipelineCanvasScroll")
        self.canvas_scroll.setWidgetResizable(True)
        self.canvas_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.canvas_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.canvas_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.flow_container = QWidget()
        self.flow_container.setObjectName("pipelineCanvasContent")
        self.flow_layout = FlowLayout(
            self.flow_container,
            margin=0,
            spacing=FLOW_SPACING,
        )

        self.canvas_scroll.setWidget(self.flow_container)
        canvas_layout.addWidget(self.canvas_scroll)

        self.pipeline_canvas = canvas
        return canvas

    def add_pipeline_step(self, technique: str):
        if technique not in TECHNIQUE_DISPLAY:
            raise ValueError(f"Unsupported technique: {technique}")

        meta = TECHNIQUE_DISPLAY[technique]
        self.pipeline_steps.append(
            PipelineStepDraft(
                key=self.generate_step_key(),
                technique=technique,
                description=meta["description"],
            )
        )
        self.render_step_cards()

    def generate_step_key(self) -> str:
        while True:
            key = f"step_{uuid4().hex[:STEP_KEY_HEX_LENGTH]}"
            if key not in self.used_step_keys:
                self.used_step_keys.add(key)
                return key

    def build_output_catalog(
        self,
        before_step_index: int,
    ) -> list[StepOutputInfo]:
        if not 0 <= before_step_index <= len(self.pipeline_steps):
            raise IndexError("Step index is outside the pipeline")

        catalog: list[StepOutputInfo] = []
        for step_index in range(before_step_index):
            step = self.pipeline_steps[step_index]
            draft = step.technique_inputs
            output_keys = (
                [cover.output_key for cover in draft.covers]
                if isinstance(draft, LocomotiveInputsDraft)
                else ["result"]
            )
            for output_key in output_keys:
                output_info = self.step_output_info(step_index, output_key)
                if output_info is not None:
                    catalog.append(output_info)
        return catalog

    def step_index_for_key(self, step_key: str) -> int | None:
        return next(
            (
                index
                for index, step in enumerate(self.pipeline_steps)
                if step.key == step_key
            ),
            None,
        )

    def step_output_info(
        self,
        step_index: int,
        output_key: str,
    ) -> StepOutputInfo | None:
        if not 0 <= step_index < len(self.pipeline_steps):
            raise IndexError("Step index is outside the pipeline")

        step = self.pipeline_steps[step_index]
        if step.technique == "lsbpp":
            if output_key != "result":
                return None
            media_type = "png"
            display_name = None
        elif step.technique == "locomotive":
            draft = step.technique_inputs
            if not isinstance(draft, LocomotiveInputsDraft):
                return None
            output_index = next(
                (
                    index
                    for index, cover in enumerate(draft.covers)
                    if cover.output_key == output_key
                ),
                None,
            )
            if output_index is None:
                return None
            media_type = "png"
            display_name = f"Output {output_index + 1}"
        elif step.technique == "metadata":
            if output_key != "result":
                return None
            media_type = self.metadata_output_media_type(step)
            display_name = None
        else:
            return None

        return StepOutputInfo(
            reference=StepOutput(step.key, output_key),
            step_number=step_index + 1,
            technique=step.technique,
            media_type=media_type,
            preview_path=self.step_output_preview_path(step, output_key),
            display_name=display_name,
        )

    def linked_output_error(
        self,
        reference: StepOutput,
        consumer_index: int,
        accepted_media: set[str],
    ) -> str | None:
        if not 0 <= consumer_index < len(self.pipeline_steps):
            raise IndexError("Consumer index is outside the pipeline")

        producer_index = self.step_index_for_key(reference.step_key)
        if producer_index is None:
            return "Source step no longer exists."
        if producer_index == consumer_index:
            return "A step cannot use its own output."
        if producer_index > consumer_index:
            return "A step cannot use output from a later step."

        output_info = self.step_output_info(
            producer_index,
            reference.output_key,
        )
        if output_info is None:
            output_name = output_display_name(reference.output_key)
            return (
                f"{output_name} is not available from "
                f"Step {producer_index + 1}."
            )

        producer = self.pipeline_steps[producer_index]
        if producer.technique_inputs is None:
            return f"Step {producer_index + 1} is not configured yet."

        media_type = output_info.media_type
        if media_type is None:
            return f"Step {producer_index + 1} output type is unknown."

        accepted = {media.lower() for media in accepted_media}
        if media_type.lower() not in accepted:
            expected = ", ".join(sorted(media.upper() for media in accepted))
            return (
                f"{media_type.upper()} output from Step "
                f"{producer_index + 1} cannot be used here. "
                f"Expected: {expected}."
            )
        return None

    def linked_output_dependency_error(
        self,
        reference: StepOutput,
        consumer_index: int,
        accepted_media: set[str],
    ) -> str | None:
        """Validate a link and the producer chain behind that link."""
        direct_error = self.linked_output_error(
            reference,
            consumer_index,
            accepted_media,
        )
        if direct_error is not None:
            return direct_error

        usage_error = self.step_output_usage_error(
            reference,
            consumer_index,
        )
        if usage_error is not None:
            return usage_error

        producer_index = self.step_index_for_key(reference.step_key)
        if producer_index is None:
            return "Source step no longer exists."

        upstream_error = self.step_dependency_error(producer_index)
        if upstream_error is not None:
            return (
                f"Step {producer_index + 1} is blocked by an earlier "
                "dependency."
            )
        return None

    @staticmethod
    def step_output_references(
        step: PipelineStepDraft,
    ) -> list[StepOutput]:
        """Return every saved output reference used by a Step."""
        draft = step.technique_inputs
        if isinstance(draft, LSBInputsDraft) and isinstance(
            draft.cover,
            StepOutput,
        ):
            return [draft.cover]
        if isinstance(draft, LocomotiveInputsDraft):
            references = [
                cover.source
                for cover in draft.covers
                if isinstance(cover.source, StepOutput)
            ]
            if draft.payload_mode == "files":
                references.extend(
                    source
                    for source in draft.payload_files
                    if isinstance(source, StepOutput)
                )
            return references
        if isinstance(draft, MetadataInputsDraft):
            references = (
                [draft.cover]
                if isinstance(draft.cover, StepOutput)
                else []
            )
            if isinstance(draft.payload, MP3MetadataDraft):
                references.extend(
                    image.image
                    for image in draft.payload.apic_images
                    if isinstance(image.image, StepOutput)
                )
            return references
        return []

    def step_output_consumer_indices(
        self,
        reference: StepOutput,
    ) -> list[int]:
        consumers: list[int] = []
        for step_index, step in enumerate(self.pipeline_steps):
            consumers.extend(
                step_index
                for saved_reference in self.step_output_references(step)
                if saved_reference == reference
            )
        return consumers

    def step_output_usage_error(
        self,
        reference: StepOutput,
        consumer_index: int,
    ) -> str | None:
        """Enforce one saved consumer per output across all input roles."""
        if not 0 <= consumer_index < len(self.pipeline_steps):
            raise IndexError("Consumer index is outside the pipeline")

        consumers = self.step_output_consumer_indices(reference)
        if not consumers:
            return None

        if consumers.count(consumer_index) > 1:
            producer_index = self.step_index_for_key(reference.step_key)
            output_name = self.output_name_for_reference(reference)
            source = (
                output_name
                if producer_index is None
                else f"{output_name} from Step {producer_index + 1}"
            )
            return f"{source} is used more than once by Step {consumer_index + 1}."

        owner_index = consumers[0]
        if consumer_index == owner_index:
            return None

        producer_index = self.step_index_for_key(reference.step_key)
        output_name = self.output_name_for_reference(reference)
        if producer_index is None:
            source = output_name
        else:
            source = f"{output_name} from Step {producer_index + 1}"
        return f"{source} is already used by Step {owner_index + 1}."

    def output_name_for_reference(self, reference: StepOutput) -> str:
        producer_index = self.step_index_for_key(reference.step_key)
        if producer_index is None:
            return output_display_name(reference.output_key)
        output_info = self.step_output_info(
            producer_index,
            reference.output_key,
        )
        if output_info is not None and output_info.display_name:
            return output_info.display_name
        return output_display_name(reference.output_key)

    def step_output_preview_path(
        self,
        step: PipelineStepDraft,
        output_key: str = "result",
    ) -> str | None:
        draft = step.technique_inputs
        if isinstance(draft, LSBInputsDraft):
            return self.resolve_source_preview_path(draft.cover)
        if isinstance(draft, LocomotiveInputsDraft):
            cover = next(
                (
                    cover
                    for cover in draft.covers
                    if cover.output_key == output_key
                ),
                None,
            )
            return (
                self.resolve_source_preview_path(cover.source)
                if cover is not None
                else None
            )
        if isinstance(draft, MetadataInputsDraft):
            return self.resolve_source_preview_path(draft.cover)
        return None

    def resolve_source_preview_path(
        self,
        source: str | StepOutput | None,
        visited_steps: set[str] | None = None,
    ) -> str | None:
        if isinstance(source, str):
            return source
        if source is None:
            return None

        visited = set() if visited_steps is None else set(visited_steps)
        if source.step_key in visited:
            return None
        visited.add(source.step_key)

        producer = self.step_draft_for_key(source.step_key)
        if producer is None:
            return None
        draft = producer.technique_inputs
        if isinstance(draft, LSBInputsDraft):
            return self.resolve_source_preview_path(draft.cover, visited)
        if isinstance(draft, LocomotiveInputsDraft):
            cover = next(
                (
                    cover
                    for cover in draft.covers
                    if cover.output_key == source.output_key
                ),
                None,
            )
            return (
                self.resolve_source_preview_path(cover.source, visited)
                if cover is not None
                else None
            )
        if isinstance(draft, MetadataInputsDraft):
            return self.resolve_source_preview_path(draft.cover, visited)
        return None

    @staticmethod
    def metadata_output_media_type(
        step: PipelineStepDraft,
    ) -> str | None:
        draft = step.technique_inputs
        if not isinstance(draft, MetadataInputsDraft):
            return None
        if isinstance(draft.payload, PNGMetadataDraft):
            return "png"
        if isinstance(draft.payload, MP3MetadataDraft):
            return "mp3"
        if isinstance(draft.cover, str):
            suffix = Path(draft.cover).suffix.lower()
            if suffix in {".png", ".mp3"}:
                return suffix[1:]
        return None

    def clear_pipeline(self):
        self.close_active_step_config()
        self.pipeline_steps.clear()
        self.render_step_cards()

    def confirm_clear_pipeline(self) -> None:
        if not self.pipeline_steps:
            return

        step_count = len(self.pipeline_steps)
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Clear Pipeline")
        dialog.setText("Clear entire pipeline?")
        dialog.setInformativeText(
            f"This will remove all {step_count} steps and their current "
            "configuration.\nThis action cannot be undone."
        )

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("SecondaryBtn")
        dialog.addButton(cancel_button, QMessageBox.ButtonRole.RejectRole)

        clear_button = QPushButton("Clear Pipeline")
        clear_button.setObjectName("DangerBtn")
        dialog.addButton(clear_button, QMessageBox.ButtonRole.DestructiveRole)
        dialog.setDefaultButton(cancel_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec()

        if dialog.clickedButton() is clear_button:
            self.clear_pipeline()

    def remove_pipeline_step(self, index: int):
        if not 0 <= index < len(self.pipeline_steps):
            return

        self.close_active_step_config()
        self.pipeline_steps.pop(index)
        self.render_step_cards()

    def step_draft_for_key(self, step_key: str) -> PipelineStepDraft | None:
        step_index = self.step_index_for_key(step_key)
        if step_index is None:
            return None
        return self.pipeline_steps[step_index]

    def save_step_draft(
        self,
        step_key: str,
        description: str,
        guidenote: str,
        technique_form: QWidget | None = None,
    ) -> bool:
        step = self.step_draft_for_key(step_key)
        if step is None:
            return False

        description = description.strip()
        if not description:
            QMessageBox.warning(
                self,
                "Description Required",
                "Enter a description before saving this step.",
            )
            return False

        technique_inputs = step.technique_inputs
        if isinstance(technique_form, LSBEmbedInputs):
            if not technique_form.validate_draft():
                return False
            lsb_draft = technique_form.export_draft()
            if isinstance(lsb_draft.cover, StepOutput):
                step_index = self.step_index_for_key(step_key)
                if step_index is None:
                    return False
                dependency_error = self.linked_output_dependency_error(
                    lsb_draft.cover,
                    step_index,
                    {"png"},
                )
                if dependency_error is not None:
                    technique_form.cover_output_picker.set_unavailable_reason(
                        dependency_error
                    )
                    return technique_form.show_validation_warning(
                        dependency_error,
                        title="Linked Output Unavailable",
                    )
            technique_inputs = lsb_draft
        elif isinstance(technique_form, LocomotiveEmbedInputs):
            if not technique_form.validate_draft():
                return False
            locomotive_draft = technique_form.export_draft()
            step_index = self.step_index_for_key(step_key)
            if step_index is None:
                return False
            linked_inputs = [
                (cover.source, {"png"})
                for cover in locomotive_draft.covers
                if isinstance(cover.source, StepOutput)
            ]
            if locomotive_draft.payload_mode == "files":
                linked_inputs.extend(
                    (source, {"png", "mp3"})
                    for source in locomotive_draft.payload_files
                    if isinstance(source, StepOutput)
                )

            references = [reference for reference, _media in linked_inputs]
            if len(references) != len(set(references)):
                return technique_form.show_validation_warning(
                    "The same previous output cannot be used more than once "
                    "in a Locomotive step.",
                    title="Linked Output Already Used",
                )

            for reference, accepted_media in linked_inputs:
                dependency_error = self.linked_output_dependency_error(
                    reference,
                    step_index,
                    accepted_media,
                )
                if dependency_error is not None:
                    return technique_form.show_validation_warning(
                        dependency_error,
                        title="Linked Output Unavailable",
                    )
            technique_inputs = locomotive_draft
        elif isinstance(technique_form, MetadataEmbedInputs):
            if not technique_form.validate_draft():
                return False
            metadata_draft = technique_form.export_draft()
            step_index = self.step_index_for_key(step_key)
            if step_index is None:
                return False
            linked_apic_images = (
                [
                    image.image
                    for image in metadata_draft.payload.apic_images
                    if isinstance(image.image, StepOutput)
                ]
                if isinstance(metadata_draft.payload, MP3MetadataDraft)
                else []
            )
            linked_references = (
                [metadata_draft.cover]
                if isinstance(metadata_draft.cover, StepOutput)
                else []
            )
            linked_references.extend(linked_apic_images)
            if len(linked_references) != len(set(linked_references)):
                return technique_form.show_validation_warning(
                    "The same previous output cannot be used more than once "
                    "in a Metadata step.",
                    title="Linked Output Already Used",
                )
            if isinstance(metadata_draft.cover, StepOutput):
                dependency_error = self.linked_output_dependency_error(
                    metadata_draft.cover,
                    step_index,
                    {"png", "mp3"},
                )
                if dependency_error is not None:
                    technique_form.cover_output_picker.set_unavailable_reason(
                        dependency_error
                    )
                    return technique_form.show_validation_warning(
                        dependency_error,
                        title="Linked Output Unavailable",
                    )
            for reference in linked_apic_images:
                dependency_error = self.linked_output_dependency_error(
                    reference,
                    step_index,
                    {"png"},
                )
                if dependency_error is not None:
                    apic_form = (
                        technique_form.mp3_form.apic_images_form
                    )
                    apic_form.mark_linked_source_unavailable(
                        reference,
                        dependency_error,
                    )
                    return technique_form.show_validation_warning(
                        dependency_error,
                        title="Linked APIC Source Unavailable",
                    )
            technique_inputs = metadata_draft

        step.description = description
        step.guidenote = guidenote.strip()
        step.technique_inputs = technique_inputs
        return True

    def create_step_technique_form(
        self,
        step: PipelineStepDraft,
        step_index: int,
    ) -> QWidget | None:
        if step.technique == "lsbpp":
            cover_dependency_error = None
            if (
                isinstance(step.technique_inputs, LSBInputsDraft)
                and isinstance(step.technique_inputs.cover, StepOutput)
            ):
                cover_dependency_error = self.linked_output_dependency_error(
                    step.technique_inputs.cover,
                    step_index,
                    {"png"},
                )
            output_catalog = [
                output
                for output in self.build_output_catalog(step_index)
                if output.media_type == "png"
                and self.linked_output_dependency_error(
                    output.reference,
                    step_index,
                    {"png"},
                )
                is None
            ]
            form = LSBEmbedInputs(
                key_registry=self.key_registry,
                output_catalog=output_catalog,
                cover_dependency_error=cover_dependency_error,
            )
            if isinstance(step.technique_inputs, LSBInputsDraft):
                form.load_draft(step.technique_inputs)
            return form

        if step.technique == "locomotive":
            saved_draft = (
                step.technique_inputs
                if isinstance(step.technique_inputs, LocomotiveInputsDraft)
                else LocomotiveInputsDraft()
            )
            saved_cover_references = {
                cover.source
                for cover in saved_draft.covers
                if isinstance(cover.source, StepOutput)
            }
            saved_payload_references = (
                {
                    source
                    for source in saved_draft.payload_files
                    if isinstance(source, StepOutput)
                }
                if saved_draft.payload_mode == "files"
                else set()
            )
            all_outputs = self.build_output_catalog(step_index)
            cover_output_catalog = [
                output
                for output in all_outputs
                if output.media_type == "png"
                and self.linked_output_dependency_error(
                    output.reference,
                    step_index,
                    {"png"},
                )
                is None
                and (
                    not self.step_output_consumer_indices(output.reference)
                    or output.reference in saved_cover_references
                )
            ]
            payload_output_catalog = [
                output
                for output in all_outputs
                if output.media_type in {"png", "mp3"}
                and self.linked_output_dependency_error(
                    output.reference,
                    step_index,
                    {"png", "mp3"},
                )
                is None
                and (
                    not self.step_output_consumer_indices(output.reference)
                    or output.reference in saved_payload_references
                )
            ]
            cover_dependency_errors = {
                reference: error
                for reference in saved_cover_references
                if (
                    error := self.linked_output_dependency_error(
                        reference,
                        step_index,
                        {"png"},
                    )
                )
                is not None
            }
            payload_dependency_errors = {
                reference: error
                for reference in saved_payload_references
                if (
                    error := self.linked_output_dependency_error(
                        reference,
                        step_index,
                        {"png", "mp3"},
                    )
                )
                is not None
            }
            form = LocomotiveEmbedInputs(
                key_registry=self.key_registry,
                output_catalog=cover_output_catalog,
                payload_output_catalog=payload_output_catalog,
                cover_dependency_errors=cover_dependency_errors,
                payload_dependency_errors=payload_dependency_errors,
            )
            if isinstance(step.technique_inputs, LocomotiveInputsDraft):
                form.load_draft(step.technique_inputs)
            return form

        if step.technique == "metadata":
            saved_draft = (
                step.technique_inputs
                if isinstance(step.technique_inputs, MetadataInputsDraft)
                else MetadataInputsDraft()
            )
            saved_reference = (
                saved_draft.cover
                if isinstance(saved_draft.cover, StepOutput)
                else None
            )
            saved_apic_references = {
                image.image
                for image in (
                    saved_draft.payload.apic_images
                    if isinstance(saved_draft.payload, MP3MetadataDraft)
                    else []
                )
                if isinstance(image.image, StepOutput)
            }
            cover_dependency_error = (
                self.linked_output_dependency_error(
                    saved_reference,
                    step_index,
                    {"png", "mp3"},
                )
                if saved_reference is not None
                else None
            )
            all_outputs = self.build_output_catalog(step_index)
            output_catalog = [
                output
                for output in all_outputs
                if output.media_type in {"png", "mp3"}
                and self.linked_output_dependency_error(
                    output.reference,
                    step_index,
                    {"png", "mp3"},
                )
                is None
                and (
                    not self.step_output_consumer_indices(output.reference)
                    or output.reference == saved_reference
                )
            ]
            apic_output_catalog = [
                output
                for output in all_outputs
                if output.media_type == "png"
                and self.linked_output_dependency_error(
                    output.reference,
                    step_index,
                    {"png"},
                )
                is None
                and (
                    not self.step_output_consumer_indices(output.reference)
                    or output.reference in saved_apic_references
                )
            ]
            apic_dependency_errors = {
                reference: error
                for reference in saved_apic_references
                if (
                    error := self.linked_output_dependency_error(
                        reference,
                        step_index,
                        {"png"},
                    )
                )
                is not None
            }
            form = MetadataEmbedInputs(
                output_catalog=output_catalog,
                cover_dependency_error=cover_dependency_error,
                apic_output_catalog=apic_output_catalog,
                apic_dependency_errors=apic_dependency_errors,
            )
            if isinstance(step.technique_inputs, MetadataInputsDraft):
                form.load_draft(step.technique_inputs)
            return form

        raise ValueError(f"Unsupported technique: {step.technique}")

    def on_step_card_clicked(self, index: int) -> None:
        if not 0 <= index < len(self.pipeline_steps):
            return

        step = self.pipeline_steps[index]
        print(f"Step {index + 1} clicked: technique={step.technique}")
        if self.config_variant == "inline":
            self.open_step_config_inline(index)
        else:
            self.open_step_config_popup(index)

    def open_step_config_popup(self, index: int) -> None:
        if not 0 <= index < len(self.pipeline_steps):
            return

        self.close_active_step_config()
        step = self.pipeline_steps[index]
        meta = TECHNIQUE_DISPLAY[step.technique]
        technique_form = self.create_step_technique_form(step, index)
        dialog = StepConfigShellDialog(
            step_number=index + 1,
            technique_label=meta["label"],
            description=step.description,
            accent=meta["accent"],
            guidenote=step.guidenote,
            content_widget=technique_form,
            save_callback=partial(
                self.save_step_draft,
                step.key,
                technique_form=technique_form,
            ),
            parent=self.window(),
        )
        self.active_step_index = index
        self.active_step_key = step.key
        self.active_step_dialog = dialog
        result = dialog.exec()

        if self.active_step_dialog is dialog:
            self.active_step_dialog = None
            self.active_step_index = None
            self.active_step_key = None
        if result == QDialog.DialogCode.Accepted:
            self.render_step_cards()
        dialog.deleteLater()

    def open_step_config_inline(self, index: int) -> None:
        if not 0 <= index < len(self.pipeline_steps):
            return

        self.close_active_step_config()
        step = self.pipeline_steps[index]
        meta = TECHNIQUE_DISPLAY[step.technique]
        technique_form = self.create_step_technique_form(step, index)
        panel = StepConfigShellPanel(
            step_number=index + 1,
            technique_label=meta["label"],
            description=step.description,
            accent=meta["accent"],
            guidenote=step.guidenote,
            content_widget=technique_form,
            save_callback=partial(
                self.save_step_draft,
                step.key,
                technique_form=technique_form,
            ),
        )
        panel.saved.connect(self.on_inline_step_saved)
        panel.cancelled.connect(self.close_active_step_config)
        self.active_step_index = index
        self.active_step_key = step.key
        self.active_step_panel = panel
        self.inline_slot.addWidget(panel)
        panel.show()
        self._refresh_page_layout()
        QTimer.singleShot(0, lambda: self.page_scroll.ensureWidgetVisible(panel))

    def on_inline_step_saved(self) -> None:
        self.close_active_step_config()
        self.render_step_cards()

    def close_active_step_config(self) -> None:
        dialog = self.active_step_dialog
        panel = self.active_step_panel
        self.active_step_dialog = None
        self.active_step_panel = None
        self.active_step_index = None
        self.active_step_key = None
        if dialog is not None:
            dialog.reject()
        if panel is not None:
            self.inline_slot.removeWidget(panel)
            panel.hide()
            panel.deleteLater()
            self._refresh_page_layout()

    def set_config_variant(self, variant: str) -> None:
        if variant not in {"popup", "inline"}:
            raise ValueError(f"Unsupported step config variant: {variant}")
        if variant == self.config_variant:
            return

        self.close_active_step_config()
        self.config_variant = variant

    def render_step_cards(self):
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        self.step_cards = []
        for step_number, step in enumerate(self.pipeline_steps, start=1):
            if step_number > 1:
                self.flow_layout.addWidget(make_arrow())

            step_card = StepCard(
                step_number,
                step.technique,
                description=step.description,
            )
            step_card.remove_requested.connect(
                lambda index=step_number - 1: self.remove_pipeline_step(index)
            )
            step_card.clicked.connect(
                lambda index=step_number - 1: self.on_step_card_clicked(index)
            )
            self.apply_step_draft_to_card(step_card, step)
            dependency_error = self.step_dependency_error(step_number - 1)
            if dependency_error is not None:
                step_card.set_status("blocked", dependency_error)
            self.step_cards.append(step_card)
            self.flow_layout.addWidget(step_card)

        has_steps = bool(self.pipeline_steps)
        self.empty_canvas_label.setVisible(not has_steps)
        self.canvas_scroll.setVisible(has_steps)
        if not has_steps:
            self.canvas_scroll.verticalScrollBar().setValue(0)

        self.refresh_canvas_height()

    def apply_step_draft_to_card(
        self,
        step_card: StepCard,
        step: PipelineStepDraft,
    ) -> None:
        draft = step.technique_inputs
        if step.technique == "lsbpp" and isinstance(draft, LSBInputsDraft):
            self.apply_lsb_draft_to_card(step_card, draft)
            return

        if step.technique == "locomotive" and isinstance(
            draft,
            LocomotiveInputsDraft,
        ):
            self.apply_locomotive_draft_to_card(
                step_card,
                draft,
            )
            return

        if (
            step.technique == "metadata"
            and isinstance(draft, MetadataInputsDraft)
        ):
            if isinstance(draft.payload, PNGMetadataDraft):
                self.apply_metadata_png_draft_to_card(
                    step_card,
                    draft,
                )
            elif isinstance(draft.payload, MP3MetadataDraft):
                self.apply_metadata_mp3_draft_to_card(
                    step_card,
                    draft,
                )

    def apply_lsb_draft_to_card(
        self,
        step_card: StepCard,
        draft: LSBInputsDraft,
    ) -> None:
        encryption = EmbedConfigurablePage.encryption_summary(
            draft.encryption_enabled,
            draft.encryption_mode,
        )
        if isinstance(draft.cover, StepOutput):
            cover = self.step_output_summary(draft.cover)
        elif draft.cover:
            cover = Path(draft.cover).name
        else:
            cover = "Not selected"

        step_card.set_summary(
            cover=cover,
            payload=(
                f"Text ({format_file_size(len(draft.payload_text.encode('utf-8')))})"
            ),
            output="PNG ×1",
            encryption=encryption,
        )
        if isinstance(draft.cover, StepOutput):
            step_card.set_summary_tooltip(
                "cover",
                self.step_output_tooltip(draft.cover),
            )
        step_card.set_status("ready", "LSB++ inputs are configured")

    def step_dependency_error(self, step_index: int) -> str | None:
        if not 0 <= step_index < len(self.pipeline_steps):
            raise IndexError("Step index is outside the pipeline")

        step = self.pipeline_steps[step_index]
        if any(
            reference.step_key == step.key
            for reference in self.step_output_references(step)
        ):
            return "A step cannot use its own output."

        if self._has_dependency_cycle(step_index):
            return "Circular dependency detected."

        draft = step.technique_inputs
        if isinstance(draft, LSBInputsDraft) and isinstance(
            draft.cover,
            StepOutput,
        ):
            return self.linked_output_dependency_error(
                draft.cover,
                step_index,
                {"png"},
            )
        if isinstance(draft, LocomotiveInputsDraft):
            linked_inputs = [
                (cover.source, {"png"})
                for cover in draft.covers
                if isinstance(cover.source, StepOutput)
            ]
            if draft.payload_mode == "files":
                linked_inputs.extend(
                    (source, {"png", "mp3"})
                    for source in draft.payload_files
                    if isinstance(source, StepOutput)
                )
            for reference, accepted_media in linked_inputs:
                dependency_error = self.linked_output_dependency_error(
                    reference,
                    step_index,
                    accepted_media,
                )
                if dependency_error is not None:
                    return dependency_error
        if isinstance(draft, MetadataInputsDraft):
            linked_inputs = (
                [(draft.cover, {"png", "mp3"})]
                if isinstance(draft.cover, StepOutput)
                else []
            )
            if isinstance(draft.payload, MP3MetadataDraft):
                linked_inputs.extend(
                    (image.image, {"png"})
                    for image in draft.payload.apic_images
                    if isinstance(image.image, StepOutput)
                )
            for reference, accepted_media in linked_inputs:
                dependency_error = self.linked_output_dependency_error(
                    reference,
                    step_index,
                    accepted_media,
                )
                if dependency_error is not None:
                    return dependency_error
        return None

    def _has_dependency_cycle(
        self,
        step_index: int,
        path: set[str] | None = None,
    ) -> bool:
        """Follow saved linked covers while guarding invalid imported graphs."""
        step = self.pipeline_steps[step_index]
        current_path = set() if path is None else path
        if step.key in current_path:
            return True

        for reference in self.step_output_references(step):
            producer_index = self.step_index_for_key(reference.step_key)
            if producer_index is None:
                continue
            if self._has_dependency_cycle(
                producer_index,
                current_path | {step.key},
            ):
                return True
        return False

    def step_output_summary(self, reference: StepOutput) -> str:
        producer_index = self.step_index_for_key(reference.step_key)
        if producer_index is None:
            return "Source unavailable"
        output_info = self.step_output_info(
            producer_index,
            reference.output_key,
        )
        output_name = (
            output_info.display_name
            if output_info is not None and output_info.display_name
            else output_display_name(reference.output_key)
        )
        return f"From STEP {producer_index + 1}, {output_name}"

    def step_output_tooltip(self, reference: StepOutput) -> str:
        producer = self.step_draft_for_key(reference.step_key)
        if producer is None:
            return "Source step no longer exists."
        preview_path = (
            self.step_output_preview_path(producer, reference.output_key)
        )
        source_name = Path(preview_path).name if preview_path else "Unavailable"
        return f"{self.step_output_summary(reference)}\nSource: {source_name}"

    def apply_locomotive_draft_to_card(
        self,
        step_card: StepCard,
        draft: LocomotiveInputsDraft,
    ) -> None:
        cover_count = len(draft.covers)
        if cover_count == 1:
            source = draft.covers[0].source
            cover = (
                self.step_output_summary(source)
                if isinstance(source, StepOutput)
                else Path(source).name
            )
        else:
            cover = f"PNG ×{cover_count}"

        if draft.payload_mode == "text":
            payload_size = len(draft.payload_text.encode("utf-8"))
            payload = f"Text ({format_file_size(payload_size)})"
        else:
            manual_payloads = [
                source
                for source in draft.payload_files
                if isinstance(source, str)
            ]
            linked_payloads = [
                source
                for source in draft.payload_files
                if isinstance(source, StepOutput)
            ]
            payload_size = sum(
                Path(path).stat().st_size
                for path in manual_payloads
                if Path(path).is_file()
            )
            if linked_payloads:
                payload = f"Files ×{len(draft.payload_files)} (at run)"
            else:
                payload = (
                    f"Files ×{len(draft.payload_files)} "
                    f"({format_file_size(payload_size)})"
                )

        step_card.set_summary(
            cover=cover,
            payload=payload,
            output=f"PNG ×{cover_count}",
            encryption=EmbedConfigurablePage.encryption_summary(
                draft.encryption_enabled,
                draft.encryption_mode,
            ),
        )

        if cover_count > 1:
            cover_lines = [f"Cover PNGs ({cover_count}):"]
            cover_lines.extend(
                (
                    f"{index}. {self.step_output_summary(item.source)}"
                    if isinstance(item.source, StepOutput)
                    else f"{index}. {Path(item.source).name}"
                )
                for index, item in enumerate(draft.covers, start=1)
            )
            step_card.set_summary_tooltip(
                "cover",
                "\n".join(cover_lines),
            )
        elif cover_count == 1 and isinstance(
            draft.covers[0].source,
            StepOutput,
        ):
            step_card.set_summary_tooltip(
                "cover",
                self.step_output_tooltip(draft.covers[0].source),
            )

        if draft.payload_mode == "files":
            payload_lines = [
                f"Payload files ({len(draft.payload_files)}):"
            ]
            for index, source in enumerate(draft.payload_files, start=1):
                if isinstance(source, StepOutput):
                    payload_lines.append(
                        f"{index}. {self.step_output_summary(source)}"
                    )
                else:
                    file_path = Path(source)
                    file_size = (
                        format_file_size(file_path.stat().st_size)
                        if file_path.is_file()
                        else "Unavailable"
                    )
                    payload_lines.append(
                        f"{index}. {file_path.name} — {file_size}"
                    )
            if not linked_payloads:
                payload_lines.append(
                    f"Total: {format_file_size(payload_size)}"
                )
            step_card.set_summary_tooltip(
                "payload",
                "\n".join(payload_lines),
            )

        step_card.set_status("ready", "Locomotive inputs are configured")

    def apply_metadata_png_draft_to_card(
        self,
        step_card: StepCard,
        draft: MetadataInputsDraft,
    ) -> None:
        payload = draft.payload
        if not isinstance(payload, PNGMetadataDraft):
            return
        if not payload.entries:
            return
        if isinstance(draft.cover, str):
            if Path(draft.cover).suffix.lower() != ".png":
                return
            cover_summary = Path(draft.cover).name
        elif isinstance(draft.cover, StepOutput):
            cover_summary = self.step_output_summary(draft.cover)
        else:
            return

        entry_count = len(payload.entries)
        step_card.set_summary(
            cover=cover_summary,
            payload=f"Text fields ×{entry_count}",
            output="PNG ×1",
            encryption="None",
        )
        if isinstance(draft.cover, StepOutput):
            step_card.set_summary_tooltip(
                "cover",
                self.step_output_tooltip(draft.cover),
            )

        key_lines = [f"PNG metadata fields ({entry_count}):"]
        key_lines.extend(
            f"{index}. {keyword}"
            for index, keyword in enumerate(payload.entries, start=1)
        )
        step_card.set_summary_tooltip(
            "payload",
            "\n".join(key_lines),
        )
        step_card.set_status(
            "ready",
            "PNG metadata inputs are configured",
        )

    def apply_metadata_mp3_draft_to_card(
        self,
        step_card: StepCard,
        draft: MetadataInputsDraft,
    ) -> None:
        payload = draft.payload
        if not isinstance(payload, MP3MetadataDraft):
            return
        if isinstance(draft.cover, str):
            if Path(draft.cover).suffix.lower() != ".mp3":
                return
            cover_summary = Path(draft.cover).name
        elif isinstance(draft.cover, StepOutput):
            cover_summary = self.step_output_summary(draft.cover)
        else:
            return

        frame_count = 0
        frame_lines: list[str] = []
        seen_frame_ids: set[str] = set()
        for frame in payload.frames:
            frame_id = frame.frame_id
            frame_info = FRAME_INFO.get(frame_id)
            if frame_info is None or frame_id in seen_frame_ids:
                return
            seen_frame_ids.add(frame_id)

            if isinstance(frame, MP3SimpleFrameDraft):
                if not frame.value.strip():
                    return
                instance_count = 1
            elif isinstance(frame, MP3ComplexFrameDraft):
                if not frame.instances:
                    return
                if any(
                    not ((instance.text or "").strip())
                    and not ((instance.url or "").strip())
                    for instance in frame.instances
                ):
                    return
                instance_count = len(frame.instances)
            else:
                return

            frame_count += instance_count
            count_suffix = (
                f" ×{instance_count}" if instance_count > 1 else ""
            )
            frame_lines.append(
                f"{len(frame_lines) + 1}. {frame_id}{count_suffix} - "
                f"{frame_info[0]}"
            )

        apic_lines: list[str] = []
        for image in payload.apic_images:
            if (
                not isinstance(image, ApicImageDraft)
                or image.picture_type not in APIC_TYPES
            ):
                return
            if isinstance(image.image, StepOutput):
                image_name = self.step_output_summary(image.image)
            elif isinstance(image.image, str) and image.image.strip():
                image_name = Path(image.image).name
            else:
                return
            apic_lines.append(
                f"{len(apic_lines) + 1}. {image_name} - "
                f"{APIC_TYPES[image.picture_type]}"
            )

        apic_count = len(apic_lines)
        if frame_count == 0 and apic_count == 0:
            return

        if frame_count and apic_count:
            payload_summary = f"Text ×{frame_count} + APIC ×{apic_count}"
            tooltip_lines = [
                "MP3 metadata payload:",
                f"Text frames ({frame_count}):",
                *frame_lines,
                f"APIC images ({apic_count}):",
                *apic_lines,
            ]
            status_tooltip = "MP3 text-frame and APIC inputs are configured"
        elif frame_count:
            payload_summary = f"Text frames ×{frame_count}"
            tooltip_lines = [f"MP3 text frames ({frame_count}):", *frame_lines]
            status_tooltip = "MP3 text-frame inputs are configured"
        else:
            payload_summary = f"APIC images ×{apic_count}"
            tooltip_lines = [f"MP3 APIC images ({apic_count}):", *apic_lines]
            status_tooltip = "MP3 APIC inputs are configured"

        step_card.set_summary(
            cover=cover_summary,
            payload=payload_summary,
            output="MP3 ×1",
            encryption="None",
        )
        if isinstance(draft.cover, StepOutput):
            step_card.set_summary_tooltip(
                "cover",
                self.step_output_tooltip(draft.cover),
            )
        step_card.set_summary_tooltip(
            "payload",
            "\n".join(tooltip_lines),
        )
        step_card.set_status(
            "ready",
            status_tooltip,
        )

    @staticmethod
    def encryption_summary(enabled: bool, mode: str) -> str:
        if not enabled:
            return "None"
        if mode == "public_key":
            return "Public Key"
        return "Password"

    def refresh_canvas_height(self):
        self._update_canvas_height()
        QTimer.singleShot(0, self._update_canvas_height)

    def _update_canvas_height(self):
        if not self.pipeline_steps:
            self.flow_container.setMinimumHeight(0)
            self.flow_container.resize(self.flow_container.width(), 0)
            self.canvas_scroll.setFixedHeight(CARD_HEIGHT)
            self.pipeline_canvas.setFixedHeight(CARD_HEIGHT + CANVAS_MARGIN * 2)
            self._refresh_page_layout()
            return

        viewport_width = self.canvas_scroll.viewport().width()
        if viewport_width <= 0:
            return

        required_height = self.flow_layout.heightForWidth(viewport_width)
        required_height = max(CARD_HEIGHT, required_height)
        self.flow_container.setMinimumHeight(required_height)

        visible_flow_height = min(required_height, MAX_VISIBLE_FLOW_HEIGHT)
        self.canvas_scroll.setFixedHeight(visible_flow_height)
        self.pipeline_canvas.setFixedHeight(
            visible_flow_height + CANVAS_MARGIN * 2
        )
        self._refresh_page_layout()

    def _refresh_page_layout(self):
        self.pipeline_builder_card.layout().invalidate()
        self.pipeline_builder_card.updateGeometry()
        self.page_content_layout.invalidate()
        self.page_content_layout.activate()
        self.page_content.updateGeometry()


    def build_step_ui_row(self):
        row = QHBoxLayout()
        row.setSpacing(8)

        label = QLabel("STEP CONFIG UI:")
        label.setObjectName("stepConfigUI")
        row.addWidget(label)

        self.btn_popup = QPushButton(" Popup Dialog")
        self.btn_popup.setObjectName("stepUiBtn")
        self.btn_popup.setCheckable(True)
        self.btn_popup.setChecked(True)
        self.btn_popup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_popup.clicked.connect(
            lambda checked=False: self.set_config_variant("popup")
        )

        self.btn_inline = QPushButton(" Inline Panel")
        self.btn_inline.setObjectName("stepUiBtn")
        self.btn_inline.setCheckable(True)
        self.btn_inline.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_inline.clicked.connect(
            lambda checked=False: self.set_config_variant("inline")
        )

        variant_group = QButtonGroup(self)
        variant_group.setExclusive(True)
        variant_group.addButton(self.btn_popup)
        variant_group.addButton(self.btn_inline)

        row.addWidget(self.btn_popup)
        row.addWidget(self.btn_inline)
        row.addStretch()
        return row


    # --- แถบล่าง: status + progress + Export/Run ---
    def build_execution_bar(self):
        execution_bar = QHBoxLayout()
        execution_bar.setContentsMargins(0, 0, 0, 0)
        execution_bar.setSpacing(8)

        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QVBoxLayout(status_card)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("loadingIndicator")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Status: Ready")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.status_label)

        execution_bar.addWidget(status_card, 1)

        # Save Outputs เปิดใช้ได้เฉพาะหลัง Run Pipeline สำเร็จ (มีไฟล์ output ให้ save)
        self.save_outputs_btn = QPushButton(" Save Outputs")
        self.save_outputs_btn.setObjectName("SecondaryBtn")
        self.save_outputs_btn.setProperty("textColor", "white")
        self.save_outputs_btn.setFixedHeight(50)
        self.save_outputs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_outputs_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "upload.svg", color_hex="#FFFFFF", size=ICON_SIZE)))
        self.save_outputs_btn.setEnabled(False)
        # self.save_outputs_btn.clicked.connect(self.on_save_outputs) TODO
        execution_bar.addWidget(self.save_outputs_btn)

        self.run_pipeline_btn = QPushButton("Run Pipeline")
        self.run_pipeline_btn.setObjectName("PrimaryActionBtn")
        self.run_pipeline_btn.setFixedHeight(50)
        self.run_pipeline_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # self.run_pipeline_btn.clicked.connect(self.on_run_pipeline) TODO
        execution_bar.addWidget(self.run_pipeline_btn)

        return execution_bar
