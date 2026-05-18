
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QSize, Qt

from src.gui.components.gui_utils import create_icon_pixmap


ICON_SIZE = 22 
COLOR_NORMAL = "#818D9F"
COLOR_HOVER = "#E2E7EF"
COLOR_CHECKED = "#38BDF8"

class SidebarButton(QPushButton):
    def __init__(self, text: str, icon_path: str):
        super().__init__(text)
        
        custom_icon = self.create_icon(icon_path)
        
        self.setIcon(custom_icon)
        self.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.setFixedHeight(45)
        
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.setObjectName("sidebarButton")
        
    def create_icon(self, icon_path: str) -> QIcon:

        custom_icon = QIcon()
        
        # -- Create pixmaps for different states --
        
        # Normal State
        pix_normal = create_icon_pixmap(icon_path, COLOR_NORMAL, size=ICON_SIZE)
        custom_icon.addPixmap(pix_normal, QIcon.Mode.Normal, QIcon.State.Off)
        
        # Hover State
        pix_hover = create_icon_pixmap(icon_path, COLOR_HOVER, size=ICON_SIZE)
        custom_icon.addPixmap(pix_hover, QIcon.Mode.Active, QIcon.State.Off)
        
        # Checked State
        pix_checked = create_icon_pixmap(icon_path, COLOR_CHECKED, size=ICON_SIZE)
        custom_icon.addPixmap(pix_checked, QIcon.Mode.Normal, QIcon.State.On)
        custom_icon.addPixmap(pix_checked, QIcon.Mode.Active, QIcon.State.On)
        
        return custom_icon