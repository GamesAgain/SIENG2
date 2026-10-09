from html import escape
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from PyQt6.QtCore import QMimeData, pyqtSignal, Qt
from PyQt6.QtGui import QDrag, QIcon

from src.core.configurable.drafts import LSBInputsDraft, LocomotiveInputsDraft
from src.core.configurable.link import is_linked
from src.core.configurable.step_output import FileSource, StepOutput
from src.gui.components.gui_utils import create_icon_pixmap, format_file_size, truncate_text_middle
from src.gui.features.embed.configurable.constants import TECHNIQUE_DISPLAY
from src.path import svg_path

CARD_WIDTH = 300
CARD_HEIGHT = 160
ARROW_SIZE = 20
CLOSE_BUTTON_SIZE = 24
CLOSE_BUTTON_MARGIN = 6
STEP_CARD_MIME = "application/sieng2-step-card"
COVER_FILENAME_MAX_LENGTH = 36
TOOLTIP_TEXT_LIMIT = 300  # chars of the secret message shown in the payload tooltip
SUMMARY_PLACEHOLDERS = {  # row texts of a step that has no saved inputs yet
    "cover": "Not selected", "payload": "Not configured", "output": "Pending", "encryption": "Not configured",
}

# --- Step Card Summary helpers ---
def encryption_text(draft: LSBInputsDraft | LocomotiveInputsDraft) -> str:
    if not draft.encryption_enabled:
        return "Off"
    return "Password" if draft.encryption_mode == "password" else "Public Key"

def text_size(text: str) -> str:
    return format_file_size(len(text.encode("utf-8")))

def file_size_text(path: str) -> str:
    try:
        return format_file_size(Path(path).stat().st_size)
    except OSError:
        return "Unavailable"

def cover_name(cover: FileSource, labels: dict[StepOutput, str]) -> str:
    """File name of a manual cover, or 'Step N output' for a Previous Output."""
    return labels.get(cover, "Unavailable output") if is_linked(cover) else Path(cover).name

def cover_line(cover: FileSource, labels: dict[StepOutput, str]) -> str:
    """For lists and tooltips: a Previous Output also shows its file name (outputs of one step share a label)."""
    name = cover_name(cover, labels)
    return f"{name} ({cover.output_key}.png)" if is_linked(cover) else name

def text_tooltip(text: str) -> str:
    """Show the message as plain text: long text is cut, and '<b>' etc. stays visible instead of becoming HTML."""
    preview = text if len(text) <= TOOLTIP_TEXT_LIMIT else text[:TOOLTIP_TEXT_LIMIT] + "…"
    return "<qt>" + escape(preview).replace("\n", "<br>") + "</qt>"

