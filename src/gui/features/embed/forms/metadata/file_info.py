"""File summaries for the Metadata editor's FileInfoBar (read only, never changes the file)."""
from pathlib import Path

from mutagen.mp3 import MP3
from PIL import Image, UnidentifiedImageError

from src.core.stego.metadata_handlers.mp3_handler import MetadataMP3Handler
from src.core.stego.metadata_handlers.png_handler import TEXT_CHUNKS, MetadataPNGHandler
from src.gui.components.gui_utils import format_file_size, truncate_text_middle
from src.path import svg_path


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


def get_mp3_file_info(file_path: str) -> dict:
    """Arguments for FileInfoBar.update_info(): name, size · length · bitrate, ID3 version, frame count."""
    path = Path(file_path)
    handler = MetadataMP3Handler()
    tags = handler.load_tags(file_path)  # ไม่ใช่ MP3 จริง -> ValueError
    audio = MP3(file_path).info
    seconds = int(audio.length)

    # ID3() ที่ไม่ได้อ่านจากไฟล์ (ไฟล์ไม่มี tag) จะไม่มี filename
    version = f"ID3v2.{tags.version[1]}" if tags.filename else "No Tag"
    frame_count = sum(not handler.is_toc(frame) for frame in tags.values())  # ไม่นับ TOC ของเราเอง
    return {
        "file_path": str(path),
        "display_name": truncate_text_middle(path.name, 110),
        "detail": f"{format_file_size(path.stat().st_size)} · {seconds // 60}:{seconds % 60:02d} · {audio.bitrate // 1000} kbps",
        "badges": [(version, "blue"), (f"{frame_count} frames", "neutral")],
        "icon_path": str(svg_path("photo-video.svg")),
    }
