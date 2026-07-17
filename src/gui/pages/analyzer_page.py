from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QStackedWidget,
    QTabBar, QTabWidget, QVBoxLayout, QWidget
)
from src.gui.components.file_drop import FileDropWidget
from src.gui.components.gui_utils import create_icon_pixmap, format_file_size, truncate_text_middle
from src.gui.tabs.analyzer.bit_stat import BitStatTab
from src.gui.tabs.analyzer.file_structure import FileStructureTab
from src.gui.tabs.analyzer.metadata_tab import MetadataTab
from src.gui.tabs.analyzer.report_tab import ReportTab
from src.gui.tabs.metadata_shared import FileInfoBar
from src.gui.components.worker import FuncWorker

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "svg"
ICON_SIZE = 16

def get_analyzer_file_display_info(file_path: str) -> dict:
    path_obj = Path(file_path)
    size_text = format_file_size(path_obj.stat().st_size)
    display_name = truncate_text_middle(path_obj.name, 110)
    ext = path_obj.suffix.lower()

    if ext in [".png", ".jpg", ".jpeg", ".bmp", ".gif"]:
        try:
            from PIL import Image
            with Image.open(file_path) as img:
                width, height = img.size
                bit_depth = {"1": 1, "L": 8, "P": 8, "RGB": 24, "RGBA": 32}.get(img.mode, 8)
        except Exception:
            width, height, bit_depth = 0, 0, 8
        
        return {
            "icon": str(ICON_DIR / "photo.svg"),
            "name": display_name,
            "detail": f"{size_text} · {width} × {height} · {bit_depth}-bit",
            "badges": [("PNG", "blue")] if ext == ".png" else [(ext.upper().replace(".", ""), "blue")],
        }
    else:
        ext_upper = ext.upper().replace(".", "")
        return {
            "icon": str(ICON_DIR / "file.svg"),
            "name": display_name,
            "detail": f"{size_text} · {ext_upper} File",
            "badges": [(ext_upper, "blue")],
        }

class AnalyzerPage(QFrame):

    def __init__(self):
        super().__init__()
        self.file_path = None
        self._analysis_worker = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        self.file_stack = QStackedWidget()
        self.file_stack.setFixedHeight(110)
        self.file_stack.addWidget(self.build_file_drop_card())
        self.file_stack.addWidget(self.build_file_selected_card())
        main_layout.addWidget(self.file_stack)

        self.tab_metadata = MetadataTab()
        self.tab_file_structure = FileStructureTab()
        self.tab_bit_stat = BitStatTab()
        self.tab_report = ReportTab()

        self.tab = QTabWidget()
        self.tab.addTab(self.tab_file_structure, self.create_state_icon(ICON_DIR / "file-search.svg", ICON_SIZE), "File Structure")
        self.tab.addTab(self.tab_metadata, self.create_state_icon(ICON_DIR / "tags.svg", ICON_SIZE), "Metadata")
        self.tab.addTab(self.tab_bit_stat, self.create_state_icon(ICON_DIR / "chart-histogram.svg", ICON_SIZE), "Bit Statistics")
        self.tab.addTab(self.tab_report, self.create_state_icon(ICON_DIR / "report.svg", ICON_SIZE), "Report")

        main_layout.addWidget(self.tab)  

    def build_file_drop_card(self):
        self.drop_zone = FileDropWidget(
            "Drop file here or click to browse", 
            "Supported: .png .avi .wav", 
            icon_path=str(ICON_DIR / "file.svg"), 
            allowed_extensions=["png", "avi", "wav"]
        )
        self.drop_zone.file_selected.connect(self.on_file_selected)
        return self.drop_zone
    
    def build_file_selected_card(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.file_info_bar = FileInfoBar()
        self.file_info_bar.change_file_requested.connect(self.on_change_file_clicked)
        
        self.run_analysis_btn = self.file_info_bar.add_extra_button("Run Analysis")
        self.run_analysis_btn.clicked.connect(self.on_run_analysis_clicked)
        
        layout.addWidget(self.file_info_bar)

        return container

    # --- Event Handlers ---
    def on_file_selected(self, file_path: str):
        self.file_path = file_path
        
        info = get_analyzer_file_display_info(file_path)
        self.file_info_bar.update_info(info)
        
        self.file_stack.setCurrentIndex(1)

    def on_change_file_clicked(self):
        self.drop_zone.clear_file()
        self.file_path = None
        self.file_stack.setCurrentIndex(0)
        
        # Clear data from tabs
        if hasattr(self.tab_metadata, 'load_data'):
            self.tab_metadata.load_data({})
        if hasattr(self.tab_file_structure, 'load_data'):
            self.tab_file_structure.load_data({})
            self.tab_file_structure.set_target_file(None)
        if hasattr(self.tab_bit_stat, 'load_data'):
            self.tab_bit_stat.load_data({})
            self.tab_bit_stat.set_target_file(None)
        if hasattr(self.tab_report, 'load_data'):
            self.tab_report.load_data({})

    def on_run_analysis_clicked(self):
        # analyze() shells out to Docker (seconds) - run it on a worker so the window stays
        # responsive, and show a busy state instead of a silent freeze.
        if not self.file_path or (self._analysis_worker and self._analysis_worker.isRunning()):
            return
        from src.core.analyzer.docker_bridge import analyze
        self._set_analyzing(True)
        self._analysis_worker = FuncWorker(analyze, self.file_path)
        self._analysis_worker.done.connect(self._on_analysis_done)
        self._analysis_worker.start()

    def _set_analyzing(self, busy: bool):
        self.run_analysis_btn.setEnabled(not busy)
        self.run_analysis_btn.setText("Analyzing…" if busy else "Run Analysis")

    def _on_analysis_done(self, results: dict):
        self._set_analyzing(False)
        if not isinstance(results, dict) or results.get("error"):
            QMessageBox.critical(self, "Analysis Failed",
                                 (results or {}).get("error", "Unknown error") if isinstance(results, dict)
                                 else "Unknown error")
            return

        if hasattr(self.tab_metadata, 'load_data'):
            self.tab_metadata.load_data(results)

        if hasattr(self.tab_file_structure, 'load_data'):
            self.tab_file_structure.load_data(results)
            self.tab_file_structure.set_target_file(self.file_path)

        if hasattr(self.tab_bit_stat, 'load_data'):
            self.tab_bit_stat.load_data(results)
            self.tab_bit_stat.set_target_file(self.file_path)

        if hasattr(self.tab_report, 'load_data'):
            self.tab_report.load_data(results)

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