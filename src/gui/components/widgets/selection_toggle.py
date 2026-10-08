from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton

from src.gui.components.gui_utils import create_icon_state


class SelectionToggle(QFrame):
    mode_changed = pyqtSignal(str)

    def __init__(self, buttons: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("selectionToggle")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        self.buttons = {}

        for index, button_data in enumerate(buttons):
            text = button_data.get("text", "")
            value = button_data.get("value", text)

            variant = button_data.get("variant", "standalone")
            color_checked = button_data.get("color_checked","#38BDF8")
            icon_path = button_data.get("icon_path")
            icon_size = button_data.get("icon_size", 16)

            button = self.make_button(
                text=text,
                value=value,
                variant=variant,
                color_checked=color_checked,
                icon_path=icon_path,
                icon_size=icon_size,
            )

            self.buttons[value] = button
            self.button_group.addButton(button)
            layout.addWidget(button)

            if index == 0:
                button.setChecked(True)

        self.button_group.buttonClicked.connect(self.on_button_clicked)

    def on_button_clicked(self, button: QPushButton) -> None:
        value = button.property("value")
        self.mode_changed.emit(value)

    @staticmethod
    def make_button(
        text: str,
        value: str,
        variant: str,
        color_checked: str = "#38BDF8",
        icon_path: Path | None = None,
        icon_size: int = 16,
    ) -> QPushButton:

        button = QPushButton(f" {text}")

        button.setObjectName("selectionToggleBtn")
        button.setProperty("value", value)
        button.setProperty("variant", variant)

        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)

        # Icon
        if icon_path is not None:

            if icon_path.exists():
                icon = create_icon_state(
                    str(icon_path),
                    icon_size,
                    color_checked=color_checked,
                )

                button.setIcon(icon)
                button.setIconSize(
                    QSize(icon_size, icon_size)
                )
            else:
                print(f"Icon not found: {icon_path}")

        return button

    def mode(self) -> str | None:
        button = self.button_group.checkedButton()

        if button is None:
            return None

        return button.property("value")

    def set_mode(self, value: str) -> None:
        if value not in self.buttons:
            raise ValueError(
                f"Unsupported mode: {value}"
            )

        self.buttons[value].setChecked(True)
