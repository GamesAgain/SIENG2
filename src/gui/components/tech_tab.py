from PyQt6.QtWidgets import QLabel, QTabWidget
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QSize
from pathlib import Path

from src.gui.utils import create_tinted_pixmap

# (วางฟังก์ชัน create_tinted_pixmap ของคุณไว้ตรงนี้ หรือ import เข้ามา)

def create_stateful_tab_icon(icon_path):
    """ฟังก์ชันช่วยแพ็ค Icon 2 สี (เทา/ฟ้า) ให้อยู่ในก้อนเดียว"""
    icon = QIcon()
    
    # 1. สถานะปกติ (ไม่ได้เลือก) -> ย้อมสีเทา #64748b
    pix_normal = create_tinted_pixmap(icon_path, "#64748b", size=16)
    icon.addPixmap(pix_normal, QIcon.Mode.Normal, QIcon.State.Off)
    
    # 2. สถานะถูกเลือก (Active/Selected) -> ย้อมสีฟ้า #38bdf8
    pix_active = create_tinted_pixmap(icon_path, "#38bdf8", size=16)
    icon.addPixmap(pix_active, QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(pix_active, QIcon.Mode.Active, QIcon.State.On)
    icon.addPixmap(pix_active, QIcon.Mode.Active, QIcon.State.Off) # เผื่อตอน Hover
    
    return icon

class TechTabWidget(QTabWidget):
    def __init__(self):
        super().__init__()
        
        # 1. สร้าง QTabWidget
        self.setObjectName("techTabs")
        self.setIconSize(QSize(16, 16))
        
        # 2. สร้างหน้าย่อย (เนื้อหาของแต่ละแท็บ)
        self.tab_lsb = QLabel("หน้าฟอร์ม LSB++")
        self.tab_eof = QLabel("หน้าฟอร์ม Locomotive")
        self.tab_meta = QLabel("หน้าฟอร์ม Metadata")
        
        # สมมติโฟลเดอร์ภาพ (ปรับ Path ให้ตรงกับเครื่องคุณ)
        icon_dir = Path(__file__).parent.parent / "assets" / "svg"
        
        # 3. แอดแท็บ พร้อมใส่ Icon อัจฉริยะที่เราแพ็คสีไว้แล้ว
        self.addTab(self.tab_lsb, create_stateful_tab_icon(icon_dir / "binary.svg"), "LSB++")
        self.addTab(self.tab_eof, create_stateful_tab_icon(icon_dir / "train.svg"), "Locomotive") 
        self.addTab(self.tab_meta, create_stateful_tab_icon(icon_dir / "tags.svg"), "Metadata")