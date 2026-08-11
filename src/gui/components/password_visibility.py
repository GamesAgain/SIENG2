"""Reusable show/hide action for password fields."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QLineEdit


def add_password_visibility_toggle(
    line_edit: QLineEdit,
    *linked_line_edits: QLineEdit,
) -> None:
    """Add synchronized show/hide actions to one or more password fields."""

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
    fields = (line_edit, *linked_line_edits)
    actions = []

    def set_visibility(visible: bool) -> None:
        echo_mode = (
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        )
        for field, action in zip(fields, actions):
            field.setEchoMode(echo_mode)
            action.setIcon(visible_icon if visible else hidden_icon)
            action.setToolTip("Hide password" if visible else "Show password")

    for field in fields:
        action = field.addAction(
            hidden_icon,
            QLineEdit.ActionPosition.TrailingPosition,
        )
        action.setObjectName("passwordVisibilityAction")
        action.setToolTip("Show password")
        actions.append(action)

        def toggle_visibility(
            checked: bool = False,
            source: QLineEdit = field,
        ) -> None:
            del checked
            set_visibility(source.echoMode() == QLineEdit.EchoMode.Password)

        action.triggered.connect(toggle_visibility)
