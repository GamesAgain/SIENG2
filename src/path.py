from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
TEMPLATES_DIR = SRC_DIR / "templates"

GUI_DIR = SRC_DIR / "gui"

ASSETS_DIR = GUI_DIR / "assets"
SVG_DIR = ASSETS_DIR / "svg"
PNG_DIR = ASSETS_DIR / "png"

STYLES_DIR = GUI_DIR / "styles"
DEFAULT_QSS_PATH = STYLES_DIR / "default.qss"


def svg_path(filename: str) -> Path:
    """Return the path of an SVG asset."""
    return SVG_DIR / filename


def png_path(filename: str) -> Path:
    """Return the path of a PNG asset."""
    return PNG_DIR / filename
