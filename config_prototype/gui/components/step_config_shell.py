from collections.abc import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class StepConfigHeader(QFrame):
    """Editable description and receiver note shared by both shell variants."""

    def __init__(
        self,
        step_number: int,
        technique_label: str,
        description: str,
        guidenote: str,
        accent: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        self.title_label = QLabel(f"Step {step_number} :")
        self.title_label.setObjectName("cardTitle")
        title_row.addWidget(self.title_label)

        self.technique_label = QLabel(technique_label)
        self.technique_label.setObjectName("prototypeStepConfigTechnique")
        self.technique_label.setProperty("accentColor", accent)
        title_row.addWidget(self.technique_label)
        title_row.addStretch()

        description_label = QLabel("Description")
        description_label.setObjectName("formLabel")
        title_row.addWidget(description_label)

        self.description_edit = QLineEdit(description)
        self.description_edit.setObjectName("formInput")
        self.description_edit.setPlaceholderText("Describe what this step does")
        self.description_edit.setFixedWidth(300)
        title_row.addWidget(self.description_edit)
        layout.addLayout(title_row)

        guidenote_row = QHBoxLayout()
        guidenote_row.setSpacing(8)
        guidenote_label = QLabel("GuideNote")
        guidenote_label.setObjectName("formLabel")
        guidenote_row.addWidget(guidenote_label)

        self.guidenote_edit = QLineEdit(guidenote)
        self.guidenote_edit.setObjectName("formInput")
        self.guidenote_edit.setPlaceholderText(
            "Optional hint shown to the receiver while extracting this step"
        )
        guidenote_row.addWidget(self.guidenote_edit, 1)
        layout.addLayout(guidenote_row)

    def description(self) -> str:
        return self.description_edit.text().strip()

    def guidenote(self) -> str:
        return self.guidenote_edit.text().strip()


class StepConfigShell(QWidget):
    """Shared step identity and content host without technique logic."""

    save_requested = pyqtSignal()
    cancel_requested = pyqtSignal()

    def __init__(
        self,
        step_number: int,
        technique_label: str,
        description: str,
        accent: str,
        guidenote: str = "",
        content_widget: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.step_number = step_number
        self.technique_label_text = technique_label
        self.build_ui(
            description,
            guidenote,
            accent,
            content_widget,
        )

    def build_ui(
        self,
        description: str,
        guidenote: str,
        accent: str,
        content_widget: QWidget | None,
    ) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        self.header = StepConfigHeader(
            self.step_number,
            self.technique_label_text,
            description,
            guidenote,
            accent,
        )
        self.title_label = self.header.title_label
        self.technique_label = self.header.technique_label
        self.description_edit = self.header.description_edit
        self.guidenote_edit = self.header.guidenote_edit
        layout.addWidget(self.header)

        self.content_frame = QFrame()
        self.content_frame.setObjectName("prototypeStepConfigContent")
        content_layout = QVBoxLayout(self.content_frame)
        content_layout.setContentsMargins(16, 16, 16, 16)

        self.content_widget = content_widget
        self.placeholder_label: QLabel | None = None
        if self.content_widget is None:
            self.placeholder_label = QLabel(
                "Technique configuration form will appear here."
            )
            self.placeholder_label.setObjectName("pipelineEmpty")
            self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            content_layout.addWidget(self.placeholder_label)
        else:
            content_layout.addWidget(self.content_widget)
            self.content_widget.show()
        layout.addWidget(self.content_frame, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("SecondaryBtn")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        button_row.addWidget(self.cancel_button)

        self.save_button = QPushButton("Save Step")
        self.save_button.setObjectName("PrimaryActionBtn")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.clicked.connect(self.save_requested.emit)
        self.save_button.setDefault(True)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

    def description(self) -> str:
        return self.header.description()

    def guidenote(self) -> str:
        return self.header.guidenote()


class StepConfigShellDialog(QDialog):
    """Popup host for the shared step configuration shell."""

    def __init__(
        self,
        step_number: int,
        technique_label: str,
        description: str,
        accent: str,
        guidenote: str = "",
        content_widget: QWidget | None = None,
        save_callback: Callable[[str, str], bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.step_number = step_number
        self.technique_label_text = technique_label
        self.setObjectName("stepConfigShellDialog")
        self.setWindowTitle(f"Configure Step {step_number} - {technique_label}")
        self.setModal(True)
        self.setMinimumSize(900, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.shell = StepConfigShell(
            step_number,
            technique_label,
            description,
            accent,
            guidenote,
            content_widget,
        )
        self._save_callback = save_callback
        self.shell.cancel_requested.connect(self.reject)
        self.shell.save_requested.connect(self._try_save)
        self.cancel_button = self.shell.cancel_button
        self.save_button = self.shell.save_button
        layout.addWidget(self.shell)

    def _try_save(self) -> None:
        if self._save_callback is None:
            return
        if self._save_callback(
            self.shell.description(),
            self.shell.guidenote(),
        ):
            self.accept()


class StepConfigShellPanel(QFrame):
    """Inline host for the same shell content used by the popup."""

    saved = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(
        self,
        step_number: int,
        technique_label: str,
        description: str,
        accent: str,
        guidenote: str = "",
        content_widget: QWidget | None = None,
        save_callback: Callable[[str, str], bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.step_number = step_number
        self.technique_label_text = technique_label
        self.setObjectName("card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.shell = StepConfigShell(
            step_number,
            technique_label,
            description,
            accent,
            guidenote,
            content_widget,
        )
        self._save_callback = save_callback
        self.shell.cancel_requested.connect(self.cancelled.emit)
        self.shell.save_requested.connect(self._try_save)
        self.cancel_button = self.shell.cancel_button
        self.save_button = self.shell.save_button
        layout.addWidget(self.shell)

    def _try_save(self) -> None:
        if self._save_callback is None:
            return
        if self._save_callback(
            self.shell.description(),
            self.shell.guidenote(),
        ):
            self.saved.emit()
