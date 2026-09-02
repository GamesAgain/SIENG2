from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config_prototype.gui.paths import ICON_DIR
from src.core.stego.metadata_handlers.png_handler import (
    MAX_KEYWORD_LENGTH,
    PNG_TEXT_KEYWORDS,
)
from src.gui.components.gui_utils import create_icon_pixmap


def _make_tag_badge(text: str) -> QLabel:
    badge = QLabel(text)
    badge.setObjectName("fileInfoBadge")
    badge.setProperty("badgeColor", "neutral")
    return badge


def _make_delete_button() -> QPushButton:
    button = QPushButton()
    button.setObjectName("btnRemoveFile")
    button.setFixedSize(26, 26)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setIcon(
        QIcon(
            create_icon_pixmap(
                ICON_DIR / "x.svg",
                size=12,
                color_hex="#F43F5E",
            )
        )
    )
    return button


class PNGStandardField(QFrame):
    """Always-visible value input for one fixed PNG metadata keyword."""

    def __init__(
        self,
        keyword: str,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.keyword = keyword

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)

        display_name, _description = PNG_TEXT_KEYWORDS.get(
            keyword,
            (keyword, ""),
        )
        self.name_label = QLabel(display_name)
        self.name_label.setObjectName("formLabel")
        self.keyword_badge = _make_tag_badge(keyword)

        header_layout.addWidget(self.name_label)
        header_layout.addWidget(self.keyword_badge)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        self.value_input = QLineEdit()
        self.value_input.setObjectName("formInput")
        layout.addWidget(self.value_input)

    def get_value(self) -> str:
        return self.value_input.text().strip()

    def set_value(self, value: object | None) -> None:
        self.value_input.setText("" if value is None else str(value))

    def is_empty(self) -> bool:
        return not self.get_value()


class PNGCustomRow(QFrame):
    """Editable PNG metadata keyword/value pair that can request removal."""

    removed = pyqtSignal(object)

    def __init__(
        self,
        keyword: str = "",
        value: str = "",
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("fileItemRow")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)

        self.title_label = QLabel("Custom Keyword")
        self.title_label.setObjectName("fileItemName")
        self.delete_button = _make_delete_button()
        self.delete_button.clicked.connect(
            lambda: self.removed.emit(self)
        )

        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.delete_button)
        layout.addLayout(header_layout)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(6)

        self.keyword_input = QLineEdit(keyword)
        self.keyword_input.setObjectName("formInput")
        self.keyword_input.setPlaceholderText("keyword")
        self.keyword_input.setMaxLength(MAX_KEYWORD_LENGTH)
        self.keyword_input.setFixedWidth(220)

        self.value_input = QLineEdit(value)
        self.value_input.setObjectName("formInput")
        self.value_input.setPlaceholderText("value")

        input_layout.addWidget(self.keyword_input)
        input_layout.addWidget(self.value_input, 1)
        layout.addLayout(input_layout)

    def get_keyword(self) -> str:
        return self.keyword_input.text().strip()

    def get_value(self) -> str:
        return self.value_input.text().strip()

    def is_empty(self) -> bool:
        return not self.get_keyword()
