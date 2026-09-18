from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton


class LinkedStepToggle(QFrame):
    """Choose whether one input uses a local file or an earlier output."""

    mode_changed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("linkedStepToggleContainer")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)

        self.manual_button = self._make_button("Manual File", "manual")
        self.linked_button = self._make_button(
            "Previous Output",
            "linked",
        )
        layout.addWidget(self.manual_button)
        layout.addWidget(self.linked_button)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.button_group.addButton(self.manual_button)
        self.button_group.addButton(self.linked_button)
        self.button_group.buttonClicked.connect(
            lambda button: self.mode_changed.emit(
                str(button.property("sourceMode"))
            )
        )
        self.manual_button.setChecked(True)

    @staticmethod
    def _make_button(text: str, mode: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("linkedStepToggleBtn")
        button.setProperty("sourceMode", mode)
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def mode(self) -> str:
        return "linked" if self.linked_button.isChecked() else "manual"

    def set_mode(self, mode: str) -> None:
        if mode not in {"manual", "linked"}:
            raise ValueError(f"Unsupported source mode: {mode}")
        button = self.linked_button if mode == "linked" else self.manual_button
        button.setChecked(True)

    def is_linked(self) -> bool:
        return self.mode() == "linked"
