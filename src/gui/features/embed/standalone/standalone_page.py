from PyQt6.QtWidgets import QFrame, QTabWidget, QVBoxLayout
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon

from src.gui.components.gui_utils import create_icon_pixmap
from src.gui.features.embed.standalone.locomotive_tab import LocomotiveStandaloneTab
from src.gui.features.embed.standalone.lsb_tab import LSBStandaloneTab
from src.gui.features.embed.standalone.metadata_tab import MetadataStandaloneTab
from src.gui.services.key_registry import KeyRegistry
from src.path import svg_path

ICON_SIZE = 16

class EmbedStandalonePage(QFrame):
    def __init__(self, key_registry: KeyRegistry = None, parent=None):
        super().__init__(parent)
        self.key_registry = key_registry
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)

        self.tab_lsb = LSBStandaloneTab(key_registry=self.key_registry)
        self.tab_locomotive = LocomotiveStandaloneTab(key_registry=self.key_registry)
        self.tab_metadata = MetadataStandaloneTab()

        tech_tabs = QTabWidget()
        tech_tabs.setObjectName("siengTabs")
        tech_tabs.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        tech_tabs.addTab(self.tab_lsb, self.create_state_icon(svg_path("binary.svg"), ICON_SIZE), "LSB++")
        tech_tabs.addTab(self.tab_locomotive, self.create_state_icon(svg_path("train.svg"), ICON_SIZE), "Locomotive")
        tech_tabs.addTab(self.tab_metadata, self.create_state_icon(svg_path("tags.svg"), ICON_SIZE), "Metadata")

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
