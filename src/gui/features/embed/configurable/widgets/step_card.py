from PyQt6.QtCore import QMimeData, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QIcon
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from src.gui.components.gui_utils import create_icon_pixmap, truncate_text_middle
from src.path import svg_path


CARD_WIDTH = 300
CARD_HEIGHT = 160
ARROW_SIZE = 20
CLOSE_BUTTON_SIZE = 24
CLOSE_BUTTON_MARGIN = 6
STEP_CARD_MIME = "application/sieng2-step-card"
COVER_FILENAME_MAX_LENGTH = 36
TECHNIQUE_DISPLAY = {
    "lsbpp": {
        "label": "LSB++", "description": "Embed text in PNG",
        "accent": "blue", "hex": "#38BDF8",
    },
    "locomotive": {
        "label": "Locomotive", "description": "Embed files in PNG",
        "accent": "purple", "hex": "#A78BFA",
    },
    "metadata": {
        "label": "Metadata", "description": "Hide data in PNG or MP3 metadata",
        "accent": "orange", "hex": "#F59E0F",
    },
}


class StepCard(QFrame):
    """Visual summary of one step; inputs and configuration are not connected yet."""
    remove_requested = pyqtSignal()
    clicked = pyqtSignal()

    def __init__(self, step_number: int, technique: str, parent=None, *, step_key: str = ""):
        super().__init__(parent)
        if technique not in TECHNIQUE_DISPLAY:
            raise ValueError(f"Unsupported technique: {technique}")
        self.step_number = step_number
        self.step_key = step_key
        self.technique = technique
        self.meta = TECHNIQUE_DISPLAY[technique]
        self.summary_labels: dict[str, QLabel] = {}
        self.drag_start_position = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("stepCard")
        self.setProperty("accentColor", self.meta["accent"])
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.build_ui()
        self.build_close_button()

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 14, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        # Reserve room for the floating hover button so it cannot cover SETUP.
        header.setContentsMargins(0, 0, CLOSE_BUTTON_SIZE + 4, 0)
        header.setSpacing(7)
        self.step_label = QLabel(f"STEP {self.step_number}")
        self.step_label.setObjectName("stepCardNumber")
        technique_label = QLabel(self.meta["label"])
        technique_label.setObjectName("stepCardTitle")
        technique_label.setProperty("accentColor", self.meta["accent"])
        self.status_label = QLabel("SETUP")
        self.status_label.setObjectName("stepCardStatus")
        self.status_label.setProperty("state", "setup")
        self.status_label.setMinimumSize(58, 18)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setToolTip("Inputs or settings are incomplete")
        header.addWidget(self.step_label)
        header.addWidget(technique_label)
        header.addStretch()
        header.addWidget(self.status_label)
        layout.addLayout(header)

        description_label = QLabel(self.meta["description"])
        self.description_label = description_label
        description_label.setObjectName("stepCardSub")
        description_label.setToolTip(self.meta["description"])
        layout.addWidget(description_label)
        layout.addSpacing(12)

        # Placeholders follow the reference; they will reflect saved inputs later.
        layout.addWidget(self.create_row("Cover", "Not selected"))
        layout.addWidget(self.create_row("Payload", "Not configured"))
        divider = QFrame()
        divider.setObjectName("stepCardDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        layout.addWidget(divider)
        layout.addWidget(self.create_row("Output", "Pending"))
        layout.addWidget(self.create_row("Encryption", "Not configured"))
        layout.addStretch()

    def build_close_button(self):
        self.close_button = QPushButton(self)
        self.close_button.setObjectName("stepCloseBtn")
        self.close_button.setFixedSize(CLOSE_BUTTON_SIZE, CLOSE_BUTTON_SIZE)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setIcon(QIcon(create_icon_pixmap(svg_path("x.svg"), "#FFFFFF", size=12)))
        self.close_button.move(CARD_WIDTH - CLOSE_BUTTON_SIZE - CLOSE_BUTTON_MARGIN, CLOSE_BUTTON_MARGIN)
        self.close_button.clicked.connect(self.remove_requested.emit)
        self.set_step_number(self.step_number)
        self.close_button.hide()

    def set_step_number(self, number: int):
        self.step_number = number
        self.step_label.setText(f"STEP {number}")
        self.close_button.setToolTip(f"Remove Step {number}")
        self.close_button.setAccessibleName(f"Remove Step {number}")

    def enterEvent(self, event):
        self.close_button.show()
        self.close_button.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.close_button.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = event.position().toPoint()
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_start_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            distance = (event.position().toPoint() - self.drag_start_position).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self.start_drag()
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        start = self.drag_start_position
        self.drag_start_position = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # start_drag() clears the press position, so its release cannot click.
        if event.button() == Qt.MouseButton.LeftButton and start is not None:
            position = event.position().toPoint()
            if self.rect().contains(position) and (position - start).manhattanLength() < QApplication.startDragDistance():
                event.accept()
                self.clicked.emit()
                return
        super().mouseReleaseEvent(event)

    def start_drag(self):
        # QDrag.source() identifies this exact card, even for duplicate techniques.
        hotspot = self.drag_start_position
        self.drag_start_position = None
        self.close_button.hide()
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(STEP_CARD_MIME, b"internal")
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(hotspot)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        try:
            # Esc/outside drops return IgnoreAction; only the canvas changes order.
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_description(self, description: str):
        self.description_label.setText(description)
        self.description_label.setToolTip(description)

    def set_summary(self, **values: str):
        for name, value in values.items():
            label = self.summary_labels[name]
            label.setText(truncate_text_middle(value, COVER_FILENAME_MAX_LENGTH) if name == "cover" else value)
            label.setToolTip(value)

    def set_status(self, state: str, detail: str):
        self.status_label.setText(state.upper())
        self.status_label.setProperty("state", state)
        self.status_label.setToolTip(detail)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def create_row(self, field_name: str, placeholder: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        field_label = QLabel(field_name.upper())
        field_label.setObjectName("pipelineSummary")
        field_label.setFixedWidth(78)
        value_label = QLabel(placeholder)
        value_label.setObjectName("stepCardSub")
        self.summary_labels[field_name.lower()] = value_label
        layout.addWidget(field_label)
        layout.addWidget(value_label, 1)
        return row


def make_arrow() -> QWidget:
    """Keep the arrow vertically centered within a full-height flow item."""
    container = QWidget()
    container.setFixedSize(ARROW_SIZE, CARD_HEIGHT)
    arrow = QLabel(container)
    arrow.setPixmap(create_icon_pixmap(svg_path("arrow-narrow-right.svg"), "#64748B", size=ARROW_SIZE))
    arrow.setFixedSize(ARROW_SIZE, ARROW_SIZE)
    arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
    arrow.move(0, (CARD_HEIGHT - ARROW_SIZE) // 2)
    return container
