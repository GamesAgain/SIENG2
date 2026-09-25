from PyQt6.QtWidgets import QButtonGroup, QFrame, QLabel, QVBoxLayout,  QPushButton
from PyQt6.QtCore import pyqtSignal, QSize, Qt
from PyQt6.QtGui import QIcon

from src.gui.components.gui_utils import create_icon_pixmap
from src.path import svg_path

# --- Button ICON Path ---
EMBED_ICON = svg_path("lock-plus.svg")
EXTRACT_ICON = svg_path("lock-open.svg")
ANALYZER_ICON = svg_path("file-search.svg")
COMPARE_ICON = svg_path("columns.svg")
KEYS_ICON = svg_path("key.svg")

# --- SideBar Button ---
class SidebarButton(QPushButton):
    
    ICON_SIZE = 22 
    COLOR_NORMAL = "#818D9F"
    COLOR_HOVER = "#E2E7EF"
    COLOR_CHECKED = "#38BDF8"
    
    def __init__(self, text: str, icon_path: str):
        super().__init__(text)
        
        custom_icon = self.create_icon(icon_path)
        
        self.setIcon(custom_icon)
        self.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        self.setFixedHeight(45)
        
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.setObjectName("sidebarButton")
        
    def create_icon(self, icon_path: str) -> QIcon:

        custom_icon = QIcon()
        
        # -- Create pixmaps for different states --
        # Normal State
        pix_normal = create_icon_pixmap(icon_path, self.COLOR_NORMAL, size=self.ICON_SIZE)
        custom_icon.addPixmap(pix_normal, QIcon.Mode.Normal, QIcon.State.Off)
        
        # Hover State
        pix_hover = create_icon_pixmap(icon_path, self.COLOR_HOVER, size=self.ICON_SIZE)
        custom_icon.addPixmap(pix_hover, QIcon.Mode.Active, QIcon.State.Off)
        
        # Checked State
        pix_checked = create_icon_pixmap(icon_path, self.COLOR_CHECKED, size=self.ICON_SIZE)
        custom_icon.addPixmap(pix_checked, QIcon.Mode.Normal, QIcon.State.On)
        custom_icon.addPixmap(pix_checked, QIcon.Mode.Active, QIcon.State.On)
        
        return custom_icon
    
# --- SideBar ---    
class SIENG2SideBar(QFrame):
    
    button_clicked = pyqtSignal(int)
        
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setup_ui()
        
    def setup_ui(self):
        self.setObjectName("sidebar")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 20, 10, 20)
        
        # -- Sidebar Button Group --
        button_group = QButtonGroup(self)
        button_group.setExclusive(True)
        
        # -- Steganography Section --
        layout.addWidget(self.create_section_label("Steganography"))
        embed_btn = SidebarButton("Embed", EMBED_ICON)
        extract_btn = SidebarButton("Extract", EXTRACT_ICON)
        layout.addWidget(embed_btn)
        layout.addWidget(extract_btn)

        button_group.addButton(embed_btn, 0)
        button_group.addButton(extract_btn, 1)
        
        # -- Section Separator --
        layout.addSpacing(16)
        layout.addWidget(self.create_separator_line())
        
        # -- Steganalysis Section --
        layout.addWidget(self.create_section_label("Steganalysis"))
        analyzer_btn = SidebarButton("Analyzer", ANALYZER_ICON)
        compare_btn = SidebarButton("Compare", COMPARE_ICON)
        layout.addWidget(analyzer_btn)
        layout.addWidget(compare_btn)
        
        button_group.addButton(analyzer_btn, 3)
        button_group.addButton(compare_btn, 4)
        
        # -- Section Separator --
        layout.addSpacing(16)
        layout.addWidget(self.create_separator_line())
        
        # -- Utility Section --
        layout.addWidget(self.create_section_label("Utility"))
        self.keys_btn = SidebarButton("Key Management", KEYS_ICON)
        layout.addWidget(self.keys_btn)
        
        button_group.addButton(self.keys_btn, 2)
        
        button_group.idClicked.connect(self.button_clicked)
        
        layout.addStretch()
        
        # -- Default selection --
        embed_btn.setChecked(True)
        
        
    # --- UI helper ---
    def create_section_label(self, text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setObjectName("sectionLabel")
        return label
        
    def create_separator_line(self, color: str = "#282828", height: int = 1) -> QFrame:
        line = QFrame()
        line.setFixedHeight(height)
        line.setFrameShape(QFrame.Shape.NoFrame) 
        line.setStyleSheet(f"background-color: {color}; border: none;")
        return line