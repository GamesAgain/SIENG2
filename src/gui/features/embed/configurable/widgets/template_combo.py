from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox


class TemplateComboBox(QComboBox):
    popup_opening = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Let Qt shorten only the text that does not fit the actual row width.
        self.view().setTextElideMode(Qt.TextElideMode.ElideMiddle)

    def showPopup(self):
        self.popup_opening.emit()
        super().showPopup()
