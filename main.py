import sys
from pathlib import Path

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from src.gui.app.main_window import MainWindow
from src.path import DEFAULT_QSS_PATH

DEFAULT_FONT = QFont("Segoe UI", 10)

def load_stylesheet(style_path: Path) -> str:
    return style_path.read_text(encoding="utf-8")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("SIENG2")
    
    app.setFont(DEFAULT_FONT)
    app.setStyleSheet(load_stylesheet(DEFAULT_QSS_PATH))

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())