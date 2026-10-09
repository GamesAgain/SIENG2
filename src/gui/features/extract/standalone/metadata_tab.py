from PyQt6.QtWidgets import QFrame, QVBoxLayout

from src.gui.features.extract.forms.metadata_form import MetadataExtractForm


class MetadataStandaloneTab(QFrame):
    """Extract Metadata: no password and no run step (metadata is plain text), so the form reads the file as soon as it is chosen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.form = MetadataExtractForm()
        layout.addWidget(self.form, 1)
