# src/gui/components/title_bar.py

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import QSize, Qt
from pathlib import Path

from src.gui.utils import create_tinted_pixmap

CURRENT_DIR = Path(__file__).resolve().parent
ICON_DIR = CURRENT_DIR.parent / "assets" / "svg"

class SIENG2TitleBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)  # ความสูงตาม HTML var(--header-h)
        self.setObjectName("titleBar")
        
        # ตัวแปรสำหรับจำตำแหน่งเมาส์ตอนลากหน้าต่าง
        self._start_pos = None
        
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        # โลโก้ (สร้างเป็นกล่องสีฟ้าตามภาพ)
        self.logo_mark = QLabel()
        self.logo_mark.setFixedSize(28, 28)
        self.logo_mark.setObjectName("logoMark")
        layout.addWidget(self.logo_mark)

        # ชื่อโปรแกรมและซับไตเติ้ล
        title_layout = QVBoxLayout()
        title_layout.setSpacing(0)
        title_layout.setContentsMargins(0, 8, 0, 8)
        
        self.app_title = QLabel("SIENG2")
        self.app_title.setObjectName("appTitle")
        self.app_subtitle = QLabel("Secure Incognito ENcryption Guard")
        self.app_subtitle.setObjectName("appSubtitle")
        
        title_layout.addWidget(self.app_title)
        title_layout.addWidget(self.app_subtitle)
        layout.addLayout(title_layout)

        # ดันของที่เหลือไปชิดขวา
        layout.addStretch()

        # Window Controls: ย่อ (Minimize), ขยาย (Maximize), ปิด (Close)
        self.btn_minimize = QPushButton("—")
        self.btn_minimize.setObjectName("windowControlBtn")
        self.btn_minimize.clicked.connect(self.window().showMinimized)
        
        self.btn_maximize = QPushButton("☐")
        self.btn_maximize.setObjectName("windowControlBtn")
        self.btn_maximize.clicked.connect(self.toggle_maximize)
        
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("windowCloseBtn")
        self.btn_close.clicked.connect(self.window().close)

        for btn in [self.btn_minimize, self.btn_maximize, self.btn_close]:
            btn.setFixedSize(36, 32)
            layout.addWidget(btn)

    # --- ฟังก์ชันสลับ ย่อ/ขยาย หน้าต่าง ---
    def toggle_maximize(self):
        if self.window().isMaximized():
            self.window().showNormal()
        else:
            self.window().showMaximized()

    # --- ฟังก์ชันระบบลากหน้าต่าง (Drag to Move) ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self._start_pos is not None:
            # คำนวณระยะที่เมาส์ขยับ แล้วย้ายหน้าต่างตาม
            delta = event.position().toPoint() - self._start_pos
            self.window().move(self.window().pos() + delta)

    def mouseReleaseEvent(self, event):
        self._start_pos = None
        
    def mouseDoubleClickEvent(self, event):
        # ดับเบิ้ลคลิกที่ Title Bar เพื่อขยายหน้าต่าง
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()