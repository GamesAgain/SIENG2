"""Reusable show/hide action for password fields."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QLineEdit


def add_password_visibility_toggle(line_edit: QLineEdit) -> None:
    """Add a show/hide action to a password field."""

    def create_eye_icon(is_open: bool) -> QIcon:
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#94A3B8")
        painter.setPen(QPen(color, 2))

        painter.drawEllipse(2, 6, 20, 12)
        if is_open:
            painter.setBrush(color)
            painter.drawEllipse(10, 10, 4, 4)
        else:
            painter.drawLine(4, 4, 20, 20)

        painter.end()
        return QIcon(pixmap)

    visible_icon = create_eye_icon(True)
    hidden_icon = create_eye_icon(False)
    action = line_edit.addAction(
        hidden_icon,
        QLineEdit.ActionPosition.TrailingPosition,
    )
    action.setObjectName("passwordVisibilityAction")
    action.setToolTip("Show password")

    def toggle_visibility() -> None:
        is_hidden = line_edit.echoMode() == QLineEdit.EchoMode.Password
        line_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if is_hidden else QLineEdit.EchoMode.Password
        )
        action.setIcon(visible_icon if is_hidden else hidden_icon)
        action.setToolTip("Hide password" if is_hidden else "Show password")

    action.triggered.connect(toggle_visibility)
