from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config_prototype.gui.paths import ICON_DIR
from src.gui.components.gui_utils import create_icon_pixmap


CARD_WIDTH = 300
CARD_HEIGHT = 160
ARROW_SIZE = 20
CLOSE_BUTTON_SIZE = 24
CLOSE_ICON_SIZE = 12
CLOSE_BUTTON_MARGIN = 6
STATUS_NAMES = {"setup", "ready", "blocked"}

TECHNIQUE_DISPLAY = {
    "lsbpp": {
        "label": "LSB++",
        "description": "Embed text in PNG",
        "accent": "blue",
        "hex": "#38BDF8",
    },
    "locomotive": {
        "label": "Locomotive",
        "description": "Embed files in PNG",
        "accent": "purple",
        "hex": "#A78BFA",
    },
    "metadata": {
        "label": "Metadata",
        "description": "Hide data in PNG or MP3 metadata",
        "accent": "orange",
        "hex": "#F59E0F",
    },
}


class StepCard(QWidget):
    clicked = pyqtSignal()
    remove_requested = pyqtSignal()

    def __init__(
        self,
        step_number: int,
        technique: str,
        parent: QWidget | None = None,
        *,
        description: str | None = None,
    ) -> None:
        super().__init__(parent)

        if technique not in TECHNIQUE_DISPLAY:
            raise ValueError(f"Unsupported technique: {technique}")

        self.step_number = step_number
        self.technique = technique
        self.meta = TECHNIQUE_DISPLAY[technique]
        self.description = (
            self.meta["description"] if description is None else description
        )

        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.build_ui()
        self.build_close_button()
        self.set_status("setup", "Inputs or settings are incomplete")

    def build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame()
        self.card.setObjectName("stepCard")
        self.card.setProperty("accentColor", self.meta["accent"])
        root_layout.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(16, 12, 14, 12)
        card_layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, CLOSE_BUTTON_SIZE + 4, 0)
        header.setSpacing(7)

        step_label = QLabel(f"STEP {self.step_number}")
        step_label.setObjectName("prototypeStepCardNumber")

        technique_label = QLabel(self.meta["label"])
        technique_label.setObjectName("prototypeStepCardTitle")
        technique_label.setProperty("accentColor", self.meta["accent"])

        self.status_label = QLabel()
        self.status_label.setObjectName("prototypeStepCardStatus")
        self.status_label.setMinimumWidth(58)
        self.status_label.setMinimumHeight(18)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header.addWidget(step_label)
        header.addWidget(technique_label)
        header.addStretch()
        header.addWidget(self.status_label)
        card_layout.addLayout(header)

        description_label = QLabel(self.description)
        description_label.setObjectName("stepCardSub")
        card_layout.addWidget(description_label)

        card_layout.addSpacing(12)

        card_layout.addWidget(self.create_row("Cover", "Not selected"))
        card_layout.addWidget(self.create_row("Payload", "Not configured"))

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        card_layout.addWidget(divider)

        card_layout.addWidget(self.create_row("Output", "Pending"))
        card_layout.addWidget(self.create_row("Encryption", "Not configured"))
        card_layout.addStretch()

    def build_close_button(self) -> None:
        self.close_button = QPushButton(self)
        self.close_button.setObjectName("prototypeStepCloseBtn")
        self.close_button.setFixedSize(CLOSE_BUTTON_SIZE, CLOSE_BUTTON_SIZE)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setIcon(
            QIcon(
                create_icon_pixmap(
                    ICON_DIR / "x.svg",
                    color_hex="#FFFFFF",
                    size=CLOSE_ICON_SIZE,
                )
            )
        )
        self.close_button.setToolTip(f"Remove Step {self.step_number}")
        self.close_button.setAccessibleName(f"Remove Step {self.step_number}")
        self.close_button.move(
            CARD_WIDTH - CLOSE_BUTTON_SIZE - CLOSE_BUTTON_MARGIN,
            CLOSE_BUTTON_MARGIN,
        )
        self.close_button.clicked.connect(self.remove_requested.emit)
        self.close_button.hide()

    def enterEvent(self, event) -> None:
        self.close_button.show()
        self.close_button.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.close_button.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        close_button_clicked = (
            self.close_button.isVisible()
            and self.close_button.geometry().contains(event.position().toPoint()) # เช็คว่าคลิกที่ตำแหน่งปุ่ม Delete ไหม
        )
        if (event.button() == Qt.MouseButton.LeftButton and not close_button_clicked):
            self.clicked.emit()

        super().mousePressEvent(event)

    def set_status(self, status: str, tooltip: str = "") -> None:
        status = status.lower()
        if status not in STATUS_NAMES:
            raise ValueError(f"Unsupported step status: {status}")

        self.status = status
        self.status_label.setText(status.upper())
        self.status_label.setProperty("state", status)
        self.status_label.setToolTip(tooltip)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.update()

    @staticmethod
    def create_row(field_name: str, placeholder: str) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        field_label = QLabel(field_name.upper())
        field_label.setObjectName("pipelineSummary")
        field_label.setFixedWidth(78)

        value_label = QLabel(placeholder)
        value_label.setObjectName("stepCardSub")

        row_layout.addWidget(field_label)
        row_layout.addWidget(value_label, 1)
        return row


def center_in_band(inner: QWidget, inner_width: int, inner_height: int) -> QWidget:
    """Center a small widget vertically against the full StepCard height."""
    container = QWidget()
    container.setFixedSize(inner_width, CARD_HEIGHT)
    inner.setParent(container)
    inner.move(0, (CARD_HEIGHT - inner_height) // 2)
    return container


def make_arrow() -> QWidget:
    arrow = QLabel()
    arrow.setPixmap(
        create_icon_pixmap(
            ICON_DIR / "arrow-narrow-right.svg",
            color_hex="#64748B",
            size=ARROW_SIZE,
        )
    )
    arrow.setFixedSize(ARROW_SIZE, ARROW_SIZE)
    arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return center_in_band(arrow, ARROW_SIZE, ARROW_SIZE)
