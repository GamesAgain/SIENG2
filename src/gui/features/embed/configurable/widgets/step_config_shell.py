from collections.abc import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


class StepConfigHeader(QFrame):
    """Shared step description and optional note, independent of the technique."""

    def __init__(self, step_number: int, technique_label: str, description: str, guidenote: str, accent: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.title_label = QLabel(f"Step {step_number} :")
        self.title_label.setObjectName("cardTitle")
        self.technique_label = QLabel(technique_label)
        self.technique_label.setObjectName("stepConfigTechnique")
        self.technique_label.setProperty("accentColor", accent)
        title_row.addWidget(self.title_label)
        title_row.addWidget(self.technique_label)
        title_row.addStretch()

        description_label = QLabel("Description")
        description_label.setObjectName("formLabel")
        self.description_edit = QLineEdit(description)
        self.description_edit.setObjectName("formInput")
        self.description_edit.setPlaceholderText("Describe what this step does")
        self.description_edit.setFixedWidth(300)
        title_row.addWidget(description_label)
        title_row.addWidget(self.description_edit)
        layout.addLayout(title_row)

        note_row = QHBoxLayout()
        note_row.setSpacing(8)
        note_label = QLabel("GuideNote")
        note_label.setObjectName("formLabel")
        self.guidenote_edit = QLineEdit(guidenote)
        self.guidenote_edit.setObjectName("formInput")
        self.guidenote_edit.setPlaceholderText("Optional hint shown to the receiver while extracting this step")
        note_row.addWidget(note_label)
        note_row.addWidget(self.guidenote_edit, 1)
        layout.addLayout(note_row)

    def description(self) -> str:
        return self.description_edit.text().strip()

    def guidenote(self) -> str:
        return self.guidenote_edit.text().strip()


class StepConfigShell(QWidget):
    """Shared editor; saving closes the host only after validation succeeds."""
    close_requested = pyqtSignal()
    saved = pyqtSignal()

    def __init__(
        self, step_number: int, technique_label: str, content_widget: QWidget,
        parent=None, *, description: str = "", guidenote: str = "", accent: str = "blue",
        save_callback: Callable[[str, str], bool] | None = None,
    ):
        super().__init__(parent)
        self.content_widget = content_widget
        self.save_callback = save_callback
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        self.header = StepConfigHeader(step_number, technique_label, description, guidenote, accent)
        layout.addWidget(self.header)

        # Reuse the existing technique form without standalone execution controls.
        self.content_frame = QFrame()
        content_layout = QVBoxLayout(self.content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(content_widget)
        layout.addWidget(self.content_frame, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.close_button = QPushButton("Cancel")
        self.cancel_button = self.close_button
        self.close_button.setObjectName("SecondaryBtn")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self.close_requested.emit)
        button_row.addWidget(self.close_button)
        self.save_button = QPushButton("Save Step")
        self.save_button.setObjectName("PrimaryActionBtn")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.clicked.connect(self.try_save)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

    def try_save(self):
        if self.save_callback and self.save_callback(self.description(), self.guidenote()):
            self.saved.emit()

    def description(self) -> str:
        return self.header.description()

    def guidenote(self) -> str:
        return self.header.guidenote()

    def set_step_number(self, number: int):
        self.header.title_label.setText(f"Step {number} :")


class StepConfigShellDialog(QDialog):
    """Modal wrapper around the shared Save/Cancel editor."""

    def __init__(
        self, step_number: int, technique_label: str, content_widget: QWidget,
        parent=None, *, description: str = "", guidenote: str = "", accent: str = "blue",
        save_callback: Callable[[str, str], bool] | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("stepConfigShellDialog")
        self.setWindowTitle(f"Configure Step {step_number} - {technique_label}")
        self.setModal(True)
        self.setMinimumSize(1100, 650)
        self.resize(1100, 650)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.shell = StepConfigShell(
            step_number, technique_label, content_widget,
            description=description, guidenote=guidenote, accent=accent, save_callback=save_callback,
        )
        layout.addWidget(self.shell)
        self.header = self.shell.header
        self.content_widget = self.shell.content_widget
        self.close_button = self.shell.close_button
        self.cancel_button = self.shell.cancel_button
        self.save_button = self.shell.save_button
        self.save_button.setDefault(True)
        self.close_button.setAutoDefault(False)
        self.shell.close_requested.connect(self.reject)
        self.shell.saved.connect(self.accept)

    def description(self) -> str:
        return self.shell.description()

    def guidenote(self) -> str:
        return self.shell.guidenote()


class StepConfigShellPanel(QFrame):
    """Inline card wrapper around exactly the same shell content."""
    close_requested = pyqtSignal()
    saved = pyqtSignal()

    def __init__(
        self, step_number: int, technique_label: str, content_widget: QWidget,
        parent=None, *, description: str = "", guidenote: str = "", accent: str = "blue",
        save_callback: Callable[[str, str], bool] | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumHeight(650)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.shell = StepConfigShell(
            step_number, technique_label, content_widget,
            description=description, guidenote=guidenote, accent=accent, save_callback=save_callback,
        )
        layout.addWidget(self.shell)
        self.header = self.shell.header
        self.content_widget = self.shell.content_widget
        self.close_button = self.shell.close_button
        self.cancel_button = self.shell.cancel_button
        self.save_button = self.shell.save_button
        self.shell.close_requested.connect(self.close_requested.emit)
        self.shell.saved.connect(self.saved.emit)
        self.cancel_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.cancel_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.cancel_shortcut.activated.connect(self.close_requested.emit)

    def description(self) -> str:
        return self.shell.description()

    def guidenote(self) -> str:
        return self.shell.guidenote()

    def set_step_number(self, number: int):
        self.shell.set_step_number(number)
