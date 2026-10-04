from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, 
    QProgressBar, QPushButton, QVBoxLayout,
)
from PyQt6.QtCore import pyqtSignal


class ExecutionBar(QFrame):
    """Standalone status, progress and action controls."""
    execute_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        loading_status_bar = self.build_loading_status_bar()
        layout.addWidget(loading_status_bar, 1)

        self.execute_embed_btn = QPushButton("Embed Data")
        self.execute_embed_btn.setFixedHeight(50)
        self.execute_embed_btn.setObjectName("PrimaryActionBtn")
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
