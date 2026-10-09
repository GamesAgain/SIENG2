"""Small widgets shared by the PNG and MP3 metadata editors."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from src.gui.components.gui_utils import create_icon_pixmap
from src.path import svg_path

# QLineEdit ตัดข้อความเกิน 32767 ตัวอักษรทิ้งเงียบ ๆ -> ข้อความลับยาว ๆ จะหาย จึงขยายไว้
MAX_VALUE_LENGTH = 10_000_000


def make_value_input(placeholder: str = "", text: str = "") -> QLineEdit:
    value_input = QLineEdit(text)
    value_input.setObjectName("formInput")
    value_input.setMaxLength(MAX_VALUE_LENGTH)
    value_input.setPlaceholderText(placeholder)
    return value_input


def make_badge(text: str) -> QLabel:
    badge = QLabel(text)
    badge.setObjectName("fileInfoBadge")
    badge.setProperty("badgeColor", "neutral")
    return badge


def make_remove_button(tooltip: str = "Remove") -> QPushButton:
    button = QPushButton()
    button.setObjectName("btnRemoveFile")
    button.setFixedSize(26, 26)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(tooltip)
    button.setIcon(QIcon(create_icon_pixmap(svg_path("x.svg"), size=12, color_hex="#F43F5E")))
    return button


def make_card_header(title: str, icon: str, hint: str, badge: QLabel | None = None) -> QFrame:
    header = QFrame()
    layout = QHBoxLayout(header)
    icon_label = QLabel()
    icon_label.setPixmap(create_icon_pixmap(svg_path(icon), size=16))
    title_label = QLabel(title)
    title_label.setObjectName("cardTitle")
    hint_label = QLabel(hint)
    hint_label.setObjectName("hintLabel")
    layout.addWidget(icon_label)
    layout.addWidget(title_label)
    if badge is not None:
        layout.addWidget(badge)
    layout.addStretch()
    layout.addWidget(hint_label)
    return header


class SecretPreview(QWidget):
    """
    Two short messages above the editor:
    - orange: the file already lists hidden fields (a previous Metadata save); saving replaces that list
    - grey  : the fields the receiver will see (what the user added or modified)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.notice_label = QLabel()
        self.notice_label.setObjectName("metadataNotice")
        self.notice_label.setWordWrap(True)
        self.notice_label.hide()
        layout.addWidget(self.notice_label)

        self.preview_label = QLabel()
        self.preview_label.setObjectName("metadataPreview")
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)
        self.show_changes([])

    def show_changes(self, names: list[str]) -> None:
        if names:
            self.preview_label.setText("Receiver will see: " + ", ".join(names))
        else:
            self.preview_label.setText("No added or modified fields yet. The receiver will see nothing.")

    def show_previous_secret(self, names: list[str]) -> None:
        if not names:
            self.notice_label.hide()
            return
        self.notice_label.setText(
            f"This file already lists hidden fields ({', '.join(names)}). "
            "Saving replaces that list with the fields you add or modify now."
        )
        self.notice_label.show()
