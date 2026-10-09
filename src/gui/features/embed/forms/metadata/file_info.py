"""File summaries for the Metadata editor's FileInfoBar (read only, never changes the file)."""
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from src.core.stego.metadata_handlers.png_handler import TEXT_CHUNKS, MetadataPNGHandler
from src.gui.components.gui_utils import format_file_size, truncate_text_middle


def get_png_file_info(file_path: str) -> dict:
    """Arguments for FileInfoBar.update_info(): name, size · width × height, badges."""
    path = Path(file_path)
    try:
        with Image.open(path) as image:
            image_format = image.format
            width, height = image.size
    except UnidentifiedImageError:
        raise ValueError(f"'{path.name}' is not a valid image file.") from None
    if image_format != "PNG":
        raise ValueError(f"'{path.name}' is not a PNG image.")

    chunks, _ = MetadataPNGHandler().read_chunks(file_path)  # ไฟล์ที่โครง chunk เสียจะ raise ตรงนี้
    text_count = sum(kind in TEXT_CHUNKS for kind, _ in chunks)
    return {
        "file_path": str(path),
        "display_name": truncate_text_middle(path.name, 110),
        "detail": f"{format_file_size(path.stat().st_size)} · {width} × {height}",
        "badges": [("PNG", "blue"), (f"{text_count} text chunks", "neutral")],
    }
