

from copy import deepcopy
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
from uuid import uuid4

from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget)

from PyQt6.QtCore import QEvent, QIODevice, QSaveFile, QTimer, Qt
from PyQt6.QtGui import QIcon

from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap
from src.gui.components.widgets.execution_bar import ExecutionBar
from src.core.configurable.drafts import StepDraft
from src.core.configurable.config_file import ConfigError, export_pipeline, import_pipeline, pipeline_label, read_document
from src.core.configurable.extract_plan import PLAN_FILE_NAME, PipelineRun, run_with_plan
from src.core.configurable.link import dependents, link_labels, output_choices
from src.core.configurable.runner import (
    StepOutputFile, check_steps, final_files, final_outputs, save_outputs, step_status,
)
from src.gui.features.embed.configurable.constants import TECHNIQUE_DISPLAY
from src.gui.features.embed.configurable.widgets.flow_layout import FlowLayout
from src.gui.features.embed.configurable.widgets.export_config_dialog import ExportConfigDialog
from src.gui.features.embed.configurable.widgets.template_combo import TemplateComboBox
from src.gui.features.embed.configurable.widgets.output_files_card import OutputFilesCard
from src.gui.features.embed.configurable.widgets.step_canvas import StepCanvas
from src.gui.features.embed.configurable.widgets.step_card import CARD_HEIGHT, StepCard, make_arrow
from src.gui.features.embed.forms.locomotive_form import LocomotiveInputForm
from src.gui.features.embed.forms.lsb_form import LSBInputForm
from src.gui.features.embed.forms.metadata_form import MetadataInputForm
from src.gui.features.embed.configurable.widgets.step_config_shell import StepConfigShellDialog, StepConfigShellPanel
from src.gui.services.key_registry import KeyRegistry
from src.gui.services.worker import FunctionWorker
from src.path import TEMPLATES_DIR, svg_path

ICON_SIZE = 16
CHIP_ICON_SIZE = 12
CANVAS_MARGIN = 16
EMPTY_CANVAS_HEIGHT = 192
FLOW_SPACING = 8
MAX_VISIBLE_FLOW_HEIGHT = CARD_HEIGHT * 2 + FLOW_SPACING

