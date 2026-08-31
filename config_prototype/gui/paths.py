from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
SHARED_GUI_ROOT = PROJECT_ROOT / "src" / "gui"

ICON_DIR = SHARED_GUI_ROOT / "assets" / "svg"
STYLE_PATH = SHARED_GUI_ROOT / "styles" / "default.qss"
