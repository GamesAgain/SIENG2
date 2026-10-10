"""
One step of the receiver's extract pipeline.

Shows what the step needs, what it gives, the guidenote and the decryption options (the same controls as the
Standalone extract forms), plus the Result / Extract buttons. The look follows the embed StepCard (same QSS names).
This widget only shows things: reading the secrets and extracting are done by the page.
"""
from html import escape

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QSizePolicy, QVBoxLayout

from src.core.configurable.extract_plan import PlanStep
from src.gui.components.gui_utils import add_password_visibility_toggle, create_icon_pixmap
from src.gui.components.widgets.key_source import KeySourceWidget
from src.gui.components.widgets.key_validation import KeyValidationLabel, KeyValidationResult, inspect_private_key
from src.gui.features.embed.configurable.constants import TECHNIQUE_DISPLAY
from src.gui.services.key_registry import KeyRegistry
from src.path import svg_path

TITLE_WIDTH = 78       # same width as the summary titles of the embed StepCard
BUTTON_WIDTH = 120
BUTTON_HEIGHT = 30
PROGRESS_HEIGHT = 6  # mini loading bar under the card's rows
KEY_DROP_HEIGHT = 72   # shorter than the standalone form: the card holds more than one thing
MISSING_COLOR = "#F59E0F"
STATES = {"waiting": "WAITING", "ready": "READY", "done": "DONE", "failed": "FAILED"}


def gives_text(step: PlanStep) -> str:
    """What the receiver gets from this step, in a few words."""
    parts = []
    if step.gives_text:
        parts.append("Text")
    if step.gives_fields:
        parts.append("Hidden fields")
    files = step.gives_files + list(step.gives_pictures.values())
    if files:
        parts.append(f"{len(files)} file{'s' if len(files) > 1 else ''}: {', '.join(files)}")
    return " + ".join(parts) or "Nothing"


