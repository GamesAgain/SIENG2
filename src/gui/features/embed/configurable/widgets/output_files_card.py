"""'Output Files' card under the Pipeline Builder: the files Save Outputs will save after a run."""
from pathlib import Path

from PyQt6.QtCore import QFileInfo, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFileIconProvider, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, format_file_size, truncate_text_middle
from src.path import svg_path

ICON_SIZE = 16


class OutputFilesCard(QFrame):
    """Hidden until a run finishes. The rows are read-only: saving is done by Save Outputs in the execution bar."""

    clear_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        add_shadow_effect(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        title_layout = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(create_icon_pixmap(svg_path("file-search.svg"), size=ICON_SIZE))
        title = QLabel("Output Files")
        title.setObjectName("cardTitle")
        hint = QLabel("These files are saved by Save Outputs")
        hint.setObjectName("hintLabel")
        title_layout.addWidget(icon)
        title_layout.addWidget(title)
        title_layout.addStretch()
        title_layout.addWidget(hint)
        layout.addLayout(title_layout)

        # Reuse the pipeline canvas background/border (same as the extract page's file list)
        self.canvas = QFrame()
        self.canvas.setObjectName("pipelineCanvas")
        self.rows_layout = QVBoxLayout(self.canvas)
        self.rows_layout.setContentsMargins(8, 8, 8, 8)
        self.rows_layout.setSpacing(8)
        layout.addWidget(self.canvas)

        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("DangerBtn")
        self.clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_button.clicked.connect(self.clear_requested.emit)
        actions = QHBoxLayout()
        actions.addWidget(self.clear_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.hide()

    def show_files(self, files: list[tuple[str, Path]]) -> None:
        """Show (name it is saved as, file) rows. An empty list hides the card."""
        self.clear()
        for name, path in files:
            self.rows_layout.addWidget(self.build_row(name, path))
        self.setVisible(bool(files))

    def clear(self) -> None:
        while self.rows_layout.count():
            row = self.rows_layout.takeAt(0).widget()
            if row is not None:
                row.hide()
                row.deleteLater()
        self.hide()

    def build_row(self, name: str, path: Path) -> QFrame:
        """Read-only row: thumbnail (or the system icon for a non-image), name, size."""
        row = QFrame()
        row.setObjectName("fileItemRow")
        row.setFixedHeight(64)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        icon = QLabel()
        icon.setFixedSize(40, 40)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview = QPixmap(str(path))
        if not preview.isNull():
            icon.setPixmap(preview.scaled(
                40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            system_icon = QFileIconProvider().icon(QFileInfo(name)).pixmap(32, 32)
            # the system may give no icon (e.g. no desktop theme): use the app's file icon so the slot is never empty
            icon.setPixmap(system_icon if not system_icon.isNull() else create_icon_pixmap(svg_path("file.svg"), size=28))

        name_label = QLabel(truncate_text_middle(name, max_length=40))
        name_label.setObjectName("fileItemName")
        name_label.setToolTip(name)
        size_label = QLabel(format_file_size(path.stat().st_size))
        size_label.setObjectName("fileItemSize")
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.addWidget(name_label)
        text_layout.addWidget(size_label)

        layout.addWidget(icon)
        layout.addLayout(text_layout, 1)
        return row
