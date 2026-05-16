
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtGui import QIcon, QPainter, QColor
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPixmap

from src.gui.utils import create_tinted_pixmap

ICON_SIZE = 22 
class SidebarButton(QPushButton):
    def __init__(self, text, icon_path):
        super().__init__(text)
        
        color_normal = "#94a3b8"   # --text2
        color_hover = "#e2e8f0"    # --text
        color_checked = "#38bdf8"  # --cyan

        custom_icon = QIcon()
        
        pix_normal = create_tinted_pixmap(icon_path, color_normal, size=ICON_SIZE)
        custom_icon.addPixmap(pix_normal, QIcon.Mode.Normal, QIcon.State.Off)
        
        pix_hover = create_tinted_pixmap(icon_path, color_hover, size=ICON_SIZE)
        custom_icon.addPixmap(pix_hover, QIcon.Mode.Active, QIcon.State.Off)
        
        pix_checked = create_tinted_pixmap(icon_path, color_checked, size=ICON_SIZE)
        custom_icon.addPixmap(pix_checked, QIcon.Mode.Normal, QIcon.State.On)
        custom_icon.addPixmap(pix_checked, QIcon.Mode.Active, QIcon.State.On)
        
        self.setIcon(custom_icon)
        self.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.setFixedHeight(45)
        
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.setObjectName("sidebarButton")