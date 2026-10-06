from pathlib import Path
from copy import deepcopy
from uuid import uuid4

from PyQt6.QtCore import QEvent, QTimer, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, format_file_size
from src.gui.components.widgets.execution_bar import ExecutionBar
from src.core.configurable.step_output import StepOutput, StepOutputInfo
from src.core.stego.metadata_handlers.mp3_handler import APIC_TYPES, FRAME_INFO
from src.gui.features.embed.configurable.pipeline_links import (
    build_output_catalog as collect_output_catalog, declared_step_outputs,
    evaluate_pipeline_statuses, reconcile_links,
    build_output_usage, validate_output_usage,
)
from src.gui.features.embed.configurable.pipeline_draft import PipelineStepDraft
from src.gui.features.embed.configurable.pipeline_run import PipelineRunContext
from src.gui.features.embed.configurable.pipeline_execution import run_pipeline
from src.gui.features.embed.configurable.pipeline_delivery import save_outputs
from src.gui.features.embed.forms.lsb_form import LSBInputForm, LSBInputsDraft
from src.gui.features.embed.forms.locomotive_form import LocomotiveInputForm, LocomotiveInputsDraft
from src.gui.features.embed.forms.metadata_form import MetadataInputForm, MetadataInputsDraft
from src.gui.features.embed.forms.metadata.png_form import PNGMetadataDraft
from src.gui.features.embed.forms.metadata.mp3_draft import MP3ComplexFrameDraft, MP3MetadataDraft
from src.gui.features.embed.configurable.widgets.flow_layout import FlowLayout
from src.gui.features.embed.configurable.widgets.step_canvas import StepCanvas
from src.gui.features.embed.configurable.widgets.step_config_shell import StepConfigShellDialog, StepConfigShellPanel
from src.gui.features.embed.configurable.widgets.step_card import (
    CARD_HEIGHT, TECHNIQUE_DISPLAY, StepCard, make_arrow,
)
from src.gui.services.key_registry import KeyRegistry
from src.gui.services.worker import FunctionWorker
from src.path import svg_path


ICON_SIZE = 16
CHIP_ICON_SIZE = 12
CANVAS_MARGIN = 16
EMPTY_CANVAS_HEIGHT = 192
FLOW_SPACING = 8
MAX_VISIBLE_FLOW_HEIGHT = CARD_HEIGHT * 2 + FLOW_SPACING


