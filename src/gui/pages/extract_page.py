from pathlib import Path
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton, QStackedWidget, QVBoxLayout, QLabel

from src.gui.components.gui_utils import create_icon_state
from src.gui.pages.sub_pages.extract.standalone_page import ExtractStandalonePage

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "svg"
MODE_ICON_SIZE = 16
MODE_ICON_COLOR_NORMAL = "#94A3B8"
MODE_ICON_COLOR_CHECKED_STANDALONE = "#38BDF8"
MODE_ICON_COLOR_CHECKED_CONFIGURABLE = "#F59E0F"

class ExtractPage(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("extractPage")
        self.init_ui()
    
    def init_ui(self):
        
        main_layout = QVBoxLayout(self)
        
        # Mode Selection
        self.mode_selection = self.build_mode_selection()
        main_layout.addWidget(self.mode_selection)
        
        # --- BUTTON GROUP ---
        self.mode_group = QButtonGroup()
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.btn_standalone, 0)
        self.mode_group.addButton(self.btn_configurable, 1)
        
        # Mode Stack 
        self.mode_stack = QStackedWidget()
        
        self.mode_stack.addWidget(ExtractStandalonePage())
        self.mode_stack.addWidget(self.build_configurable_mode())
        
        self.mode_group.idClicked.connect(self.mode_stack.setCurrentIndex)
        main_layout.addWidget(self.mode_selection)
        main_layout.addSpacing(10)
        main_layout.addWidget(self.mode_stack)
        
    def build_mode_selection(self):
        
        mode_selection = QFrame()
        mode_selection.setObjectName("modeSelectionContainer")
        
        mode_layout = QHBoxLayout(mode_selection)
        mode_layout.setContentsMargins(3, 3, 3, 3) 
        mode_layout.setSpacing(3)
        
        # --- STANDALONE MODE BUTTON ---
        self.btn_standalone = QPushButton(" Standalone Mode") 
        self.btn_standalone.setObjectName("modeStandaloneBtn")
        self.btn_standalone.setCheckable(True)
        self.btn_standalone.setCursor(Qt.CursorShape.PointingHandCursor)
        # ADD ICON
        standalone_icon_path = ICON_DIR / "tool.svg"
        if standalone_icon_path.exists():
            standalone_icon = create_icon_state(str(standalone_icon_path), MODE_ICON_SIZE, color_checked=MODE_ICON_COLOR_CHECKED_STANDALONE)
            self.btn_standalone.setIcon(standalone_icon)
            self.btn_standalone.setIconSize(QSize(MODE_ICON_SIZE, MODE_ICON_SIZE))
        
        # --- CONFIGURABLE PIPELINE BUTTON ---
        self.btn_configurable = QPushButton(" Configurable Pipeline")
        self.btn_configurable.setObjectName("modeConfigurableBtn")
        self.btn_configurable.setCheckable(True)
        self.btn_configurable.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # ADD ICON
        configurable_icon_path = ICON_DIR / "git-branch.svg"
        if configurable_icon_path.exists():
            configurable_icon = create_icon_state(str(configurable_icon_path), MODE_ICON_SIZE, color_checked=MODE_ICON_COLOR_CHECKED_CONFIGURABLE)
            self.btn_configurable.setIcon(configurable_icon)
            self.btn_configurable.setIconSize(QSize(MODE_ICON_SIZE, MODE_ICON_SIZE))
        
        mode_layout.addWidget(self.btn_standalone)
        mode_layout.addWidget(self.btn_configurable)
        
        # Set default selection
        self.btn_standalone.setChecked(True)
        
        return mode_selection
    
    def build_configurable_mode(self):
        placeholder = QLabel("Configurable Mode Placeholder")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return placeholder
