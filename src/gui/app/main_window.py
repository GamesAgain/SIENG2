from PyQt6.QtWidgets import (
    QLabel, QMainWindow, QWidget, QFrame,
    QVBoxLayout, QHBoxLayout, QStackedWidget)
from PyQt6.QtCore import Qt

from src.gui.app.resize_handle import WindowResizeHandler
from src.gui.app.title_bar import SIENG2TitleBar
from src.gui.app.sidebar import SIENG2SideBar
from src.gui.features.key_management.key_manage_page import KeyManagementPage
from src.gui.services.key_registry import KeyRegistry


class MainWindow(QMainWindow):
    
    def __init__(self, key_registry: KeyRegistry | None = None, parent=None):
        super().__init__(parent)
        
        self.key_registry = key_registry or KeyRegistry()
        
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("SIENG2")
        self.resize(1280, 720)
        self.setMinimumSize(1024, 700)
        
        self.setup_ui()
        
        # -- Window Resize Handler --
        self.resize_handler = WindowResizeHandler(self, margin=8)
        
    def setup_ui(self):
        
        # -- Root Container --
        root_widget = QFrame()
        root_widget.setObjectName("windowForm")
        root_layout = QVBoxLayout(root_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        
        # -- Title Bar --
        title_bar = SIENG2TitleBar(self)
        
        # -- Center Container --
        center_widget = QWidget()
        center_layout = QHBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        
        # -- Sidebar --
        sidebar = SIENG2SideBar(self)
        
        # -- Main Content --
        self.page_stack = QStackedWidget()
        
        #TODO Page viewer
        self.page_stack.addWidget(QLabel("Emebed"))
        self.page_stack.addWidget(QLabel("Extract"))
        self.page_stack.addWidget(KeyManagementPage(self.key_registry))
        self.page_stack.addWidget(QLabel("Analyzer"))
        self.page_stack.addWidget(QLabel("Compare"))
        
        # -- Connect sidebar to page container --
        sidebar.button_clicked.connect(self.page_chaged)
        
        # Sidebar and main content layout 20:80
        center_layout.addWidget(sidebar, 2)
        center_layout.addWidget(self.page_stack, 8)
        
        root_layout.addWidget(title_bar)
        root_layout.addWidget(center_widget)
        
        self.setCentralWidget(root_widget)
    
    # --- Event Handlers ---
    def page_chaged(self, index: int):
        self.page_stack.setCurrentIndex(index)
    