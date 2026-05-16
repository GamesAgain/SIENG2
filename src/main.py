from PyQt6.QtWidgets import QApplication
import sys, os
from pathlib import Path

from src.gui.main_window import MainWindow

def load_stylesheet():
    style_path = Path(__file__).parent / "gui" / "styles" / "default.qss"
    with open(style_path, "r", encoding="utf-8") as f:
        return f.read()
    
def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(load_stylesheet())
    window = MainWindow()
    window.show()
    print("SIENG2 GUI starting...")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()