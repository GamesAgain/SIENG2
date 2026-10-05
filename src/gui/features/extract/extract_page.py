from PyQt6.QtWidgets import QFrame, QLabel, QStackedWidget, QVBoxLayout

from src.gui.components.widgets.selection_toggle import SelectionToggle
from src.gui.features.embed.configurable.configurable_page import EmbedConfigurablePage
from src.gui.features.embed.standalone.standalone_page import EmbedStandalonePage
from src.gui.features.extract.standalone.standalone_page import ExtractStandalonePage
from src.gui.services.key_registry import KeyRegistry
from src.path import svg_path


ICON_SIZE = 16
COLOR_CHECKED_STANDALONE = "#38BDF8"
COLOR_CHECKED_CONFIGURABLE = "#F59E0F"


class ExtractPage(QFrame):
    def __init__(self, key_registry: KeyRegistry = None, parent=None):
        super().__init__(parent)

        self.key_registry = key_registry
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

        self.mode_selection = SelectionToggle([
            {
                "text": "Standalone Mode",
                "value": "standalone",
                "variant": "standalone",
                "color_checked": COLOR_CHECKED_STANDALONE,
                "icon_path": svg_path("tool.svg"),
                "icon_size": ICON_SIZE,
            },
            {
                "text": "Configurable Pipeline",
                "value": "configurable",
                "variant": "configurable",
                "color_checked": COLOR_CHECKED_CONFIGURABLE,
                "icon_path": svg_path("git-branch.svg"),
                "icon_size": ICON_SIZE,
            },
        ])

        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(ExtractStandalonePage(self.key_registry))
        self.mode_stack.addWidget(QLabel("Config")) # TODO

        self.mode_selection.mode_changed.connect(self.on_mode_changed)

        main_layout.addWidget(self.mode_selection)
        main_layout.addSpacing(10)
        main_layout.addWidget(self.mode_stack)

    def on_mode_changed(self, mode: str):
        if mode == "standalone":
            self.mode_stack.setCurrentIndex(0)

        elif mode == "configurable":
            self.mode_stack.setCurrentIndex(1)
