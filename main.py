import sys
from pathlib import Path

from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication

from src.gui.main_window import MainWindow

DEFAULT_FONT = QFont("Segoe UI", 10)

def apply_stylesheet(app: QApplication, style: str = "default.qss"):
    """Apply a stylesheet to the application."""
    style_path = Path(__file__).parent / "src" / "gui" / "styles" / style
    
    with open(style_path, "r", encoding="utf-8") as f:
        app.setStyleSheet(f.read())


def main():
    app = QApplication(sys.argv)
    
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#94a3b8"))
    # palette.setColor(QPalette.ColorRole.Text, QColor("##94a3b8"))
    # palette.setColor(QPalette.ColorRole.ButtonText, QColor("#94a3b8"))
    
    app.setPalette(palette)
    app.setFont(DEFAULT_FONT)
    apply_stylesheet(app)
    
    window = MainWindow()
    window.show()
    print("SIENG2 GUI starting...")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
