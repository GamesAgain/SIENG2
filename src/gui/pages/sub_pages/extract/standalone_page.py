from pathlib import Path
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFrame, QLabel, QTabWidget, QVBoxLayout

from src.gui.components.gui_utils import create_icon_pixmap
from src.gui.tabs.extract.lsb_extract import LSBExtractTab

ICON_DIR = Path(__file__).parent.parent.parent.parent / "assets" / "svg"
ICON_SIZE = 16

class ExtractStandalonePage(QFrame):
    def __init__(self):
        super().__init__()
        self.setup_ui()
    
    def setup_ui(self):
        self.setObjectName("standalonePage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.tab_lsb = LSBExtractTab()
        self.tab_eof = QLabel("หน้าฟอร์ม Locomotive")
        self.tab_meta = QLabel("หน้าฟอร์ม Metadata")
        
        tech_tabs = QTabWidget()
        tech_tabs.setObjectName("techTabs")
        tech_tabs.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        tech_tabs.addTab(self.tab_lsb, self.create_state_icon(ICON_DIR / "binary.svg", ICON_SIZE), "LSB++")
        tech_tabs.addTab(self.tab_eof, self.create_state_icon(ICON_DIR / "train.svg", ICON_SIZE), "Locomotive") 
        tech_tabs.addTab(self.tab_meta, self.create_state_icon(ICON_DIR / "tags.svg", ICON_SIZE), "Metadata")
        
        layout.addWidget(tech_tabs)
    
    # ----- Icon Helper -----
    def create_state_icon(self, icon_path: str, icon_size: int) -> QIcon:
        color_normal = "#64748B"
        color_checked = "#38BDF8"
        color_hover = "#E2E8F0"
        icon = QIcon()
        
        # --- Create pixmaps for different states ---
        # Normal State
        pix_normal = create_icon_pixmap(icon_path, color_normal, size=icon_size)
        icon.addPixmap(pix_normal, QIcon.Mode.Normal, QIcon.State.Off)
        
        # Hover State
        pix_hover = create_icon_pixmap(icon_path, color_hover, size=icon_size)
        icon.addPixmap(pix_hover, QIcon.Mode.Active, QIcon.State.Off)
        
        # Checked State
        pix_checked = create_icon_pixmap(icon_path, color_checked, size=icon_size)
        icon.addPixmap(pix_checked, QIcon.Mode.Normal, QIcon.State.On)
        icon.addPixmap(pix_checked, QIcon.Mode.Active, QIcon.State.On)
        
        return icon