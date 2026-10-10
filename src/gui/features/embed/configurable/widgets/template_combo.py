from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox


class TemplateComboBox(QComboBox):
    popup_opening = pyqtSignal()

    def showPopup(self):
        self.popup_opening.emit()
        super().showPopup()