class EmbedConfigurablePage(QFrame):
    """Pipeline builder and sequential execution of saved technique drafts."""

    def __init__(self, key_registry: KeyRegistry | None = None, parent=None):
        super().__init__(parent)
        self.key_registry = key_registry
        self.technique_buttons: dict[str, QPushButton] = {}
        self.step_cards: list[StepCard] = []
        # Cards own the visual order; drafts are addressed by stable identity.
        self.step_drafts: dict[str, PipelineStepDraft] = {}
        self.active_step_dialog: StepConfigShellDialog | None = None
        self.active_step_panel: StepConfigShellPanel | None = None
        self.active_step_card: StepCard | None = None
        self.run_worker = None
        self.run_context = None
        self.last_run_context = None
        self.pending_run_result = None
        self.save_worker = None
        self.pending_save_result = None
        self.setup_ui()
        QApplication.instance().aboutToQuit.connect(self.cleanup_run_workspaces)

    def setup_ui(self):
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)

        # Builder content scrolls independently of the execution bar below.
        self.page_scroll = QScrollArea()
        self.page_scroll.setObjectName("pipelineScroll")
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("pipelineScrollContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(10)
        self.pipeline_builder_card = self.build_pipeline_builder_card()
        content_layout.addWidget(self.pipeline_builder_card)
        self.link_notice = QLabel()
        self.link_notice.setObjectName("hintLabel")
        self.link_notice.setWordWrap(True)
        content_layout.addWidget(self.link_notice)
        self.link_notice.hide()
        # Inline forms belong below the builder, inside the same page scroll.
        self.inline_slot = QVBoxLayout()
        content_layout.addLayout(self.inline_slot)
        content_layout.addStretch()
        self.page_scroll.setWidget(content)
        page_layout.addWidget(self.page_scroll, 1)

        execution_layout = QHBoxLayout()
        execution_layout.setContentsMargins(4, 0, 4, 4)
        self.execution_bar = ExecutionBar(text_active_button="Run Pipeline", is_config=True)
        execution_layout.addWidget(self.execution_bar)
        page_layout.addLayout(execution_layout)
        self.execution_bar.execute_requested.connect(self.on_run_pipeline)
        self.execution_bar.save_outputs_requested.connect(self.on_save_outputs)

    def on_run_pipeline(self):
        if self.run_worker is not None or self.save_worker is not None:
            return
        if self.active_step_panel is not None or self.active_step_dialog is not None:
            self.show_run_error("Save or cancel the open step editor before running the pipeline.")
            return
        try:
            context = PipelineRunContext(self.pipeline_steps)
        except (OSError, TypeError, ValueError) as error:
            self.show_run_error(str(error))
            return
        # A new run owns new files; previous results survive until this point.
        self.cleanup_run_workspaces()
        self.run_context = context
        self.pending_run_result = None
        worker = FunctionWorker(run_pipeline, context, report_progress=True)
        worker.setParent(self)
        self.run_worker = worker
        worker.progress.connect(self.execution_bar.update_progress)
        worker.done.connect(self.on_run_done)
        worker.finished.connect(self.release_run_worker)
        self.window().installEventFilter(self)
        self.page_scroll.widget().setEnabled(False)
        self.execution_bar.reset()
        self.execution_bar.set_busy(True)
        worker.start()

    def on_run_done(self, result):
        # Wait for finished before opening a modal error dialog.
        self.pending_run_result = result

    def release_run_worker(self):
        worker = self.run_worker
        self.run_worker = None
        if worker is not None:
            worker.deleteLater()
        self.page_scroll.widget().setEnabled(True)
        self.execution_bar.set_busy(False)
        result = self.pending_run_result
        self.pending_run_result = None
        context = self.run_context
        self.run_context = None
        if result is context and context is not None and context.completed:
            self.last_run_context = context
            self.execution_bar.set_save_available(True)
            self.execution_bar.update_progress(100, f"Pipeline complete: {len(context.outputs)} outputs (temporary).")
        else:
            if context is not None:
                context.cleanup()
            message = str(result["error"]) if isinstance(result, dict) and "error" in result else "Pipeline returned an invalid result."
            self.show_run_error(message)

    def on_save_outputs(self):
        if self.run_worker is not None or self.save_worker is not None:
            return
        context = self.last_run_context
        if context is None or context.closed or not context.completed:
            self.execution_bar.set_save_available(False)
            return
        destination = QFileDialog.getExistingDirectory(self, "Save Outputs — choose a destination folder")
        if not destination:
            return  # Cancel keeps the successful run available for another attempt.
        worker = FunctionWorker(save_outputs, context, destination, report_progress=True)
        worker.setParent(self)
        self.save_worker = worker
        self.pending_save_result = None
        worker.progress.connect(self.execution_bar.update_progress)
        worker.done.connect(self.on_save_outputs_done)
        worker.finished.connect(self.release_save_worker)
        self.window().installEventFilter(self)
        self.page_scroll.widget().setEnabled(False)
        self.execution_bar.reset()
        self.execution_bar.update_progress(0, "Preparing output package…")
        self.execution_bar.set_busy(True)
        worker.start()

    def on_save_outputs_done(self, result):
        self.pending_save_result = result

    def release_save_worker(self):
        worker = self.save_worker
        self.save_worker = None
        if worker is not None:
            worker.deleteLater()
        self.page_scroll.widget().setEnabled(True)
        self.execution_bar.set_busy(False)
        result = self.pending_save_result
        self.pending_save_result = None
        if isinstance(result, Path) and result.is_dir():
            saved_files = sorted(path.name for path in result.iterdir())
            self.cleanup_run_workspaces()
            self.execution_bar.update_progress(100, f"Saved {len(saved_files) - 1} outputs + extract_config.yaml")
            QMessageBox.information(self, "Save Outputs", f"Saved package to:\n{result}\n\n" + "\n".join(saved_files))
        else:
            message = str(result["error"]) if isinstance(result, dict) and "error" in result else "Save Outputs returned an invalid result."
            # A failed save keeps the run and its enabled Save button for retry.
            self.show_run_error(message, "Save Outputs")

    def show_run_error(self, message, title="Run Pipeline"):
        self.execution_bar.status_label.setText(f"Status: {message}")
        QMessageBox.warning(self, title, message)

    def cleanup_run_workspaces(self):
        # App shutdown may bypass closeEvent; never remove files under a live worker.
        if self.run_worker is not None:
            self.run_worker.wait()
        if self.save_worker is not None:
            self.save_worker.wait()
        for context in (self.run_context, self.last_run_context):
            if context is not None:
                context.cleanup()
        self.last_run_context = None
        self.execution_bar.set_save_available(False)

    def build_pipeline_builder_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(svg_path("git-branch.svg"), size=ICON_SIZE))
        title_label = QLabel("Pipeline Builder")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        layout.addLayout(title_layout)
        layout.addLayout(self.build_template_row())
        layout.addLayout(self.build_technique_chip_row())
        layout.addWidget(self.build_canvas())
        layout.addLayout(self.build_step_ui_row())
        return card

    def build_template_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self.template_combo = QComboBox()
        # A placeholder is not a selectable template item.
        self.template_combo.setPlaceholderText("Select a Pipeline Example (Template)")
        row.addWidget(self.template_combo, 1)
        # TODO: Populate templates and connect their selection.
        # self.template_combo.currentIndexChanged.connect(self.on_template_selected)

        self.import_config_btn = QPushButton(" Import Config")
        self.export_config_btn = QPushButton(" Export Config")
        for button, icon_name in (
            (self.import_config_btn, "file-import.svg"),
            (self.export_config_btn, "file-export.svg"),
        ):
            button.setObjectName("SecondaryBtn")
            button.setProperty("textColor", "white")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(QIcon(create_icon_pixmap(svg_path(icon_name), "#FFFFFF", size=ICON_SIZE)))
            row.addWidget(button)

        # TODO: Connect config import/export when persistence is implemented.
        # self.import_config_btn.clicked.connect(self.on_import_config)
        # self.export_config_btn.clicked.connect(self.on_export_config)
        return row

    def build_technique_chip_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        for technique, meta in TECHNIQUE_DISPLAY.items():
            button = QPushButton(f" {meta['label']}")
            button.setObjectName("ChipBtn")
            button.setProperty("accentColor", meta["accent"])
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(QIcon(create_icon_pixmap(svg_path("plus.svg"), meta["hex"], size=CHIP_ICON_SIZE)))
            self.technique_buttons[technique] = button
            row.addWidget(button)
            # Bind each technique now so all three buttons keep their own value.
            button.clicked.connect(
                lambda checked=False, technique=technique: self.add_pipeline_step(technique)
            )

        row.addStretch()
        self.clear_pipeline_btn = QPushButton(" Clear")
        self.clear_pipeline_btn.setObjectName("ChipBtn")
        self.clear_pipeline_btn.setProperty("accentColor", "red")
        self.clear_pipeline_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_pipeline_btn.setIcon(QIcon(create_icon_pixmap(svg_path("trash.svg"), "#F43F5E", size=CHIP_ICON_SIZE)))
        row.addWidget(self.clear_pipeline_btn)
        self.clear_pipeline_btn.clicked.connect(self.confirm_clear_pipeline)
        return row

    def build_canvas(self) -> QFrame:
        self.pipeline_canvas = QFrame()
        self.pipeline_canvas.setObjectName("pipelineCanvas")
        self.pipeline_canvas.setFixedHeight(EMPTY_CANVAS_HEIGHT)
        self.canvas_layout = QVBoxLayout(self.pipeline_canvas)
        self.canvas_layout.setContentsMargins(CANVAS_MARGIN, CANVAS_MARGIN, CANVAS_MARGIN, CANVAS_MARGIN)
        self.canvas_layout.setSpacing(0)

        self.empty_canvas_label = QLabel("Add a technique above to create the first pipeline step.")
        self.empty_canvas_label.setObjectName("pipelineEmpty")
        self.empty_canvas_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_canvas_label.setWordWrap(True)
        self.canvas_layout.addWidget(self.empty_canvas_label)
        self.canvas_scroll = QScrollArea()
        self.canvas_scroll.setObjectName("pipelineCanvasScroll")
        self.canvas_scroll.setWidgetResizable(True)
        self.canvas_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.canvas_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.canvas_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.flow_container = StepCanvas(self.step_cards)
        self.flow_container.setObjectName("pipelineCanvasContent")
        self.flow_container.reorder_requested.connect(self.move_pipeline_step)
        self.flow_layout = FlowLayout(self.flow_container, margin=0, spacing=FLOW_SPACING)
        self.canvas_scroll.setWidget(self.flow_container)
        self.canvas_layout.addWidget(self.canvas_scroll)
        self.canvas_scroll.hide()
        # Reflow when the viewport changes, including when its scrollbar appears.
        self.canvas_scroll.viewport().installEventFilter(self)
        return self.pipeline_canvas

    def add_pipeline_step(self, technique: str):
        if self.run_worker is not None or self.save_worker is not None:
            return
        if technique not in TECHNIQUE_DISPLAY:
            raise ValueError(f"Unsupported technique: {technique}")
        key = uuid4().hex
        self.step_drafts[key] = PipelineStepDraft(key, technique, TECHNIQUE_DISPLAY[technique]["description"])
        card = StepCard(len(self.step_cards) + 1, technique, step_key=key)
        # Capture the card itself; displayed step numbers change after removal.
        card.remove_requested.connect(lambda card=card: self.remove_pipeline_step(card))
        card.clicked.connect(lambda card=card: self.open_step_configuration(card))
        self.step_cards.append(card)
        self.render_step_cards()

    @property
    def pipeline_steps(self) -> list[PipelineStepDraft]:
        """Read saved drafts in the current card order without a second ordered list."""
        return [self.step_drafts[card.step_key] for card in self.step_cards]

    def build_output_catalog(self, before_step_key: str) -> list[StepOutputInfo]:
        """Declare outputs using saved drafts and the latest card order."""
        return collect_output_catalog(self.pipeline_steps, before_step_key)

    def create_step_technique_form(self, card: StepCard) -> LSBInputForm | LocomotiveInputForm | MetadataInputForm:
        if card.technique == "metadata":
            inputs = MetadataInputForm(is_config=True)
        else:
            form_class = {"lsbpp": LSBInputForm, "locomotive": LocomotiveInputForm}[card.technique]
            inputs = form_class(key_registry=self.key_registry, is_config=True)
        draft = self.step_drafts[card.step_key].technique_inputs
        if isinstance(inputs, (LSBInputForm, LocomotiveInputForm, MetadataInputForm)):
            self.set_form_outputs(card.step_key, inputs)
        if draft is not None:
            inputs.load_draft(draft)
        return inputs

    def available_outputs_for_role(self, key: str, role: str):
        usage = build_output_usage(self.pipeline_steps)
        available = []
        for output in self.build_output_catalog(key):
            owners = usage.get(output.reference, [])
            # If invalid saved duplicates exist, the first owner can still edit its source.
            if not owners or owners[0] == (key, role):
                available.append(output)
        return available

    def set_form_outputs(self, key: str, inputs):
        if isinstance(inputs, LSBInputForm):
            inputs.set_available_outputs(self.available_outputs_for_role(key, "cover"))
        elif isinstance(inputs, LocomotiveInputForm):
            inputs.set_available_outputs(
                self.available_outputs_for_role(key, "covers"),
                self.available_outputs_for_role(key, "payload_files"),
            )
        elif isinstance(inputs, MetadataInputForm):
            inputs.set_available_outputs(
                self.available_outputs_for_role(key, "target"),
                self.available_outputs_for_role(key, "apic"),
            )

    def save_step_draft(self, key: str, description: str, guidenote: str, inputs: LSBInputForm | LocomotiveInputForm | MetadataInputForm) -> bool:
        if self.run_worker is not None or self.save_worker is not None:
            return False
        step = self.step_drafts.get(key)
        if step is None:
            return False
        if not description.strip():
            QMessageBox.warning(inputs, "Description Required", "Enter a description before saving this step.")
            return False
        if not inputs.validate_draft():
            return False
        try:
            draft = inputs.get_inputs()
            # Check fresh saved ownership before committing, including stale open forms.
            candidate_steps = deepcopy(self.pipeline_steps)
            for candidate in candidate_steps:
                if candidate.key == key:
                    candidate.technique_inputs = draft
            validate_output_usage(candidate_steps)
        except (OSError, TypeError, ValueError) as error:
            QMessageBox.warning(inputs, "Invalid Step Inputs", str(error))
            return False
        # Commit only after all checks pass; editing the form never mutates the saved draft.
        step.description = description.strip()
        step.guidenote = guidenote.strip()
        step.technique_inputs = draft
        self.refresh_pipeline_dependencies()
        self.render_step_cards()
        return True

    def refresh_pipeline_dependencies(self):
        """Run on committed changes, never as a side effect of rendering."""
        changes = reconcile_links(self.pipeline_steps)
        # Renumber the open picker after drag/save, even if no link was cleared.
        if self.active_step_panel is not None:
            inputs = self.active_step_panel.content_widget
            if isinstance(inputs, (LSBInputForm, LocomotiveInputForm, MetadataInputForm)):
                self.set_form_outputs(self.active_step_card.step_key, inputs)
        self.link_notice.setVisible(bool(changes))
        if not changes:
            self.link_notice.clear()
            return
        self.link_notice.setText(f"Cleared {len(changes)} unavailable linked input(s). Review the affected steps.")
        notice_details = []
        for change in changes:
            notice_details.append(f"{change.role}: {change.reason}")
        self.link_notice.setToolTip("\n".join(notice_details))
        self.update_open_form_links(changes)

    def update_open_form_links(self, changes):
        """Clear lost references in the open editor while retaining its other edits."""
        panel = self.active_step_panel
        if panel is None:
            return
        affected = []
        for change in changes:
            if change.step_key == self.active_step_card.step_key:
                affected.append(change)
        if not affected:
            return
        inputs = panel.content_widget
        if isinstance(inputs, MetadataInputForm):
            invalid_pictures = set()
            for change in affected:
                if change.role == "target":
                    # Target loss also clears unsaved edits belonging to that target.
                    inputs.reset_target()
                    break
                if change.role == "apic":
                    invalid_pictures.add(change.reference)
            if invalid_pictures:
                # A lost upstream cover may still have an expected output in the catalog.
                available_pictures = []
                for output in inputs.mp3_form.attached_picture_form.output_catalog:
                    if output.reference not in invalid_pictures:
                        available_pictures.append(output)
                inputs.mp3_form.attached_picture_form.set_available_outputs(available_pictures)
        elif isinstance(inputs, LSBInputForm):
            for change in affected:
                if inputs.cover_source == change.reference:
                    inputs.cover_source = None
                    inputs.output_picker.set_selection(None)
                    inputs.cover_mode_toggle.set_mode("Manual")
                    inputs.cover_source_stack.setCurrentWidget(inputs.cover_drop_zone)
                    inputs.capacity_request += 1
                    inputs.capacity_bits = None
                    inputs.isCalculating = False
                    inputs.update_capacity_label()
        elif isinstance(inputs, LocomotiveInputForm):
            invalid_covers = set()
            invalid_payload = set()
            for change in affected:
                if change.role == "covers":
                    invalid_covers.add(change.reference)
                elif change.role == "payload_files":
                    invalid_payload.add(change.reference)

            remaining_covers = []
            has_linked_cover = False
            for cover in inputs.locomotive_covers:
                if cover.source not in invalid_covers:
                    remaining_covers.append(cover)
                    if isinstance(cover.source, StepOutput):
                        has_linked_cover = True
            inputs.locomotive_covers[:] = remaining_covers

            remaining_files = []
            has_linked_payload = False
            for source in inputs.payload_files:
                if source not in invalid_payload:
                    remaining_files.append(source)
                    if isinstance(source, StepOutput):
                        has_linked_payload = True
            inputs.payload_files[:] = remaining_files

            if not has_linked_cover:
                inputs.cover_mode_toggle.set_mode("Manual")
                inputs.on_cover_mode_changed("Manual")
            if not has_linked_payload:
                inputs.payload_mode_toggle.set_mode("Manual")
                inputs.on_payload_source_mode_changed("Manual")
            inputs.update_cover_summary()
            inputs.update_payload_file_summary()

    def describe_source(self, source) -> str:
        if isinstance(source, str):
            return Path(source).name
        if isinstance(source, StepOutput):
            for number, step in enumerate(self.pipeline_steps, start=1):
                for output in declared_step_outputs(step, number):
                    if output.reference == source:
                        technique = TECHNIQUE_DISPLAY[step.technique]["label"]
                        output_name = output.display_name or "Output"
                        return f"From STEP {number} {technique}, {output_name}"
            return "Unavailable output"
        return "Not selected"

    def apply_step_draft_to_card(self, card: StepCard, status: tuple[str, str] | None = None):
        step = self.step_drafts[card.step_key]
        card.set_description(step.description)
        card.set_summary(cover="Not selected", payload="Not configured", output="Pending", encryption="Not configured")
        card.set_status(*(status or evaluate_pipeline_statuses(self.pipeline_steps)[step.key]))
        draft = step.technique_inputs
        if draft is None:
            return
        # Keep each technique's summary and tooltip logic together.
        if isinstance(draft, MetadataInputsDraft):
            self.update_metadata_card_summary(card, draft)
            return

        if not draft.encryption_enabled:
            encryption = "Off"
        elif draft.encryption_mode == "password":
            encryption = "Password"
        else:
            encryption = "Public Key"
        if isinstance(draft, LSBInputsDraft):
            self.update_lsb_card_summary(card, draft, encryption)
        elif isinstance(draft, LocomotiveInputsDraft):
            self.update_locomotive_card_summary(card, draft, encryption)

    def update_lsb_card_summary(self, card: StepCard, draft: LSBInputsDraft, encryption: str):
        """Show the message size and the cover's current source."""
        card.set_summary(
            cover=self.describe_source(draft.cover),
            payload=f"Text ({format_file_size(len(draft.payload_text.encode('utf-8')))})",
            output="PNG ×1" if draft.cover else "Pending", encryption=encryption,
        )

    def update_locomotive_card_summary(self, card: StepCard, draft: LocomotiveInputsDraft, encryption: str):
        """Keep source grouping, selected output counts and file details intact."""
        count = len(draft.covers)
        manual_count = 0
        producer_keys = set()
        cover_lines = [f"Cover PNGs ({count}):"]
        for number, item in enumerate(draft.covers, start=1):
            if isinstance(item.source, StepOutput):
                producer_keys.add(item.source.step_key)
            else:
                manual_count += 1
            cover_lines.append(f"{number}. {self.describe_source(item.source)}")

        if count == 0:
            cover = "Not selected"
        elif count == 1:
            cover = self.describe_source(draft.covers[0].source)
        elif manual_count == 0 and len(producer_keys) == 1:
            # Brackets mean selected output count, not an output's index.
            cover = f"PNGs ×{count}"
            source_key = draft.covers[0].source.step_key
            for number, producer in enumerate(self.pipeline_steps, start=1):
                if producer.key == source_key:
                    technique = TECHNIQUE_DISPLAY[producer.technique]["label"]
                    cover = f"From STEP {number} {technique}, Output [{count}]"
                    cover_lines.insert(1, cover)
                    break
        elif manual_count == 0:
            cover = f"From {len(producer_keys)} STEPs, PNG [{count}]"
        else:
            cover = f"PNGs ×{count}"
        payload_lines = []
        if draft.payload_mode == "text":
            payload = f"Text ({format_file_size(len(draft.payload_text.encode('utf-8')))})"
        else:
            size = 0
            linked_count = 0
            missing_file = False
            payload_lines.append(f"Payload files ({len(draft.payload_files)}):")
            for number, source in enumerate(draft.payload_files, start=1):
                if isinstance(source, StepOutput):
                    linked_count += 1
                    payload_lines.append(f"{number}. {self.describe_source(source)}")
                else:
                    file_size = "Unavailable"
                    try:
                        source_size = Path(source).stat().st_size
                        size += source_size
                        file_size = format_file_size(source_size)
                    except (OSError, TypeError):
                        missing_file = True
                    payload_lines.append(f"{number}. Manual: {self.describe_source(source)} — {file_size}")

            if missing_file:
                payload = f"Files ×{len(draft.payload_files)} (unavailable)"
            elif linked_count:
                payload = f"Files ×{len(draft.payload_files)} · Linked ×{linked_count}"
            else:
                payload = f"Files ×{len(draft.payload_files)} ({format_file_size(size)})"
        card.set_summary(cover=cover, payload=payload, output=f"PNG ×{count}" if count else "Pending", encryption=encryption)
        if count > 1:
            card.summary_labels["cover"].setToolTip("\n".join(cover_lines))
        if draft.payload_mode == "files":
            card.summary_labels["payload"].setToolTip("\n".join(payload_lines))


    def update_metadata_card_summary(self, card: StepCard, draft: MetadataInputsDraft):
        """Show PNG keys or MP3 frame instances and APIC source/type/description."""
        if isinstance(draft.payload, PNGMetadataDraft):
            count = len(draft.payload.entries)
            card.set_summary(
                cover=self.describe_source(draft.cover),
                payload=f"Text fields ×{count}", output="PNG ×1" if draft.cover else "Pending", encryption="None",
            )
            card.summary_labels["payload"].setToolTip(
                "\n".join([f"PNG metadata fields ({count}):", *draft.payload.entries])
            )
        elif isinstance(draft.payload, MP3MetadataDraft):
            frames = draft.payload.text_frames.frames
            frame_count = 0
            frame_lines = []
            for number, frame in enumerate(frames, start=1):
                name = FRAME_INFO.get(frame.frame_id, ("Unknown frame", ""))[0]
                if isinstance(frame, MP3ComplexFrameDraft):
                    instance_count = len(frame.instances)
                    frame_count += instance_count
                    frame_lines.append(f"{number}. {frame.frame_id} ×{instance_count} — {name}")
                else:
                    frame_count += 1
                    frame_lines.append(f"{number}. {frame.frame_id} — {name}")
            pictures = draft.payload.attached_pictures
            picture_count = len(pictures)
            if frame_count and picture_count:
                summary = f"Text ×{frame_count} + APIC ×{picture_count}"
            elif picture_count:
                summary = f"APIC images ×{picture_count}"
            else:
                summary = f"Text frames ×{frame_count}"
            card.set_summary(
                cover=self.describe_source(draft.cover),
                payload=summary, output="MP3 ×1" if draft.cover else "Pending", encryption="None",
            )
            lines = [f"Text frames ({frame_count}):"]
            lines.extend(frame_lines)
            lines.append(f"\nAPIC images ({picture_count}):")
            for number, picture in enumerate(pictures, start=1):
                if picture.source is not None:
                    source_name = self.describe_source(picture.source)
                elif picture.source_name:
                    source_name = Path(picture.source_name).name
                else:
                    source_name = "Existing image in target MP3"
                type_name = APIC_TYPES.get(picture.picture_type, "Unknown picture type")
                description = picture.description or "(empty)"
                lines.append(f"{number}. {source_name}")
                lines.append(f"   Type {picture.picture_type} — {type_name}")
                lines.append(f"   Description: {description}")
            card.summary_labels["payload"].setToolTip("\n".join(lines))

    def open_step_configuration(self, card: StepCard):
        if self.run_worker is not None or self.save_worker is not None or card not in self.step_cards:
            return
        if self.btn_popup.isChecked():
            self.open_step_config_popup(card)
        else:
            self.open_step_config_inline(card)

    def open_step_config_popup(self, card: StepCard):
        if self.active_step_dialog is not None:
            return
        self.close_step_config_inline()
        inputs = self.create_step_technique_form(card)
        step = self.step_drafts[card.step_key]
        dialog = StepConfigShellDialog(
            card.step_number, card.meta["label"], inputs, parent=self,
            description=step.description, guidenote=step.guidenote, accent=card.meta["accent"],
            save_callback=lambda description, note: self.save_step_draft(card.step_key, description, note, inputs),
        )
        self.active_step_dialog = dialog
        try:
            dialog.exec()
        finally:
            self.active_step_dialog = None
            self.release_step_config_shell(dialog, inputs)

    def open_step_config_inline(self, card: StepCard):
        if self.active_step_dialog is not None:
            return
        if self.active_step_card is card:
            self.reveal_inline_panel()
            return
        # Switching cards discards unsaved edits; the committed draft remains intact.
        self.close_step_config_inline()
        inputs = self.create_step_technique_form(card)
        step = self.step_drafts[card.step_key]
        panel = StepConfigShellPanel(
            card.step_number, card.meta["label"], inputs,
            description=step.description, guidenote=step.guidenote, accent=card.meta["accent"],
            save_callback=lambda description, note: self.save_step_draft(card.step_key, description, note, inputs),
        )
        self.active_step_card = card
        self.active_step_panel = panel
        self.inline_slot.addWidget(panel)
        panel.close_requested.connect(self.close_step_config_inline)
        panel.saved.connect(self.close_step_config_inline)
        panel.show()
        QTimer.singleShot(0, self.reveal_inline_panel)

    def reveal_inline_panel(self):
        if self.active_step_panel is not None:
            # Bring the form itself into view, even if its header was visible.
            self.page_scroll.verticalScrollBar().setValue(self.active_step_panel.y())

    def close_step_config_inline(self):
        panel = self.active_step_panel
        if panel is None:
            return
        self.active_step_panel = None
        self.active_step_card = None
        self.inline_slot.removeWidget(panel)
        panel.hide()
        self.release_step_config_shell(panel, panel.content_widget)

    def set_config_variant(self, mode: str):
        if mode == "popup":
            self.close_step_config_inline()

    def release_step_config_shell(self, host: QWidget, inputs: LSBInputForm | LocomotiveInputForm | MetadataInputForm):
        # Closing discards inputs, but capacity workers must finish before deletion.
        released = False

        def release_when_idle():
            nonlocal released
            if not released and not getattr(inputs, "capacity_workers", {}):
                released = True
                host.deleteLater()

        for worker in tuple(getattr(inputs, "capacity_workers", {}).values()):
            worker.finished.connect(release_when_idle)
        # Also handle workers whose finished signal was already queued on close.
        QTimer.singleShot(0, release_when_idle)

    def remove_pipeline_step(self, card: StepCard):
        if self.run_worker is not None or self.save_worker is not None or card not in self.step_cards:
            return
        if card is self.active_step_card:
            self.close_step_config_inline()
        self.step_cards.remove(card)
        self.step_drafts.pop(card.step_key)
        self.refresh_pipeline_dependencies()
        self.render_step_cards()
        card.deleteLater()

    def confirm_clear_pipeline(self):
        if self.run_worker is not None or self.save_worker is not None or not self.step_cards:
            return
        count = len(self.step_cards)
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Clear Pipeline")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(f"Clear all {count} {'step' if count == 1 else 'steps'}?")
        dialog.setInformativeText("This removes every step from the pipeline.")
        clear_button = dialog.addButton("Clear", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(cancel_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec()
        confirmed = dialog.clickedButton() == clear_button
        dialog.deleteLater()
        if confirmed:
            self.clear_pipeline()

    def clear_pipeline(self):
        if self.run_worker is not None or self.save_worker is not None:
            return
        self.close_step_config_inline()
        removed_cards = list(self.step_cards)
        # Keep the same list object: StepCanvas also references this collection.
        self.step_cards.clear()
        self.step_drafts.clear()
        self.link_notice.clear()
        self.link_notice.hide()
        self.flow_container.drop_indicator.hide()
        self.render_step_cards()
        for card in removed_cards:
            card.deleteLater()

    def move_pipeline_step(self, card: StepCard, insertion_index: int):
        if self.run_worker is not None or self.save_worker is not None or card not in self.step_cards or not 0 <= insertion_index <= len(self.step_cards):
            return
        source_index = self.step_cards.index(card)
        # The drop slot belongs to the original list, before removing the source.
        if source_index < insertion_index:
            insertion_index -= 1
        if source_index == insertion_index:
            return
        self.step_cards.pop(source_index)
        self.step_cards.insert(insertion_index, card)
        self.refresh_pipeline_dependencies()
        self.render_step_cards()

    def render_step_cards(self):
        #ล้าง layout แต่เก็บ StepCard เดิมไว้ เพื่อไม่ให้ข้อมูลภายในหาย
        #ส่วนลูกศรลบทิ้งและสร้างใหม่ตอนจัดเรียง
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                if not isinstance(widget, StepCard): # ลูกศรจะถูกลบ
                    widget.deleteLater()

        statuses = evaluate_pipeline_statuses(self.pipeline_steps)
        for number, card in enumerate(self.step_cards, start=1):
            card.set_step_number(number)
            self.apply_step_draft_to_card(card, statuses[card.step_key])
            if number > 1:
                self.flow_layout.addWidget(make_arrow())
            self.flow_layout.addWidget(card)
            card.show()

        if self.active_step_panel is not None:
            self.active_step_panel.set_step_number(self.active_step_card.step_number)

        has_steps = bool(self.step_cards)
        self.empty_canvas_label.setVisible(not has_steps)
        self.canvas_scroll.setVisible(has_steps)
        self.refresh_canvas_height()
        QTimer.singleShot(0, self.refresh_canvas_height)

    def eventFilter(self, watched, event):
        if watched is self.window() and event.type() == QEvent.Type.Close:
            if self.run_worker is not None or self.save_worker is not None:
                event.ignore()
                self.execution_bar.status_label.setText("Status: Wait for the current operation to finish before closing.")
                return True
            self.cleanup_run_workspaces()
        if watched is self.canvas_scroll.viewport() and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self.refresh_canvas_height)
        return super().eventFilter(watched, event)

    def refresh_canvas_height(self):
        if not self.step_cards:
            self.flow_container.setMinimumHeight(0)
            self.canvas_scroll.setFixedHeight(CARD_HEIGHT)
            self.canvas_scroll.verticalScrollBar().setValue(0)
            self.pipeline_canvas.setFixedHeight(EMPTY_CANVAS_HEIGHT)
            self.pipeline_builder_card.updateGeometry()
            return
        width = self.canvas_scroll.viewport().width()
        if width <= 0:
            return
        required_height = max(CARD_HEIGHT, self.flow_layout.heightForWidth(width))
        self.flow_container.setMinimumHeight(required_height)
        # Like the reference, show up to two rows and scroll additional rows.
        visible_height = min(required_height, MAX_VISIBLE_FLOW_HEIGHT)
        self.canvas_scroll.setFixedHeight(visible_height)
        self.pipeline_canvas.setFixedHeight(visible_height + CANVAS_MARGIN * 2)
        self.pipeline_builder_card.updateGeometry()

    def build_step_ui_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel("STEP CONFIG UI:")
        label.setObjectName("stepConfigUI")
        row.addWidget(label)

        # Opening a card reads this selection; switching to Popup closes Inline.
        self.config_variant_group = QButtonGroup(self)
        self.config_variant_group.setExclusive(True)
        self.btn_popup = QPushButton(" Popup Dialog")
        self.btn_inline = QPushButton(" Inline Panel")
        for button, value in ((self.btn_popup, "popup"), (self.btn_inline, "inline")):
            button.setObjectName("stepUiBtn")
            button.setProperty("value", value)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.config_variant_group.addButton(button)
            row.addWidget(button)
        self.btn_popup.setChecked(True)
        row.addStretch()
        self.btn_popup.clicked.connect(lambda: self.set_config_variant("popup"))
        self.btn_inline.clicked.connect(lambda: self.set_config_variant("inline"))
        return row
