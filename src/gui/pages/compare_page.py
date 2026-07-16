from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QStackedWidget,
    QTabWidget, QVBoxLayout, QWidget, QPushButton
)
from src.gui.components.file_drop import FileDropWidget
from src.gui.components.gui_utils import create_icon_pixmap, format_file_size, truncate_text_middle
from src.gui.tabs.metadata_shared import FileInfoBar
from src.gui.tabs.compare.meta_diff_tab import MetaDiffTab
from src.gui.tabs.compare.struct_diff_tab import StructDiffTab
from src.gui.tabs.compare.stat_diff_tab import StatDiffTab
from src.gui.pages.analyzer_page import get_analyzer_file_display_info

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "svg"
ICON_SIZE = 16

class ComparePage(QFrame):

    def __init__(self):
        super().__init__()
        self.file_orig_path = None
        self.file_stego_path = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # -- Input Section --
        self.input_stack = QStackedWidget()
        self.input_stack.setFixedHeight(160)
        self.input_stack.addWidget(self.build_drop_zones())
        self.input_stack.addWidget(self.build_selected_zones())
        main_layout.addWidget(self.input_stack)

        # -- Compare Button --
        self.btn_compare = QPushButton("Run Comparison")
        self.btn_compare.setObjectName("primaryButton")
        self.btn_compare.setFixedHeight(40)
        self.btn_compare.setEnabled(False) # Enabled only when both files are selected
        self.btn_compare.clicked.connect(self.on_compare_clicked)
        main_layout.addWidget(self.btn_compare)

        # -- Results Tabs --
        self.tab_struct = StructDiffTab()
        self.tab_meta = MetaDiffTab()
        self.tab_stat = StatDiffTab()

        self.tab = QTabWidget()
        self.tab.addTab(self.tab_struct, self.create_state_icon(ICON_DIR / "file-search.svg", ICON_SIZE), "Structure Diff")
        self.tab.addTab(self.tab_meta, self.create_state_icon(ICON_DIR / "tags.svg", ICON_SIZE), "Metadata Diff")
        self.tab.addTab(self.tab_stat, self.create_state_icon(ICON_DIR / "chart-histogram.svg", ICON_SIZE), "Statistical Diff")

        main_layout.addWidget(self.tab)  

    def build_drop_zones(self):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0,0,0,0)
        
        self.drop_orig = FileDropWidget(
            "Original File (Cover)", 
            "Drop cover file here", 
            icon_path=str(ICON_DIR / "file.svg")
        )
        self.drop_orig.file_selected.connect(self.on_file_orig_selected)
        
        self.drop_stego = FileDropWidget(
            "Suspicious File (Stego)", 
            "Drop suspicious file here", 
            icon_path=str(ICON_DIR / "file-dots.svg")
        )
        self.drop_stego.file_selected.connect(self.on_file_stego_selected)
        
        layout.addWidget(self.drop_orig)
        layout.addWidget(self.drop_stego)
        
        return container

    def build_selected_zones(self):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0,0,0,0)
        
        # Left Info Bar
        self.info_orig = FileInfoBar()
        self.info_orig.change_file_requested.connect(self.reset_files)
        
        # Right Info Bar
        self.info_stego = FileInfoBar()
        self.info_stego.change_file_requested.connect(self.reset_files)
        
        layout.addWidget(self.info_orig)
        layout.addWidget(self.info_stego)
        
        return container

    def on_file_orig_selected(self, file_path: str):
        self.file_orig_path = file_path
        self.check_files_ready()

    def on_file_stego_selected(self, file_path: str):
        self.file_stego_path = file_path
        self.check_files_ready()
        
    def check_files_ready(self):
        if self.file_orig_path and self.file_stego_path:
            # Update Info Bars
            self.info_orig.update_info(get_analyzer_file_display_info(self.file_orig_path))
            self.info_stego.update_info(get_analyzer_file_display_info(self.file_stego_path))
            
            self.input_stack.setCurrentIndex(1)
            self.btn_compare.setEnabled(True)

    def reset_files(self):
        self.file_orig_path = None
        self.file_stego_path = None
        self.drop_orig.clear_file()
        self.drop_stego.clear_file()
        self.input_stack.setCurrentIndex(0)
        self.btn_compare.setEnabled(False)
        
        # Clear Tabs
        self.tab_struct.load_data({})
        self.tab_meta.load_data({})
        self.tab_stat.load_data({})

    def on_compare_clicked(self):
        from src.core.analyzer.docker_bridge import analyze
        from src.core.analyzer.compare_logic import compare_results
        
        try:
            res_orig = analyze(self.file_orig_path)
            res_stego = analyze(self.file_stego_path)

            if res_orig.get("error") or res_stego.get("error"):
                QMessageBox.critical(self, "Comparison Failed", res_orig.get("error") or res_stego.get("error"))
                return

            diff = compare_results(res_orig, res_stego, self.file_orig_path, self.file_stego_path)

            self.tab_meta.load_data(diff.get("metadata_diff", {}))
            self.tab_struct.load_data(diff.get("structure_diff", {}))
            self.tab_stat.load_data(diff.get("statistical_diff", {}))

        except Exception as e:
            QMessageBox.critical(self, "Comparison Failed", str(e))

    # ----- Icon Helper -----
    def create_state_icon(self, icon_path: str, icon_size: int) -> QIcon:
        color_normal = "#64748B"
        color_checked = "#38BDF8"
        color_hover = "#E2E8F0"
        icon = QIcon()
        
        pix_normal = create_icon_pixmap(icon_path, color_normal, size=icon_size)
        icon.addPixmap(pix_normal, QIcon.Mode.Normal, QIcon.State.Off)
        
        pix_hover = create_icon_pixmap(icon_path, color_hover, size=icon_size)
        icon.addPixmap(pix_hover, QIcon.Mode.Active, QIcon.State.Off)
        
        pix_checked = create_icon_pixmap(icon_path, color_checked, size=icon_size)
        icon.addPixmap(pix_checked, QIcon.Mode.Normal, QIcon.State.On)
        icon.addPixmap(pix_checked, QIcon.Mode.Active, QIcon.State.On)
        
        return icon
