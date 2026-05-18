from PyQt6.QtWidgets import QCheckBox
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen
from PyQt6.QtCore import Qt, QPropertyAnimation, pyqtProperty

# ==========================================
# 1. คลาส ToggleSwitch ของเรา
# ==========================================
class ToggleSwitch(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self._thumb_pos = 2 
        
        self.animation = QPropertyAnimation(self, b"thumb_pos")
        self.animation.setDuration(150) 
        self.stateChanged.connect(self.start_transition)

    @pyqtProperty(float)
    def thumb_pos(self):
        return self._thumb_pos

    @thumb_pos.setter
    def thumb_pos(self, pos):
        self._thumb_pos = pos
        self.update() 

    def start_transition(self, state):
        self.animation.stop()
        if state:
            self.animation.setEndValue(18) 
        else:
            self.animation.setEndValue(2)  
        self.animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing) 

        bg_off = QColor("#2e2e2e")  
        bg_on = QColor("#0284c7")   
        border_off = QColor(56, 189, 248, 51) 
        border_on = QColor("#38bdf8") 
        thumb_off = QColor("#64748b") 
        thumb_on = QColor("#ffffff")  

        state = self.isChecked()
        
        # 1. วาดพื้นหลัง (Capsule)
        bg_color = bg_on if state else bg_off
        border_color = border_on if state else border_off

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1.5))
        
        painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 9, 9)

        # 2. วาดวงกลม (Thumb)
        thumb_color = thumb_on if state else thumb_off
        painter.setBrush(QBrush(thumb_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(self._thumb_pos), 2, 16, 16)
        
        painter.end()

    def hitButton(self, pos):
        return self.contentsRect().contains(pos)