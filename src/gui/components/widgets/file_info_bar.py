from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from src.gui.components.gui_utils import create_icon_pixmap
from src.path import svg_path


class FileInfoBar(QFrame):
    """Selected-file summary with a change-file action."""

    change_file_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fileInfoCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        icon_box = QFrame()
        icon_box.setObjectName("fileInfoIconBox")
        icon_box.setFixedSize(44, 44)
        icon_layout = QVBoxLayout(icon_box)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        self.file_icon = QLabel()
        self.file_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_layout.addWidget(self.file_icon)
        layout.addWidget(icon_box)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        self.file_name = QLabel()
        self.file_name.setObjectName("fileInfoName")
        self.file_detail = QLabel()
        self.file_detail.setObjectName("fileInfoDetail")
        text_layout.addWidget(self.file_name)
        text_layout.addWidget(self.file_detail)
        layout.addLayout(text_layout)
        layout.addStretch()

        self.badge_layout = QHBoxLayout()
        self.badge_layout.setSpacing(6)
        layout.addLayout(self.badge_layout)

        self.change_file_button = QPushButton("Change File")
        self.change_file_button.setObjectName("SecondaryBtn")
        self.change_file_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change_file_button.clicked.connect(self.change_file_requested.emit)
        layout.addWidget(self.change_file_button)

    def add_extra_button(self, text: str) -> QPushButton:
        """Add a page-specific action before Change File."""
        button = QPushButton(text)
        button.setObjectName("SecondaryBtn")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        index = self.layout().indexOf(self.change_file_button)
        self.layout().insertWidget(index, button)
        return button

    def update_info(
        self,
        file_path: str,
        display_name: str,
        detail: str,
        badges: list[tuple[str, str]],
    ) -> None:
        """Update file details and replace its format/status badges."""
        self.file_name.setText(display_name)
        self.file_name.setToolTip(str(file_path))
        self.file_detail.setText(detail)

        while self.badge_layout.count():
            item = self.badge_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.deleteLater()

        for label_text, color in badges:
            badge = QLabel(label_text)
            badge.setObjectName("fileInfoBadge")
            badge.setProperty("badgeColor", color)
            self.badge_layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)

        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            pixmap = create_icon_pixmap(str(svg_path("file-search.svg")), "#38BDF8", 28)
        self.file_icon.setPixmap(pixmap.scaled(
            40, 40, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
