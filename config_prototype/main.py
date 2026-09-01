"""Small launcher used to preview the rewritten Configurable Pipeline GUI."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication, QMainWindow

from config_prototype.gui.pages.sub_pages.embed.configurable_page import (
    EmbedConfigurablePage,
)
from config_prototype.gui.paths import STYLE_PATH
from src.gui.services.key_registry import KeyRegistry


DEFAULT_FONT = QFont("Segoe UI", 10)


def apply_stylesheet(app: QApplication, style_path: Path = STYLE_PATH) -> None:
    """Apply the shared SIENG2 stylesheet to the prototype application."""
    if not style_path.is_file():
        raise FileNotFoundError(f"Stylesheet not found: {style_path}")

    app.setStyleSheet(style_path.read_text(encoding="utf-8"))


class PrototypeWindow(QMainWindow):
    """Host the page without starting the complete SIENG2 application."""

    def __init__(self, key_registry: KeyRegistry | None = None) -> None:
        super().__init__()
        self.key_registry = (
            key_registry if key_registry is not None else KeyRegistry()
        )
        self.setWindowTitle("SIENG2 - Configurable Pipeline Prototype")
        self.resize(1100, 720)

        self.page = EmbedConfigurablePage(key_registry=self.key_registry)
        self.page.setObjectName("rootWidget")
        self.setCentralWidget(self.page)


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName("SIENG2")
    app.setApplicationName("SIENG2")
    app.setApplicationDisplayName("SIENG2 Configurable Pipeline Prototype")

    palette = app.palette()
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#94A3B8"))
    app.setPalette(palette)
    app.setFont(DEFAULT_FONT)

    apply_stylesheet(app)

    window = PrototypeWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