class EmbedConfigurablePage(QFrame):
    
    def __init__(self, key_registry: KeyRegistry | None = None, parent=None):
        super().__init__(parent)
        self.key_registry = key_registry
        self.technique_buttons: dict[str, QPushButton] = {}
        
        self.step_cards: list[StepCard] = []
        self.step_drafts: dict[str, StepDraft] = {}
        self.pipeline_name: str = ""
        self.templates_dir = TEMPLATES_DIR

        # Step editor that is open now (popup dialog or inline panel); None when closed
        self.active_step_dialog: StepConfigShellDialog = None
        self.active_step_panel: StepConfigShellPanel = None
        self.active_step_card: StepCard = None

        # Run state: outputs stay as files in run_workspace until the user presses Save Outputs
        self.run_worker: FunctionWorker | None = None
        self.run_result = None  # handed from worker.done to worker.finished
        self.run_workspace: TemporaryDirectory | None = None
        self.run_outputs: list[StepOutputFile] = []
        self.run_plan_path: Path | None = None  # extract_pipeline.yaml of the last run (saved with the outputs)

        self.setup_ui()
        QApplication.instance().aboutToQuit.connect(self.discard_run)  # remove the temp files on exit
        
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
        
        # --- Pipeline builder Card --- 
        self.pipeline_builder_card = self.build_pipeline_builder_card()
        content_layout.addWidget(self.pipeline_builder_card)
        self.link_notice = QLabel()
        self.link_notice.setObjectName("hintLabel")
        self.link_notice.setWordWrap(True)
        content_layout.addWidget(self.link_notice)
        self.link_notice.hide()
        
        # --- Inline Panel ---
        # Inline forms belong below the builder, inside the same page scroll.
        self.inline_slot = QVBoxLayout()
        content_layout.addLayout(self.inline_slot)

        # --- Output Files Card: the files Save Outputs will save (hidden until a run finishes) ---
        self.output_files_card = OutputFilesCard()
        self.output_files_card.clear_requested.connect(self.on_clear_outputs)
        content_layout.addWidget(self.output_files_card)
        content_layout.addStretch()
        self.page_scroll.setWidget(content)
        page_layout.addWidget(self.page_scroll, 1)
        
        # --- Execute Bar ---
        execution_layout = QHBoxLayout()
        execution_layout.setContentsMargins(4, 0, 4, 4)
        self.execution_bar = ExecutionBar(text_active_button="Run Pipeline", is_config=True)
        execution_layout.addWidget(self.execution_bar)
        page_layout.addLayout(execution_layout)
        self.execution_bar.execute_requested.connect(self.on_run_pipeline)
        self.execution_bar.save_outputs_requested.connect(self.on_save_outputs)
        
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
        self.template_combo = TemplateComboBox()
        # A placeholder is not a selectable template item.
        self.template_combo.setPlaceholderText("Select a Pipeline Example (Template)")
        row.addWidget(self.template_combo, 1)
        self.template_combo.popup_opening.connect(self.refresh_templates)
        self.template_combo.activated.connect(self.on_template_selected)
        self.refresh_templates()

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

        self.import_config_btn.clicked.connect(self.on_import_config)
        self.export_config_btn.clicked.connect(self.on_export_config)
        self.export_config_btn.setEnabled(False)
        return row

    # --- Config files ---
    def refresh_templates(self):
        self.template_combo.clear()
        paths = sorted(path for path in self.templates_dir.glob("*")
                       if path.is_file() and path.suffix.lower() in {".yaml", ".yml"})
        for path in paths:
            try:
                label = pipeline_label(read_document(path.read_text(encoding="utf-8-sig")))
            except (OSError, ValueError):
                self.template_combo.addItem(f"{path.name} (cannot read)", str(path))
                self.template_combo.model().item(self.template_combo.count() - 1).setEnabled(False)
                continue
            self.template_combo.addItem(label, str(path))
            self.template_combo.setItemData(self.template_combo.count() - 1,
                                            f"{label}\n{path.name}", Qt.ItemDataRole.ToolTipRole)
        self.template_combo.setCurrentIndex(-1)

    def on_template_selected(self, index: int):
        path = self.template_combo.itemData(index)
        self.template_combo.setCurrentIndex(-1)
        if path is not None:
            self.import_config_file(Path(path))

    def on_import_config(self):
        if self.run_worker is not None or self.active_step_dialog is not None:
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Import Config", "", "YAML files (*.yaml *.yml)")
        if not filename:
            return
        self.import_config_file(Path(filename))

    def import_config_file(self, path: Path):
        if self.run_worker is not None or self.active_step_dialog is not None:
            return
        # Read and validate before closing an editor or touching the current pipeline/results.
        try:
            imported = import_pipeline(path.read_text(encoding="utf-8-sig"), path.parent)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Cannot Import Config", str(error))
            return
        if self.step_cards and not self.ask_clear_pipeline("Import Config", "Import"):
            return
        self.clear_pipeline()
        self.pipeline_name = imported.name
        for step in imported.steps:
            self.add_step_card(step)
        self.render_step_cards()
        self.execution_bar.reset()
        self.execution_bar.set_status(f"Imported {len(imported.steps)} step(s) from {path.name}")

    def ask_export_path(self, name: str) -> str | None:
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(". ") or "embed_pipeline"
        dialog = QFileDialog(self, "Export Config", f"{stem}.yaml", "YAML files (*.yaml *.yml)")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDefaultSuffix("yaml")
        try:
            return dialog.selectedFiles()[0] if dialog.exec() == QDialog.DialogCode.Accepted else None
        finally:
            dialog.deleteLater()

    def on_export_config(self):
        if not self.step_cards or self.run_worker is not None or self.active_step_dialog is not None:
            return
        dialog = ExportConfigDialog(self.pipeline_name, self)
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            name = dialog.name_edit.text().strip()
            include_secret = dialog.include_secret.isChecked()
            include_passwords = dialog.include_passwords.isChecked()
        finally:
            dialog.deleteLater()
        filename = self.ask_export_path(name)
        if not filename:
            return
        path = Path(filename)
        try:
            # Only saved drafts are used; the open inline editor is not committed by Export.
            text = export_pipeline(self.pipeline_steps(), name=name, include_secret=include_secret,
                                   include_passwords=include_passwords, base_dir=path.parent)
            data = text.encode("utf-8")
            output = QSaveFile(str(path))
            if not output.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(output.errorString())
            if output.write(data) != len(data):
                output.cancelWriting()
                raise OSError(output.errorString())
            if not output.commit():
                raise OSError(output.errorString())
        except (OSError, ConfigError) as error:
            QMessageBox.warning(self, "Cannot Export Config", str(error))
            return
        self.pipeline_name = name
        self.execution_bar.set_status(f"Exported config to {path}")
    
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
            button.clicked.connect(lambda checked=False, technique=technique: self.add_pipeline_step(technique))

        row.addStretch()
        self.clear_pipeline_btn = QPushButton(" Clear")
        self.clear_pipeline_btn.setObjectName("ChipBtn")
        self.clear_pipeline_btn.setProperty("accentColor", "red")
        self.clear_pipeline_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_pipeline_btn.setIcon(QIcon(create_icon_pixmap(svg_path("trash.svg"), "#F43F5E", size=CHIP_ICON_SIZE)))
        self.clear_pipeline_btn.setEnabled(False)  # enabled by render_step_cards() once there is a step
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
        
        # scroll bar hiding and shown if needed
        self.canvas_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.canvas_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.flow_container = StepCanvas(self.step_cards)  # receives the dragged cards (same list as the page: do not replace it)
        self.flow_container.setObjectName("pipelineCanvasContent")
        self.flow_container.reorder_requested.connect(self.move_pipeline_step)
        self.flow_layout = FlowLayout(self.flow_container, margin=0, spacing=FLOW_SPACING)
        self.canvas_scroll.setWidget(self.flow_container)
        self.canvas_layout.addWidget(self.canvas_scroll)
        self.canvas_scroll.hide()
        # Reflow when the viewport changes, including when its scrollbar appears.
        self.canvas_scroll.viewport().installEventFilter(self)
        return self.pipeline_canvas
    
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
    
    # --- Step Canvas Render ---
    def eventFilter(self, watched, event):
        # Cards wrap to more/fewer rows when the viewport is resized, so the canvas height must follow.
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
        visible_height = min(required_height, MAX_VISIBLE_FLOW_HEIGHT)
        self.canvas_scroll.setFixedHeight(visible_height)
        self.pipeline_canvas.setFixedHeight(visible_height + CANVAS_MARGIN * 2)
        self.pipeline_builder_card.updateGeometry()
    
    def render_step_cards(self):
        #ล้าง layout แต่เก็บ StepCard เดิมไว้ เพื่อไม่ให้ข้อมูลภายในหาย
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                if not isinstance(widget, StepCard): # ส่วนลูกศรลบทิ้งและสร้างใหม่ตอนจัดเรียง
                    widget.deleteLater()

        for number, card in enumerate(self.step_cards, start=1):
            card.set_step_number(number)
            self.apply_step_draft_to_card(card)
            if number > 1:
                self.flow_layout.addWidget(make_arrow())
            self.flow_layout.addWidget(card)
            card.show()


        has_steps = bool(self.step_cards)
        self.empty_canvas_label.setVisible(not has_steps) # ถ้าบ่มีหยัง กะบ่มีหยังนั้นล่ะ
        self.canvas_scroll.setVisible(has_steps)
        self.clear_pipeline_btn.setEnabled(has_steps)
        self.export_config_btn.setEnabled(has_steps)
        self.refresh_canvas_height()
        QTimer.singleShot(0, self.refresh_canvas_height)

        # The pipeline changed (add/remove/save/clear) -> the last run's outputs no longer match
        self.discard_run()

    # --- Step Card Summary ---
    def apply_step_draft_to_card(self, card: StepCard):
        """Show the saved step on its card: description, summary rows and status badge."""
        step = self.step_drafts[card.step_key]
        draft = step.technique_inputs

        card.set_description(step.description)
        card.set_inputs(draft, link_labels(self.pipeline_steps(), draft))  # the card knows how to show each technique's inputs
        card.set_pending(step.pending)
        state, detail = step_status(step, self.pipeline_steps())  # same rules as Run Pipeline (core)
        if step.pending:
            detail = "\n".join(step.pending) if state == "setup" else "\n".join([detail, *step.pending])
        card.set_status(state, detail)

    # --- Pipeline Step Controller ---
    def add_pipeline_step(self, technique: str):
        if technique not in TECHNIQUE_DISPLAY:
            raise ValueError(f"Unsupported technique: {technique}")
        key = uuid4().hex
        self.add_step_card(StepDraft(key, technique, TECHNIQUE_DISPLAY[technique]["description"]))
        self.render_step_cards()

    def add_step_card(self, step: StepDraft):
        self.step_drafts[step.key] = step
        card = StepCard(len(self.step_cards) + 1, step.technique, step_key=step.key)
        
        # Add ability to remove and open to step card
        card.remove_requested.connect(lambda card=card: self.remove_pipeline_step(card))
        card.clicked.connect(lambda card=card: self.open_step_configuration(card))
        
        self.step_cards.append(card)
        
    def confirm_remove_step(self, users: list[int]) -> bool:
        """Ask before removing a step whose outputs other steps use (they become BLOCKED)."""
        if len(users) == 1:
            text = f"Step {users[0]} uses this step's output; it will become BLOCKED."
        else:
            text = f"Steps {', '.join(str(number) for number in users)} use this step's output; they will become BLOCKED."
        answer = QMessageBox.question(
            self, "Remove Step", f"{text}\nRemove anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def remove_pipeline_step(self, card: StepCard):
        users = dependents(self.pipeline_steps(), card.step_key)
        if users and not self.confirm_remove_step(users):
            return
        if card is self.active_step_card:
            self.close_step_config_inline()  # do not leave an editor open for a removed step
        self.step_cards.remove(card)
        self.step_drafts.pop(card.step_key)
        self.render_step_cards()
        card.deleteLater()
    
    def move_pipeline_step(self, card: StepCard, insertion_index: int):
        """A card was dropped before position insertion_index of the cards as they were before the move."""
        if self.run_worker is not None or card not in self.step_cards or not 0 <= insertion_index <= len(self.step_cards):
            return
        source = self.step_cards.index(card)
        if source < insertion_index:
            insertion_index -= 1  # the card leaves its place first, so the later positions move up
        if source == insertion_index:
            return  # dropped where it was

        # An open inline editor shows the old order (its Previous Output list depends on it): close it like a click on another card
        self.close_step_config_inline()
        self.step_cards.insert(insertion_index, self.step_cards.pop(source))  # the same list object (StepCanvas holds it)
        self.render_step_cards()  # numbers, arrows, badges (BLOCKED / READY follow the new order) and the run results

    def confirm_clear_pipeline(self):
        if self.step_cards and self.ask_clear_pipeline():
            self.clear_pipeline()

    def ask_clear_pipeline(self, title: str = "Clear Pipeline", action: str = "Clear") -> bool:
        if not self.step_cards:
            return True
        count = len(self.step_cards)
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(f"Replace the current pipeline ({count} steps)?" if action == "Import"
                       else f"Clear all {count} {'step' if count == 1 else 'steps'}?")
        dialog.setInformativeText("This removes every step from the pipeline.")
        clear_button = dialog.addButton(action, QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(cancel_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec()
        confirmed = dialog.clickedButton() == clear_button
        dialog.deleteLater()
        return confirmed

    def clear_pipeline(self):
        self.close_step_config_inline()
        removed_cards = list(self.step_cards)
        # Keep the same list object (StepCanvas holds it).
        self.flow_container.drop_indicator.hide()
        self.step_cards.clear()
        self.step_drafts.clear()
        self.pipeline_name = ""
        self.link_notice.clear()
        self.link_notice.hide()
        self.render_step_cards()
        for card in removed_cards:
            card.deleteLater()
            
    # --- Open Step Card Configuration ---
    def create_step_technique_form(self, card: StepCard) -> LSBInputForm | LocomotiveInputForm | MetadataInputForm:
        if card.technique == "metadata":
            inputs_form = MetadataInputForm(is_config=True)  # Metadata ไม่มีการเข้ารหัส จึงไม่ใช้ key_registry
        else:
            form_class = {
                "lsbpp": LSBInputForm,
                "locomotive": LocomotiveInputForm
                }[card.technique]

            inputs_form = form_class(key_registry=self.key_registry, is_config=True)
        # Previous Output list first: load_draft looks the saved output up in it
        steps = self.pipeline_steps()
        if card.technique == "metadata":
            # 2 lists: the target (PNG without a Metadata layer) and the MP3 pictures (any free PNG)
            inputs_form.set_output_choices(output_choices(steps, card.step_key),
                                           output_choices(steps, card.step_key, picture=True))
        else:
            inputs_form.set_output_choices(output_choices(steps, card.step_key))

        draft = self.step_drafts[card.step_key].technique_inputs
        if draft is not None:
            inputs_form.load_draft(draft)
        return inputs_form
            
    def open_step_configuration(self, card: StepCard):
        if self.btn_popup.isChecked():
            self.open_step_config_popup(card)
        else:
            self.open_step_config_inline(card)
            
    def editor_args(self, card: StepCard, inputs_form) -> dict:
        """Arguments shared by the popup dialog and the inline panel (one place, so both always get the same)."""
        step = self.step_drafts[card.step_key]
        return dict(
            step_number=card.step_number, technique_label=card.meta["label"], content_widget=inputs_form,
            description=step.description, guidenote=step.guidenote, accent=card.meta["accent"],
            save_callback=lambda description, note: self.save_step_draft(card.step_key, description, note, inputs_form),
        )

    def open_step_config_popup(self, card: StepCard):
        self.close_step_config_inline()
        inputs_form = self.create_step_technique_form(card)
        dialog = StepConfigShellDialog(**self.editor_args(card, inputs_form), parent=self)
        self.active_step_dialog = dialog
        try:
            dialog.exec()
        finally:
            self.active_step_dialog = None
            self.release_step_config_shell(dialog, inputs_form)

    def open_step_config_inline(self, card: StepCard):
        if self.active_step_dialog is not None:
            return
        if self.active_step_card is card:
            self.reveal_inline_panel()
            return
        # Switching cards discards unsaved edits; the committed draft remains intact.
        self.close_step_config_inline()
        inputs_form = self.create_step_technique_form(card)
        panel = StepConfigShellPanel(**self.editor_args(card, inputs_form))
        self.active_step_card = card
        self.active_step_panel = panel
        self.inline_slot.addWidget(panel)
        panel.close_requested.connect(self.close_step_config_inline)
        panel.saved.connect(self.close_step_config_inline)
        panel.show()
        QTimer.singleShot(0, self.reveal_inline_panel)

    def save_step_draft(self, key: str, description: str, guidenote: str, inputs: LSBInputForm | LocomotiveInputForm | MetadataInputForm) -> bool:
        # 1. The step was removed while its editor was still open
        step = self.step_drafts.get(key)
        if step is None:
            return False

        # 2. Description is required
        if not description.strip():
            QMessageBox.warning(inputs, "Description Required", "Enter a description before saving this step.")
            return False

        # 3. Read the form (the form validates itself and raises ValueError when the inputs cannot be used)
        try:
            draft = inputs.get_inputs()
        except ValueError as error:
            QMessageBox.warning(inputs, "Invalid Step Inputs", str(error))
            return False

        # 4. All checks passed -> commit
        step.description = description.strip()
        step.guidenote = guidenote.strip()
        step.technique_inputs = draft
        step.pending.clear()

        # 5. Show the new description/status on the card
        self.render_step_cards()
        return True

    def reveal_inline_panel(self):
        if self.active_step_panel is not None:
            # Bring the form itself into view, even if its header was visible.
            self.page_scroll.verticalScrollBar().setValue(self.active_step_panel.y())
    
    def release_step_config_shell(self, host: QWidget, inputs: LSBInputForm | LocomotiveInputForm | MetadataInputForm):
        # Closing discards inputs, but capacity workers must finish before deletion.
        released = False

        def release_when_idle():
            nonlocal released
            if not released and not getattr(inputs, "capacity_workers", {}):
                released = True
                host.deleteLater()

        # A worker still running now: check again when it finishes (connected after the form's own
        # finished handler, so by then the worker has already been removed from capacity_workers)
        for worker in tuple(getattr(inputs, "capacity_workers", {}).values()):
            worker.finished.connect(release_when_idle)
        QTimer.singleShot(0, release_when_idle)
            
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

    # --- Run Pipeline ---
    def pipeline_steps(self) -> list[StepDraft]:
        """Saved steps in card order."""
        return [self.step_drafts[card.step_key] for card in self.step_cards]

    def on_run_pipeline(self):
        if self.run_worker is not None:
            return

        # 1. Checks before running
        if self.active_step_dialog is not None or self.active_step_panel is not None:
            self.show_run_error("Save or cancel the open step editor before running the pipeline.")
            return
        steps = deepcopy(self.pipeline_steps())  # snapshot: the run never sees later edits
        try:
            check_steps(steps)
        except ValueError as error:
            self.show_run_error(str(error))
            return

        # 2. New temp folder for this run (the previous run's files are removed)
        self.discard_run()
        self.run_workspace = TemporaryDirectory(prefix="SIENG2-pipeline-")

        # 3. Run in a worker and lock the page while it runs
        worker = FunctionWorker(run_with_plan, steps, Path(self.run_workspace.name), self.pipeline_name, report_progress=True)
        self.run_worker = worker
        worker.progress.connect(self.execution_bar.update_progress)
        worker.done.connect(self.on_run_done)
        worker.finished.connect(self.release_run_worker)

        self.page_scroll.widget().setEnabled(False)
        self.execution_bar.reset()
        self.execution_bar.set_busy(True)
        worker.start()

    def on_run_done(self, result):
        self.run_result = result

    def release_run_worker(self):
        result = self.run_result
        self.run_result = None
        self.run_worker.deleteLater()
        self.run_worker = None

        # restore UI state
        self.page_scroll.widget().setEnabled(True)
        self.execution_bar.set_busy(False)

        # success: output files + the extract plan waiting in the temp folder
        if isinstance(result, PipelineRun):
            self.run_outputs = result.outputs
            self.run_plan_path = result.plan_path
            self.execution_bar.set_save_available(True)
            self.execution_bar.update_progress(
                100, f"Pipeline complete: {len(final_outputs(result.outputs))} output(s), not saved yet.")
            self.output_files_card.show_files(final_files(result.outputs) + [(PLAN_FILE_NAME, result.plan_path)])
            QTimer.singleShot(0, lambda: self.page_scroll.ensureWidgetVisible(self.output_files_card))  # after the layout is updated
            return

        # failure: nothing half-done is kept
        self.discard_run()
        if isinstance(result, dict) and "error" in result:
            self.show_run_error(result["error"])
        else:
            self.show_run_error("Pipeline returned an invalid result.")

    def on_save_outputs(self):
        if not self.run_outputs:
            return
        directory = QFileDialog.getExistingDirectory(self, "Save Outputs")
        if not directory:
            return
        try:
            folder = save_outputs(self.run_outputs, Path(directory))
            if self.run_plan_path is not None:  # the receiver needs it with the final files
                shutil.copyfile(self.run_plan_path, folder / PLAN_FILE_NAME)
        except OSError as error:
            self.show_run_error(f"Could not save outputs: {error}")
            return
        plan = f" and {PLAN_FILE_NAME}" if self.run_plan_path is not None else ""
        self.execution_bar.update_progress(100, f"Saved {len(final_outputs(self.run_outputs))} file(s){plan} to {folder}")

    def on_clear_outputs(self):
        """Clear on the Output Files card: the results are dropped, so Save Outputs has nothing to save."""
        self.discard_run()
        self.execution_bar.reset()

    def discard_run(self):
        """Drop the last run's outputs and its temp folder."""
        if self.run_worker is not None:
            self.run_worker.wait()  # never delete files under a running worker (e.g. on exit)
        self.output_files_card.clear()  # its thumbnails are read from the temp folder
        if self.run_workspace is not None:
            self.run_workspace.cleanup()
            self.run_workspace = None
        self.run_outputs = []
        self.run_plan_path = None
        self.execution_bar.set_save_available(False)

    def show_run_error(self, message: str):
        self.execution_bar.set_error()
        QMessageBox.warning(self, "Run Pipeline", message)
