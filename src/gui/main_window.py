import sys
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from src.gui.components.sidebar_button import SidebarButton
from src.gui.components.title_bar import SIENG2TitleBar
from src.gui.pages.embed_page import EmbedPage
from src.gui.pages.extract_page import ExtractPage
from src.gui.pages.analyzer_page import AnalyzerPage
from src.gui.pages.compare_page import ComparePage
from src.gui.pages.key_management_page import KeyManagementPage
from src.gui.services.key_registry import KeyRegistry

CURRENT_DIR = Path(__file__).resolve().parent
ICON_DIR = CURRENT_DIR / "assets" / "svg"

EMBED_ICON       = str(ICON_DIR / "lock-plus.svg")
EXTRACT_ICON     = str(ICON_DIR / "lock-open.svg")
ANALYZER_ICON = str(ICON_DIR / "file-search.svg")
COMPARE_ICON     = str(ICON_DIR / "columns.svg")
KEYS_ICON        = str(ICON_DIR / "key.svg")


class MainWindow(QMainWindow):
    def __init__(self, key_registry: KeyRegistry | None = None):
        super().__init__()
        self.key_registry = key_registry or KeyRegistry()
        
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        
        self.setWindowTitle("SIENG2")
        self.resize(1280, 720)
        self.setMinimumSize(1024, 700)
        
        self.init_ui()
        
    def init_ui(self):
        
        # -- Root widget --
        root_widget = QFrame()
        root_widget.setObjectName("rootWidget")
        root_layout = QVBoxLayout(root_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        
        # -- Title Bar --
        self.title_bar = SIENG2TitleBar(self)
        root_layout.addWidget(self.title_bar)
        
        # -- Center Container --
        center_widget = QWidget()
        center_widget.setObjectName("centerContainer")
        main_layout = QHBoxLayout(center_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # -- Sidebar --
        sidebar = self.build_sidebar()
        
        # -- Main Content --
        self.page_container = QStackedWidget()
        
        self.page_container.addWidget(EmbedPage(self.key_registry))
        self.page_container.addWidget(ExtractPage(self.key_registry))
        self.page_container.addWidget(KeyManagementPage(self.key_registry))
        self.page_container.addWidget(AnalyzerPage())
        self.page_container.addWidget(ComparePage())
        
        # -- Connect sidebar to page container --
        self.sidebar_group.idClicked.connect(self.page_changed)
        
        # Sidebar and main content layout 20:80
        main_layout.addWidget(sidebar, 2)
        main_layout.addWidget(self.page_container, 8)
        
        root_layout.addWidget(center_widget)
        
        self.setCentralWidget(root_widget)
    
    # -- Event Handlers --
    def page_changed(self, index: int):
        self.page_container.setCurrentIndex(index)
    
    # -- UI Builders --
    def build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebarContainer")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 20, 10, 20)
        
        # -- Sidebar Button Group --
        self.sidebar_group = QButtonGroup(self)
        self.sidebar_group.setExclusive(True)
        
        # -- Steganography Section --
        sidebar_layout.addWidget(self.create_section_label("Steganography"))
        
        self.embed_btn = SidebarButton("Embed", EMBED_ICON)
        self.extract_btn = SidebarButton("Extract", EXTRACT_ICON)
        sidebar_layout.addWidget(self.embed_btn)
        sidebar_layout.addWidget(self.extract_btn)
        
        self.sidebar_group.addButton(self.embed_btn, 0)
        self.sidebar_group.addButton(self.extract_btn, 1)

        sidebar_layout.addSpacing(16)
        sidebar_layout.addWidget(self.create_separator_line())

        # -- Steganalysis Section --
        sidebar_layout.addWidget(self.create_section_label("Steganalysis"))
        
        self.analyzer_btn = SidebarButton("Analyzer", ANALYZER_ICON)
        self.compare_btn = SidebarButton("Compare", COMPARE_ICON)
        sidebar_layout.addWidget(self.analyzer_btn)
        sidebar_layout.addWidget(self.compare_btn)

        self.sidebar_group.addButton(self.analyzer_btn, 3)
        self.sidebar_group.addButton(self.compare_btn, 4)

        # -- Section Separator --
        sidebar_layout.addSpacing(16)
        sidebar_layout.addWidget(self.create_separator_line())

        # -- Utility Section --
        sidebar_layout.addWidget(self.create_section_label("Utility"))

        self.keys_btn = SidebarButton("Key Management", KEYS_ICON)
        sidebar_layout.addWidget(self.keys_btn)
        self.sidebar_group.addButton(self.keys_btn, 2)
        
        sidebar_layout.addStretch()
        
        # -- Default selection --
        self.embed_btn.setChecked(True)
        
        return sidebar
        
    def create_section_label(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setObjectName("sectionLabel")
        return lbl
    
    def create_separator_line(self, color: str = "#282828", height: int = 1) -> QFrame:
        separator_line = QFrame()
        separator_line.setFixedHeight(height)
        separator_line.setFrameShape(QFrame.Shape.NoFrame) 
        separator_line.setStyleSheet(f"background-color: {color}; border: none;")
        return separator_line


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
