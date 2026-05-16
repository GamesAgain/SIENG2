from pathlib import Path
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout

from src.gui.components.page_icon import PageIcon
from src.gui.components.tech_tab import TechTabWidget
from src.gui.utils import create_tinted_pixmap

class EmbedPage(QFrame):
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)
        
        # ส่วน Header (ชื่อหน้าและคำอธิบาย)
        # --- 2. ส่วน Header ---
        header_widget = QFrame()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12) # ระยะห่างระหว่าง Icon กับ Text
        
        # 2.1 ใส่ Icon กล่องสีฟ้า
        ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "svg"
        embed_icon = PageIcon(ICON_DIR / "lock-plus.svg") # ใช้สีฟ้า (Cyan) เป็นค่าเริ่มต้นอยู่แล้ว
        header_layout.addWidget(embed_icon)
        
        # 2.2 ใส่ Text (Title & Description)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        title_lbl = QLabel("Embed — Data Hiding")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #e2e8f0;")
        
        desc_lbl = QLabel("Select embedding mode: Standalone or Configurable Pipeline")
        desc_lbl.setStyleSheet("font-size: 11px; color: #64748b;")
        
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(desc_lbl)
        
        header_layout.addLayout(text_layout)
        header_layout.addStretch() # ดันให้ชิดซ้าย
        
        # นำ Header ไปใส่ใน Layout หลัก
        main_layout.addWidget(header_widget)
        
        # ส่วนปุ่มสลับ Mode (Standalone / Configurable)
        mode_switch_widget = self.create_mode_switch()
        main_layout.addWidget(mode_switch_widget)
        
        # Mode Stack [Standalone, Configurable]
        self.mode_stack = QStackedWidget()
        main_layout.addWidget(self.mode_stack)
        
        # หน้า Standalone Mode
        standalone_widget = QFrame()
        standalone_layout = QVBoxLayout(standalone_widget)
        standalone_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tech_tabs = TechTabWidget()
        standalone_layout.addWidget(self.tech_tabs)

        # หน้า Configurable Pipeline Mode (รอสร้าง)
        pipeline_widget = QLabel("หน้าต่าง Configurable Pipeline")
        pipeline_widget.setStyleSheet("color: #94a3b8;")
        
        self.mode_stack.addWidget(standalone_widget)
        self.mode_stack.addWidget(pipeline_widget)
        
        self.mode_group.idClicked.connect(self.mode_changed)
        
        main_layout.addStretch()

    def mode_changed(self, index: int):
        self.mode_stack.setCurrentIndex(index)
    
    # --- สร้างส่วน Mode Switch ---
    def create_mode_switch(self):
        mode_container = QFrame()
        mode_container.setObjectName("modeSwitchContainer")
        
        layout = QHBoxLayout(mode_container)
        layout.setContentsMargins(3, 3, 3, 3) 
        layout.setSpacing(3)
        
        # สมมติโฟลเดอร์รูปภาพ (ปรับให้ตรงกับโครงสร้างจริงของคุณ)
        ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "svg"

        # 2. สร้างปุ่มที่ 1 (Standalone)
        self.btn_standalone = QPushButton(" Standalone Mode") 
        self.btn_standalone.setObjectName("modeBtn")
        self.btn_standalone.setCheckable(True)
        self.btn_standalone.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # ใส่ Icon
        tool_icon = ICON_DIR / "tool.svg"
        if tool_icon.exists():
            self.btn_standalone.setIcon(create_stateful_icon(tool_icon))
            self.btn_standalone.setIconSize(QSize(14, 14))
            
        self.btn_standalone.setChecked(True)

        # 3. สร้างปุ่มที่ 2 (Configurable)
        self.btn_configurable = QPushButton(" Configurable Pipeline")
        self.btn_configurable.setObjectName("modeBtn")
        self.btn_configurable.setCheckable(True)
        self.btn_configurable.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # ใส่ Icon
        branch_icon = ICON_DIR / "git-branch.svg"
        if branch_icon.exists():
            self.btn_configurable.setIcon(create_stateful_icon(branch_icon))
            self.btn_configurable.setIconSize(QSize(14, 14))

        # 4. จับปุ่มเข้ากลุ่ม เพื่อให้กดได้ทีละปุ่ม (Exclusive Toggle)
        self.mode_group = QButtonGroup()
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.btn_standalone, 0)
        self.mode_group.addButton(self.btn_configurable, 1)

        # นำปุ่มใส่ลงใน Layout
        layout.addWidget(self.btn_standalone)
        layout.addWidget(self.btn_configurable)

        return mode_container
    
def create_stateful_icon(icon_path):
    icon = QIcon()
    # 1. สีปกติ (ไม่ได้เลือก) -> สีเทา #94a3b8
    pix_normal = create_tinted_pixmap(icon_path, "#94a3b8", size=14)
    icon.addPixmap(pix_normal, QIcon.Mode.Normal, QIcon.State.Off)
    
    # 2. สีตอนเลือก (Checked) หรือ Hover -> สีฟ้า #38bdf8
    pix_active = create_tinted_pixmap(icon_path, "#38bdf8", size=14)
    icon.addPixmap(pix_active, QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(pix_active, QIcon.Mode.Active, QIcon.State.Off) # ตอนเมาส์ชี้
    icon.addPixmap(pix_active, QIcon.Mode.Active, QIcon.State.On)
    return icon