class ExtractStepCard(QFrame):
    """
    step: the plan step (its id is its extract order) · number: the number shown (1 = extract first)
    step_numbers: plan step id -> number, to write "from Step 3" · missing: Need.key of the files the receiver has not added
    """
    extract_requested = pyqtSignal()
    result_requested = pyqtSignal()

    def __init__(self, step: PlanStep, number: int, step_numbers: dict[str, int] | None = None,
                 missing: set | None = None, key_registry: KeyRegistry | None = None, parent=None):
        super().__init__(parent)
        self.step = step
        self.number = number
        self.meta = TECHNIQUE_DISPLAY[step.technique]
        self.key_registry = key_registry
        self.step_numbers = step_numbers or {}
        self.password_input: QLineEdit | None = None       # encryption: password
        self.key_source: KeySourceWidget | None = None     # encryption: public_key (the receiver chooses the private key)
        self.key_password_input: QLineEdit | None = None
        self.key_status: KeyValidationLabel | None = None

        self.setObjectName("stepCard")
        self.setProperty("accentColor", self.meta["accent"])
        # Keep the height of its rows: when the list is short the page must not stretch the cards
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.build_ui(step_numbers or {}, missing or set())
        self.set_state("waiting")

    # --- UI ---
    def build_ui(self, step_numbers: dict[str, int], missing: set) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 12, 10)
        root.setSpacing(8)
        outer = QHBoxLayout()
        outer.setSpacing(12)

        body = QVBoxLayout()
        body.setSpacing(4)
        body.addLayout(self.build_header())
        if self.step.description:
            self.description_label = QLabel(self.step.description)
            self.description_label.setObjectName("stepCardSub")
            self.description_label.setWordWrap(True)
            body.addWidget(self.description_label)
            body.addSpacing(4)
        self.needs_label = self.add_row(body, "Cover", self.needs_text(step_numbers, missing), rich=True)
        if self.step.guidenote:
            self.note_label = self.add_row(body, "Note", self.step.guidenote)
        if self.step.encryption == "password":
            body.addLayout(self.build_password_row())
        elif self.step.encryption == "public_key":
            body.addLayout(self.build_key_row())
        body.addStretch()  # when the buttons are taller than the rows, the extra space goes here, not between the rows
        outer.addLayout(body, 1)

        # Result at the top, Extract at the bottom: the same line as the decryption options
        buttons = QVBoxLayout()
        buttons.setSpacing(4)
        self.result_button = self.make_button(" View Result", "SecondaryBtn", "file-search.svg", "#94A3B8")
        self.extract_button = self.make_button(" Extract", "PrimaryActionBtn", "lock-open.svg", "#38BDF8")
        self.result_button.clicked.connect(self.result_requested.emit)
        self.extract_button.clicked.connect(self.on_extract_clicked)
        buttons.addWidget(self.result_button)
        buttons.addStretch()
        buttons.addWidget(self.extract_button)
        outer.addLayout(buttons)
        root.addLayout(outer)
        root.addWidget(self.build_progress())

    def build_progress(self) -> QFrame:
        """Mini loading bar of this step (the page has no status bar: each step is extracted on its own)."""
        self.progress_box = QFrame()
        layout = QVBoxLayout(self.progress_box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.progress_label = QLabel()
        self.progress_label.setObjectName("statusLabel")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("loadingIndicator")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(PROGRESS_HEIGHT)
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)
        self.progress_box.hide()  # shown once this step is extracted
        return self.progress_box

    def build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(7)
        number_label = QLabel(f"STEP {self.number}")
        number_label.setObjectName("stepCardNumber")
        title = QLabel(self.meta["label"])
        title.setObjectName("stepCardTitle")
        title.setProperty("accentColor", self.meta["accent"])
        header.addWidget(number_label)
        header.addWidget(title)
        header.addStretch()
        self.status_label = QLabel()
        self.status_label.setObjectName("stepCardStatus")
        self.status_label.setMinimumSize(58, 18)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.status_label)
        return header

    def add_row(self, layout: QVBoxLayout, title: str, text: str, *, rich: bool = False) -> QLabel:
        """'TITLE  value' row (same look as the summary rows of the embed StepCard)."""
        row = QHBoxLayout()
        row.setSpacing(8)
        title_label = QLabel(title.upper())
        title_label.setObjectName("pipelineSummary")
        title_label.setFixedWidth(TITLE_WIDTH)
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        value = QLabel(text)
        value.setObjectName("stepCardSub")
        value.setWordWrap(True)
        value.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
        row.addWidget(title_label)
        row.addWidget(value, 1)
        layout.addLayout(row)
        return value

    def needs_text(self, step_numbers: dict[str, int], missing: set) -> str:
        """'image2.png (from Step 3) · image3.png (not added)': a file that is missing is orange."""
        parts = []
        for need in self.step.needs:
            text = escape(need.file)
            if need.source is not None:
                text += escape(f" (from Step {step_numbers[need.source]})" if need.source in step_numbers else " (from an earlier step)")
            if need.key in missing:
                text = f'<span style="color:{MISSING_COLOR}">{text} (not added)</span>'
            parts.append(text)
        return " · ".join(parts)

    def set_missing(self, missing: set) -> None:
        """Write the COVER line again when the receiver adds or removes files."""
        self.needs_label.setText(self.needs_text(self.step_numbers, missing))

    # --- Decryption options (the controls of the Standalone extract forms) ---
    def build_password_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        title = QLabel("PASSWORD")
        title.setObjectName("pipelineSummary")
        title.setFixedWidth(TITLE_WIDTH)
        self.password_input = QLineEdit()
        self.password_input.setObjectName("formInput")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter passphrase...")
        add_password_visibility_toggle(self.password_input)
        row.addWidget(title)
        row.addWidget(self.password_input, 1)
        return row

    def build_key_row(self) -> QHBoxLayout:
        """KEY  [Choose Saved Key + drop zone] / [private key password] / [key check] -- one column, the password under the drop zone."""
        row = QHBoxLayout()
        row.setSpacing(12)
        title = QLabel("PRIVATE KEY")
        title.setObjectName("pipelineSummary")
        title.setFixedWidth(TITLE_WIDTH)
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self.key_source = KeySourceWidget("private", self.key_registry)
        self.key_source.drop_zone.setMinimumHeight(0)
        self.key_source.drop_zone.drop_zone.setMinimumHeight(KEY_DROP_HEIGHT)
        self.key_password_input = QLineEdit()
        self.key_password_input.setObjectName("formInput")
        self.key_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_password_input.setPlaceholderText("Private key password (optional)")
        add_password_visibility_toggle(self.key_password_input)
        self.key_status = KeyValidationLabel()  # hidden until a key is checked
        self.key_source.key_selected.connect(self.check_key)  # same checks as the Standalone extract forms
        self.key_password_input.editingFinished.connect(self.check_key)

        column = QVBoxLayout()
        column.setSpacing(4)
        column.addWidget(self.key_source)
        column.addWidget(self.key_password_input)
        column.addWidget(self.key_status)
        row.addWidget(title)
        row.addLayout(column, 1)
        return row

    @staticmethod
    def make_button(text: str, object_name: str, icon_name: str, icon_color: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setIcon(QIcon(create_icon_pixmap(svg_path(icon_name), icon_color, size=14)))
        button.setFixedSize(BUTTON_WIDTH, BUTTON_HEIGHT)
        return button

    # --- Secrets typed into this card ---
    def credentials(self) -> tuple[str | None, str | None]:
        """(password, private key path). For a private key, the password is the key's own password (None if it has none)."""
        if self.step.encryption == "password":
            return self.password_input.text(), None
        if self.step.encryption == "public_key":
            return self.key_password_input.text() or None, self.key_source.drop_zone.file_path or None
        return None, None

    def check_key(self, _path=None) -> KeyValidationResult | None:
        """Check the chosen private key (and its password) and show the result under it; None = no key chosen."""
        path = self.key_source.drop_zone.file_path
        if not path:
            self.key_status.clear_result()
            return None
        result = inspect_private_key(path, self.key_password_input.text() or None)
        self.key_status.set_result(result)
        return result

    def set_busy(self, busy: bool) -> None:
        """While any step is extracted: no button and no secret field can be used (set_state turns the buttons on again)."""
        for widget in (self.password_input, self.key_source, self.key_password_input):
            if widget is not None:
                widget.setEnabled(not busy)
        if busy:
            self.extract_button.setEnabled(False)
            self.result_button.setEnabled(False)

    # --- State ---
    def set_state(self, state: str, detail: str = "") -> None:
        """
        state: 'waiting' (a file is not there yet) | 'ready' | 'done' | 'failed' (colour comes from QSS via the 'state' property)
        Extract can be pressed when ready or failed (try again); Result when done.
        """
        if state not in STATES:
            raise ValueError(f"Unknown step state: {state}")
        self.status_label.setText(STATES[state])
        self.status_label.setProperty("state", state)
        self.status_label.setToolTip(detail)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.extract_button.setEnabled(state in ("ready", "failed"))
        self.result_button.setEnabled(state == "done")

    # --- Progress (the page calls these while this step is extracted) ---
    def on_extract_clicked(self) -> None:
        """The page checks the inputs first, then shows the loading bar ('Starting...') and extracts this step."""
        self.extract_requested.emit()

    def set_progress(self, percent: int, message: str) -> None:
        """'Status: <message>' like the Standalone execution bar (callers pass only the message)."""
        self.progress_label.setText(f"Status: {message}")
        self.progress_bar.setValue(percent)
        self.progress_box.show()

    def clear_progress(self) -> None:
        self.progress_label.clear()
        self.progress_bar.setValue(0)
        self.progress_box.hide()
