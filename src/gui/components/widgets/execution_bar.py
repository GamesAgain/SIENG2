from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, 
    QProgressBar, QPushButton, QVBoxLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon

from src.gui.components.gui_utils import create_icon_pixmap
from src.path import svg_path


class ExecutionBar(QFrame):
    """Shared status, progress and action controls for execution pages."""
    execute_requested = pyqtSignal()
    
    def __init__(self, text_active_button: str = "Embed Data", parent=None, *, is_config: bool = False):
        super().__init__(parent)
        self.text_active_button = text_active_button
        self.is_config = is_config
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        loading_status_bar = self.build_loading_status_bar()
        layout.addWidget(loading_status_bar, 1)

        # Pipeline delivery will enable this button after a successful run.
        self.save_outputs_btn = QPushButton(" Save Outputs")
        self.save_outputs_btn.setObjectName("SecondaryBtn")
        self.save_outputs_btn.setProperty("textColor", "white")
        self.save_outputs_btn.setFixedHeight(50)
        self.save_outputs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_outputs_btn.setIcon(QIcon(create_icon_pixmap(svg_path("upload.svg"), "#FFFFFF", size=16)))
        self.save_outputs_btn.setVisible(self.is_config)
        self.save_outputs_btn.setEnabled(False)
        layout.addWidget(self.save_outputs_btn, 0)
        # TODO: Add a Save Outputs signal when pipeline delivery is implemented.
        # self.save_outputs_btn.clicked.connect(self.save_outputs_requested.emit)

        self.execute_embed_btn = QPushButton(self.text_active_button)
        self.execute_embed_btn.setFixedHeight(50)
        self.execute_embed_btn.setObjectName("PrimaryActionBtn")
        self.execute_embed_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.execute_embed_btn, 0)
        self.execute_embed_btn.clicked.connect(self.execute_requested.emit)

    def build_loading_status_bar(self):
        loading_status_bar = QFrame()
        loading_status_bar.setObjectName("card")
        loading_status_bar_layout = QVBoxLayout(loading_status_bar)

        self.status_label = QLabel("Status: Ready")
        self.status_label.setObjectName("statusLabel")
        loading_status_bar_layout.addWidget(self.status_label)

        self.loading_bar = QProgressBar()
        self.loading_bar.setObjectName("loadingIndicator")
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setFixedHeight(10)
        self.loading_bar.setRange(0, 100)
        self.loading_bar.setValue(0)
        loading_status_bar_layout.addWidget(self.loading_bar)

        return loading_status_bar
    
    def update_progress(self, percent, message):
        self.loading_bar.setValue(percent)
        self.status_label.setText(f"Status: {message}")

    def set_busy(self, busy):
        self.execute_embed_btn.setEnabled(not busy)

    def reset(self):
        self.loading_bar.setValue(0)
        self.status_label.setText("Status: Ready")
