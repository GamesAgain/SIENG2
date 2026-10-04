"""Read selected-file summaries without modifying metadata."""

from pathlib import Path

from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.mp3 import MP3
from PIL import Image

from src.core.stego.metadata_handlers.png_handler import MetadataPNGHandler
from src.gui.components.gui_utils import format_file_size, truncate_text_middle


def _file_info(file_path: str) -> dict:
    path = Path(file_path)
    return {
        "file_path": str(path),
        "display_name": truncate_text_middle(path.name, 110),
        "detail": format_file_size(path.stat().st_size),
    }


def get_png_file_info(file_path: str) -> dict:
    info = _file_info(file_path)
    with Image.open(file_path) as image:
        if image.format != "PNG":
            raise ValueError("The selected file is not a PNG image.")
        width, height = image.size
        image.verify()

    chunks = MetadataPNGHandler()._parse_chunks(Path(file_path).read_bytes())
    text_count = sum(kind in {b"tEXt", b"zTXt", b"iTXt"} for kind, _ in chunks)
    info["detail"] += f" · {width} × {height}"
    info["badges"] = [("PNG", "blue"), (f"{text_count} text chunks", "neutral")]
    return info


def get_mp3_file_info(file_path: str) -> dict:
    info = _file_info(file_path)
    audio = MP3(file_path)
    seconds = int(audio.info.length)
    bitrate = audio.info.bitrate // 1000
    try:
        tags = ID3(file_path)
    except ID3NoHeaderError:
        version = "No Tag"
        frame_count = 0
    else:
        major, minor, _ = tags.version
        version = f"ID3v{major}.{minor}"
        # Exclude the application's private manifest, as in ref.
        frame_count = sum(
            not (frame.FrameID == "PRIV" and getattr(frame, "owner", None) == "S2M")
            for frame in tags.values()
        )

    info["detail"] += f" · {seconds // 60}:{seconds % 60:02d} · {bitrate} kbps"
    info["badges"] = [(version, "blue"), (f"{frame_count} frames", "neutral")]
    return info
