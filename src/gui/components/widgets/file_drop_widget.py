from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
from PyQt6.QtWidgets import QFileDialog, QFrame, QLabel, QVBoxLayout

from src.gui.components.gui_utils import create_icon_pixmap
from src.path import svg_path


class FileDropWidget(QFrame):
    """Clickable, single-file drop zone for local files."""

    file_selected = pyqtSignal(str)

    def __init__(self, allowed_extensions: tuple[str, ...] = (".png",), parent=None):
        super().__init__(parent)
        self.allowed_extensions = tuple(ext.lower() for ext in allowed_extensions)
        self.file_path: str | None = None

        self.setObjectName("fileDropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(5)

        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(create_icon_pixmap(str(svg_path("file.svg")), "#94A3B8", 30))
        layout.addWidget(icon)

        title = QLabel("Drop file here or click to browse")
        title.setObjectName("mainLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        supported = " ".join(self.allowed_extensions)
        subtitle = QLabel(f"Supported: {supported}")
        subtitle.setObjectName("subLabel")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

    def select_file(self, file_path: str) -> bool:
        """Accept an existing file of an allowed type and emit its path."""
        path = Path(file_path)
        if not path.is_file() or path.suffix.lower() not in self.allowed_extensions:
            return False
        self.file_path = str(path)
        self.file_selected.emit(self.file_path)
        return True

    def clear_file(self) -> None:
        self.file_path = None

    def browse_file(self) -> None:
        patterns = " ".join(f"*{ext}" for ext in self.allowed_extensions)
        file_path, _ = QFileDialog.getOpenFileName(self, "Select file", "", f"Supported files ({patterns})")
        if file_path:
            self.select_file(file_path)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.browse_file()
        else:
            super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            path = Path(urls[0].toLocalFile())
            if path.is_file() and path.suffix.lower() in self.allowed_extensions:
                event.acceptProposedAction()
                self.setProperty("isDragging", True)
                self.style().unpolish(self)
                self.style().polish(self)
                return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("isDragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("isDragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        urls = event.mimeData().urls()
        if len(urls) == 1 and self.select_file(urls[0].toLocalFile()):
            event.acceptProposedAction()
        else:
            event.ignore()
