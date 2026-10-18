"""Selectable detector card used by the bit-statistics tab."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from src.gui.components.gui_utils import create_icon_pixmap
from src.path import svg_path


class DetectorButton(QPushButton):
    """Display one detector as a colored checkable card."""

    def __init__(
        self,
        name: str,
        description: str,
        badges: tuple[str, ...],
        icon_name: str,
        detector_type: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("DetectorBtn")
        self.setProperty("detectorType", detector_type)
        self.setCheckable(True)
        self.setAccessibleName(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setMinimumHeight(96)

        colors = {
            "chi": "#38BDF8",
            "rs": "#32CA85",
            "spa": "#B47AFA",
        }
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 13, 12, 13)
        layout.setSpacing(12)

        icon = QLabel()
        icon.setPixmap(
            create_icon_pixmap(
                str(svg_path(icon_name)),
                colors[detector_type],
                28,
            )
        )
        icon.setFixedSize(28, 28)
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        name_label = QLabel(name)
        name_label.setObjectName("detectorNameLabel")
        name_label.setProperty("accentColor", detector_type)
        description_label = QLabel(description)
        description_label.setObjectName("detectorDescriptionLabel")
        description_label.setWordWrap(True)
        text_layout.addWidget(name_label)
        text_layout.addWidget(description_label)

        badge_layout = QHBoxLayout()
        badge_layout.setSpacing(6)
        for badge_text in badges:
            badge = QLabel(badge_text)
            badge.setObjectName("detectorBadge")
            badge.setProperty("accentColor", detector_type)
            badge_layout.addWidget(badge)
        badge_layout.addStretch()
        text_layout.addLayout(badge_layout)
        layout.addLayout(text_layout, 1)

        # Let a click on any child label reach the enclosing button.
        for label in self.findChildren(QLabel):
            label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
