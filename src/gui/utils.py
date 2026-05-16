# ---------------------------------------------------------
# ฟังก์ชันสำหรับย้อมสี Icon (Tinting)
# ---------------------------------------------------------
from PyQt6.QtGui import QPixmap, QPainter, QIcon, QColor
from PyQt6.QtCore import Qt


def create_tinted_pixmap(icon_path, color_hex, size=22): 
    tinted = QPixmap(size, size)
    tinted.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(tinted)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    
    icon = QIcon(str(icon_path))
    icon.paint(painter, 0, 0, size, size, Qt.AlignmentFlag.AlignCenter)
    
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), QColor(color_hex))
    painter.end()
    
    return tinted