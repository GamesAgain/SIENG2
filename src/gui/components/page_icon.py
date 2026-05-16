from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt
from src.gui.utils import create_tinted_pixmap

class PageIcon(QLabel):
    def __init__(self, icon_path, theme_color="#38bdf8", bg_color="rgba(56, 189, 248, 0.10)", border_color="rgba(56, 189, 248, 0.22)"):
        super().__init__()
        
        # 1. กำหนดขนาดกล่องให้เท่า HTML (36x36) และจัดไอคอนให้อยู่กึ่งกลาง
        self.setFixedSize(36, 36)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 2. นำไอคอนมาย้อมสีตาม Theme (ขนาดไอคอนประมาณ 18-20px กำลังสวย)
        pixmap = create_tinted_pixmap(icon_path, theme_color, size=18)
        self.setPixmap(pixmap)
        
        # 3. ใส่ CSS ตกแต่งกล่องพื้นหลังและขอบมน
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
        """)