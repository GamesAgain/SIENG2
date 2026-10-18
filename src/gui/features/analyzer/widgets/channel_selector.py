"""Channel filter used by bit-statistics detail views."""

from collections.abc import Iterable

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)


class ChannelSelector(QWidget):
    """Display the available result channels as exclusive pill buttons."""

    channel_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        label = QLabel("Channel:")
        label.setObjectName("analysisFilterLabel")
        layout.addWidget(label)

        self.button_layout = QHBoxLayout()
        self.button_layout.setSpacing(5)
        layout.addLayout(self.button_layout)
        layout.addStretch()

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        self.hide()

    def set_channels(
        self,
        channels: Iterable[str],
        selected_channel: str | None,
    ) -> None:
        """Replace the pills while preserving the core channel keys."""
        for button in self.buttons.values():
            self.button_group.removeButton(button)
            self.button_layout.removeWidget(button)
            button.hide()
            button.deleteLater()
        self.buttons.clear()

        channel_names = tuple(channels)
        for channel in channel_names:
            button = QPushButton(self.display_name(channel))
            button.setObjectName("analysisChannelButton")
            button.setCheckable(True)
            button.setChecked(channel == selected_channel)
            button.clicked.connect(
                lambda checked, name=channel: checked
                and self.channel_changed.emit(name)
            )
            self.button_group.addButton(button)
            self.buttons[channel] = button
            self.button_layout.addWidget(button)

        self.setVisible(bool(channel_names))

    @staticmethod
    def display_name(channel: str) -> str:
        """Separate a pooled channel from a whole-file result in the GUI."""
        return "All Channels" if channel == "Whole" else channel
