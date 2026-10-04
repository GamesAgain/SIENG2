from PyQt6.QtCore import QEvent, QTimer, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap
from src.gui.components.widgets.execution_bar import ExecutionBar
from src.gui.features.embed.configurable.widgets.flow_layout import FlowLayout
from src.gui.features.embed.configurable.widgets.step_canvas import StepCanvas
from src.gui.features.embed.configurable.widgets.step_card import (
    CARD_HEIGHT, TECHNIQUE_DISPLAY, StepCard, make_arrow,
)
from src.gui.services.key_registry import KeyRegistry
from src.path import svg_path


ICON_SIZE = 16
CHIP_ICON_SIZE = 12
CANVAS_MARGIN = 16
EMPTY_CANVAS_HEIGHT = 192
FLOW_SPACING = 8
MAX_VISIBLE_FLOW_HEIGHT = CARD_HEIGHT * 2 + FLOW_SPACING


class EmbedConfigurablePage(QFrame):
    """Pipeline builder GUI; step editing and execution will be connected later."""

    def __init__(self, key_registry: KeyRegistry | None = None, parent=None):
        super().__init__(parent)
        self.key_registry = key_registry
        self.technique_buttons: dict[str, QPushButton] = {}
        # GUI widgets only for now; no pipeline drafts or execution state.
        self.step_cards: list[StepCard] = []
        self.setup_ui()

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
        content_layout.addStretch()
        self.page_scroll.setWidget(content)
        page_layout.addWidget(self.page_scroll, 1)

        execution_layout = QHBoxLayout()
        execution_layout.setContentsMargins(4, 0, 4, 4)
        self.execution_bar = ExecutionBar(text_active_button="Run Pipeline", is_config=True)
        execution_layout.addWidget(self.execution_bar)
        page_layout.addLayout(execution_layout)
        # TODO: Connect execution after pipeline inputs and workers are ready.
        # self.execution_bar.execute_requested.connect(self.on_run_pipeline)

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
        if technique not in TECHNIQUE_DISPLAY:
            raise ValueError(f"Unsupported technique: {technique}")
        card = StepCard(len(self.step_cards) + 1, technique)
        # Capture the card itself; displayed step numbers change after removal.
        card.remove_requested.connect(lambda card=card: self.remove_pipeline_step(card))
        self.step_cards.append(card)
        self.render_step_cards()

    def remove_pipeline_step(self, card: StepCard):
        if card not in self.step_cards:
            return
        self.step_cards.remove(card)
        self.render_step_cards()
        card.deleteLater()

    def confirm_clear_pipeline(self):
        if not self.step_cards:
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
        removed_cards = list(self.step_cards)
        # Keep the same list object: StepCanvas also references this collection.
        self.step_cards.clear()
        self.flow_container.drop_indicator.hide()
        self.render_step_cards()
        for card in removed_cards:
            card.deleteLater()

    def move_pipeline_step(self, card: StepCard, insertion_index: int):
        if card not in self.step_cards or not 0 <= insertion_index <= len(self.step_cards):
            return
        source_index = self.step_cards.index(card)
        # The drop slot belongs to the original list, before removing the source.
        if source_index < insertion_index:
            insertion_index -= 1
        if source_index == insertion_index:
            return
        self.step_cards.pop(source_index)
        self.step_cards.insert(insertion_index, card)
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

        for number, card in enumerate(self.step_cards, start=1):
            card.set_step_number(number)
            if number > 1:
                self.flow_layout.addWidget(make_arrow())
            self.flow_layout.addWidget(card)
            card.show()

        has_steps = bool(self.step_cards)
        self.empty_canvas_label.setVisible(not has_steps)
        self.canvas_scroll.setVisible(has_steps)
        self.refresh_canvas_height()
        QTimer.singleShot(0, self.refresh_canvas_height)

    def eventFilter(self, watched, event):
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

        # Only the visual selection works now; no dialog or panel is created.
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
        # TODO: Connect the selected mode when step configuration is implemented.
        # self.btn_popup.clicked.connect(lambda: self.set_config_variant("popup"))
        # self.btn_inline.clicked.connect(lambda: self.set_config_variant("inline"))
        return row