class StepCard(QFrame):
    """Visual summary of one step; inputs and configuration are not connected yet."""
    remove_requested = pyqtSignal()
    clicked = pyqtSignal()
    
    def __init__(self, step_number: int, technique: str, parent=None, *, step_key: str = ""):
        super().__init__(parent)
        if technique not in TECHNIQUE_DISPLAY:
            raise ValueError(f"Unsupported technique: {technique}")
        
        # Step card detail
        self.step_key = step_key
        self.step_number = step_number
        self.drag_start_position = None  # where the left button went down (a click or the start of a drag)
        self.technique = technique
        self.meta = TECHNIQUE_DISPLAY[technique]

        # UI Configuration
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

        # Summary rows (value labels are kept as attributes; set them with set_cover / set_payload / ...)
        self.cover_label = self.add_summary_row(layout, "Cover", SUMMARY_PLACEHOLDERS["cover"])
        self.payload_label = self.add_summary_row(layout, "Payload", SUMMARY_PLACEHOLDERS["payload"])
        divider = QFrame()
        divider.setObjectName("stepCardDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        layout.addWidget(divider)
        self.output_label = self.add_summary_row(layout, "Output", SUMMARY_PLACEHOLDERS["output"])
        self.encryption_label = self.add_summary_row(layout, "Encryption", SUMMARY_PLACEHOLDERS["encryption"])
        layout.addStretch()

    def add_summary_row(self, layout: QVBoxLayout, title: str, placeholder: str) -> QLabel:
        """Add a 'TITLE  value' row to the card and return its value label."""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        title_label = QLabel(title.upper())
        title_label.setObjectName("pipelineSummary")
        title_label.setFixedWidth(78)
        value_label = QLabel(placeholder)
        value_label.setObjectName("stepCardSub")
        row_layout.addWidget(title_label)
        row_layout.addWidget(value_label, 1)
        layout.addWidget(row)
        return value_label

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

    # --- Summary rows: text and tooltip are set together (the tooltip defaults to the text) ---
    @staticmethod
    def set_row(label: QLabel, text: str, tooltip: str | None):
        label.setText(text)
        label.setToolTip(text if tooltip is None else tooltip)

    def set_cover(self, text: str, tooltip: str | None = None):
        # A long name is shortened in the middle on the card; the tooltip keeps the full text
        self.set_row(self.cover_label, truncate_text_middle(text, COVER_FILENAME_MAX_LENGTH), text if tooltip is None else tooltip)

    def set_payload(self, text: str, tooltip: str | None = None):
        self.set_row(self.payload_label, text, tooltip)

    def set_output(self, text: str, tooltip: str | None = None):
        self.set_row(self.output_label, text, tooltip)

    def set_encryption(self, text: str, tooltip: str | None = None):
        self.set_row(self.encryption_label, text, tooltip)

    def set_summary(self, *, cover: str, payload: str, output: str, encryption: str):
        """Set all four rows at once (texts only)."""
        self.set_cover(cover)
        self.set_payload(payload)
        self.set_output(output)
        self.set_encryption(encryption)

    # --- Summary from a saved step ---
    def set_inputs(self, draft: LSBInputsDraft | LocomotiveInputsDraft | None, labels: dict[StepOutput, str] | None = None):
        """Show a step's saved inputs on the rows; None = nothing saved yet -> placeholders.
        labels: the text of each Previous Output cover, e.g. 'Step 1 output' (the page knows the step numbers)."""
        labels = labels or {}
        if draft is None:
            self.set_summary(**SUMMARY_PLACEHOLDERS)
        elif isinstance(draft, LSBInputsDraft):
            self.show_lsb(draft, labels)
        elif isinstance(draft, LocomotiveInputsDraft):
            self.show_locomotive(draft, labels)

    def show_lsb(self, draft: LSBInputsDraft, labels: dict[StepOutput, str]):
        # tooltip of a file = its full path (which folder it came from); of a Previous Output = label + file name
        tooltip = cover_line(draft.cover, labels) if is_linked(draft.cover) else draft.cover
        self.set_cover(cover_name(draft.cover, labels), tooltip=tooltip)
        self.set_payload(f"Text ({text_size(draft.payload_text)})", text_tooltip(draft.payload_text))
        self.set_output("PNG ×1")
        self.set_encryption(encryption_text(draft))

    def show_locomotive(self, draft: LocomotiveInputsDraft, labels: dict[StepOutput, str]):
        # 1. Covers: one -> its name, several -> "PNGs ×N"; the tooltip lists them all
        count = len(draft.covers)
        cover_lines = [f"Cover PNGs ({count}):"]
        cover_lines += [f"{number}. {cover_line(cover, labels)}" for number, cover in enumerate(draft.covers, start=1)]
        self.set_cover(cover_name(draft.covers[0], labels) if count == 1 else f"PNGs ×{count}", "\n".join(cover_lines))

        # 2. Payload: files -> "Files ×N (total size)", text -> "Text (size)" like LSB++
        if draft.payload_mode == "files":
            files = draft.payload_files
            payload_lines = [f"Payload files ({len(files)}):"]
            for number, path in enumerate(files, start=1):
                size = "" if is_linked(path) else f" — {file_size_text(path)}"  # a Previous Output has no file yet
                payload_lines.append(f"{number}. {cover_line(path, labels)}{size}")
            if any(is_linked(path) for path in files):
                self.set_payload(f"Files ×{len(files)} (Previous Output)", "\n".join(payload_lines))
            else:
                total = sum(Path(path).stat().st_size for path in files if Path(path).is_file())
                self.set_payload(f"Files ×{len(files)} ({format_file_size(total)})", "\n".join(payload_lines))
        else:
            self.set_payload(f"Text ({text_size(draft.payload_text)})", text_tooltip(draft.payload_text))

        # 3. Output / encryption
        self.set_output(f"PNG ×{count}")
        self.set_encryption(encryption_text(draft))

    def set_description(self, description: str):
        self.description_label.setText(description)
        self.description_label.setToolTip(description)

    def set_status(self, state: str, detail: str):
        """state: 'setup' | 'ready' | 'blocked' -- colour comes from QSS via the 'state' property"""
        self.status_label.setText(state.upper())
        self.status_label.setProperty("state", state)
        self.status_label.setToolTip(detail)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def enterEvent(self, event):
        self.close_button.show()
        self.close_button.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.close_button.hide()
        super().leaveEvent(event)

    # --- Click or drag (a drag moves the card: StepCanvas receives it) ---
    def mousePressEvent(self, event):
        # Accept the press, otherwise the release is not delivered to this card.
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Moving far enough while the button is held = a drag
        if self.drag_start_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            distance = (event.position().toPoint() - self.drag_start_position).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self.start_drag()
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        start, self.drag_start_position = self.drag_start_position, None  # a drag already cleared it, so it cannot click
        # A click = the left button released on the card without moving far
        if event.button() == Qt.MouseButton.LeftButton and start is not None:
            position = event.position().toPoint()
            if self.rect().contains(position) and (position - start).manhattanLength() < QApplication.startDragDistance():
                event.accept()
                self.clicked.emit()
                return
        super().mouseReleaseEvent(event)

    def start_drag(self):
        hotspot = self.drag_start_position
        self.drag_start_position = None
        self.close_button.hide()  # not in the picture that follows the pointer
        drag = QDrag(self)  # drag.source() is this exact card, even when two cards have the same technique
        mime = QMimeData()
        mime.setData(STEP_CARD_MIME, b"internal")
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(hotspot)
        drag.exec(Qt.DropAction.MoveAction)  # Esc or a drop outside the canvas changes nothing: only StepCanvas reorders
    
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