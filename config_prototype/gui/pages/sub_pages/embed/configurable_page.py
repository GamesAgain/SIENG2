from dataclasses import dataclass
from functools import partial
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QWidget, QDialog, QFrame, QVBoxLayout, QHBoxLayout,
    QScrollArea, QLabel, QComboBox, QMessageBox, QPushButton, QButtonGroup,
    QProgressBar,
)

from config_prototype.gui.components.step_card import (
    CARD_HEIGHT,
    TECHNIQUE_DISPLAY,
    StepCard,
    make_arrow,
)
from config_prototype.gui.components.technique_forms import (
    LSBEmbedInputs,
    LSBInputsDraft,
    LocomotiveEmbedInputs,
    LocomotiveInputsDraft,
)
from config_prototype.gui.components.step_config_shell import (
    StepConfigShellDialog,
    StepConfigShellPanel,
)
from config_prototype.gui.paths import ICON_DIR
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


@dataclass
class PipelineStepDraft:
    key: str
    technique: str
    description: str
    guidenote: str = ""
    technique_inputs: LSBInputsDraft | LocomotiveInputsDraft | None = None


class EmbedConfigurablePage(QFrame):

    def __init__(
        self,
        key_registry: KeyRegistry | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.key_registry = key_registry
        self.pipeline_steps: list[PipelineStepDraft] = []
        self._next_step_key = 1
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
                key=self._new_step_key(),
                technique=technique,
                description=meta["description"],
            )
        )
        self.render_step_cards()

    def _new_step_key(self) -> str:
        key = f"prototype_step_{self._next_step_key}"
        self._next_step_key += 1
        return key

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
        return next(
            (step for step in self.pipeline_steps if step.key == step_key),
            None,
        )

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
            technique_inputs = technique_form.export_draft()
        elif isinstance(technique_form, LocomotiveEmbedInputs):
            if not technique_form.validate_draft():
                return False
            technique_inputs = technique_form.export_draft()

        step.description = description
        step.guidenote = guidenote.strip()
        step.technique_inputs = technique_inputs
        return True

    def create_step_technique_form(
        self,
        step: PipelineStepDraft,
    ) -> QWidget | None:
        if step.technique == "lsbpp":
            form = LSBEmbedInputs(key_registry=self.key_registry)
            if isinstance(step.technique_inputs, LSBInputsDraft):
                form.load_draft(step.technique_inputs)
            return form

        if step.technique == "locomotive":
            form = LocomotiveEmbedInputs(key_registry=self.key_registry)
            if isinstance(step.technique_inputs, LocomotiveInputsDraft):
                form.load_draft(step.technique_inputs)
            return form

        if step.technique == "metadata":
            return None

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
        technique_form = self.create_step_technique_form(step)
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
        technique_form = self.create_step_technique_form(step)
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
            self.step_cards.append(step_card)
            self.flow_layout.addWidget(step_card)

        has_steps = bool(self.pipeline_steps)
        self.empty_canvas_label.setVisible(not has_steps)
        self.canvas_scroll.setVisible(has_steps)
        if not has_steps:
            self.canvas_scroll.verticalScrollBar().setValue(0)

        self.refresh_canvas_height()

    @staticmethod
    def apply_step_draft_to_card(
        step_card: StepCard,
        step: PipelineStepDraft,
    ) -> None:
        draft = step.technique_inputs
        if step.technique == "lsbpp" and isinstance(draft, LSBInputsDraft):
            EmbedConfigurablePage.apply_lsb_draft_to_card(step_card, draft)
            return

        if step.technique == "locomotive" and isinstance(
            draft,
            LocomotiveInputsDraft,
        ):
            EmbedConfigurablePage.apply_locomotive_draft_to_card(
                step_card,
                draft,
            )

    @staticmethod
    def apply_lsb_draft_to_card(
        step_card: StepCard,
        draft: LSBInputsDraft,
    ) -> None:
        encryption = EmbedConfigurablePage.encryption_summary(
            draft.encryption_enabled,
            draft.encryption_mode,
        )

        step_card.set_summary(
            cover=Path(draft.cover_path).name if draft.cover_path else "Not selected",
            payload=(
                f"Text ({format_file_size(len(draft.payload_text.encode('utf-8')))})"
            ),
            output="PNG ×1",
            encryption=encryption,
        )
        step_card.set_status("ready", "LSB++ inputs are configured")

    @staticmethod
    def apply_locomotive_draft_to_card(
        step_card: StepCard,
        draft: LocomotiveInputsDraft,
    ) -> None:
        cover_count = len(draft.cover_paths)
        cover = (
            Path(draft.cover_paths[0]).name
            if cover_count == 1
            else f"PNG ×{cover_count}"
        )

        if draft.payload_mode == "text":
            payload_size = len(draft.payload_text.encode("utf-8"))
            payload = f"Text ({format_file_size(payload_size)})"
        else:
            payload_size = sum(
                Path(path).stat().st_size
                for path in draft.payload_paths
                if Path(path).is_file()
            )
            payload = (
                f"Files ×{len(draft.payload_paths)} "
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
                f"{index}. {Path(path).name}"
                for index, path in enumerate(draft.cover_paths, start=1)
            )
            step_card.set_summary_tooltip(
                "cover",
                "\n".join(cover_lines),
            )

        if draft.payload_mode == "files":
            payload_lines = [
                f"Payload files ({len(draft.payload_paths)}):"
            ]
            for index, path in enumerate(draft.payload_paths, start=1):
                file_path = Path(path)
                file_size = (
                    format_file_size(file_path.stat().st_size)
                    if file_path.is_file()
                    else "Unavailable"
                )
                payload_lines.append(
                    f"{index}. {file_path.name} — {file_size}"
                )
            payload_lines.append(f"Total: {format_file_size(payload_size)}")
            step_card.set_summary_tooltip(
                "payload",
                "\n".join(payload_lines),
            )

        step_card.set_status("ready", "Locomotive inputs are configured")

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
