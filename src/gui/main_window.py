import sys
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from src.gui.components.sidebar_button import SidebarButton
from src.gui.components.title_bar import SIENG2TitleBar
from src.gui.pages.embed_page import EmbedPage

CURRENT_DIR = Path(__file__).resolve().parent
ICON_DIR = CURRENT_DIR / "assets" / "svg"

EMBED_ICON       = str(ICON_DIR / "lock-plus.svg")
EXTRACT_ICON     = str(ICON_DIR / "lock-open.svg")
FILE_STRUCT_ICON = str(ICON_DIR / "file-search.svg")
METADATA_ICON    = str(ICON_DIR / "tag.svg")
BIT_STAT_ICON    = str(ICON_DIR / "chart-histogram.svg")
COMPARE_ICON     = str(ICON_DIR / "columns.svg")
REPORT_ICON      = str(ICON_DIR / "report.svg")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
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
        
        self.page_container.addWidget(EmbedPage())
        self.page_container.addWidget(QLabel("Extract Page"))
        self.page_container.addWidget(QLabel("File Structure Page"))
        self.page_container.addWidget(QLabel("Metadata Page"))
        self.page_container.addWidget(QLabel("Bit Statistics Page"))
        self.page_container.addWidget(QLabel("Compare Page"))
        self.page_container.addWidget(QLabel("Report Page"))
        
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
        
        
        # -- Section Separator --
        sidebar_layout.addSpacing(16)
        sidebar_layout.addWidget(self.create_separator_line())
        
        # -- Steganalysis Section --
        sidebar_layout.addWidget(self.create_section_label("Steganalysis"))
        
        self.file_struct_btn = SidebarButton("File Structure", FILE_STRUCT_ICON)
        self.metadata_btn = SidebarButton("Metadata", METADATA_ICON)
        self.bit_stat_btn = SidebarButton("Bit Statistics", BIT_STAT_ICON)
        self.compare_btn = SidebarButton("Compare", COMPARE_ICON)
        self.report_btn = SidebarButton("Report", REPORT_ICON)
        sidebar_layout.addWidget(self.file_struct_btn)
        sidebar_layout.addWidget(self.metadata_btn)
        sidebar_layout.addWidget(self.bit_stat_btn)
        sidebar_layout.addWidget(self.compare_btn)
        sidebar_layout.addWidget(self.report_btn)
        
        self.sidebar_group.addButton(self.file_struct_btn, 2)
        self.sidebar_group.addButton(self.metadata_btn, 3)
        self.sidebar_group.addButton(self.bit_stat_btn, 4)
        self.sidebar_group.addButton(self.compare_btn, 5)
        self.sidebar_group.addButton(self.report_btn, 6)
        
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