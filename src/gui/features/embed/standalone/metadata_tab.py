from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

class MetadataStandaloneTab(QFrame):
    """Placeholder: Metadata is being rebuilt from the core up (the old version is kept in ref_metadata/)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        panel = QFrame()
        panel.setObjectName("pipelineCanvas")  # same dark panel as the other empty states
        panel_layout = QVBoxLayout(panel)
        message = QLabel("Metadata is being rebuilt and is not available yet.")
        message.setObjectName("pipelineEmpty")
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setWordWrap(True)
        panel_layout.addWidget(message)

        layout.addWidget(panel, 1)
