"""File-type detection shared by the Analyzer backend placeholders."""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image


IMAGE_FORMATS = {
    ".png": "PNG",
}
AUDIO_FORMATS = {
    ".wav": "WAV",
}
VIDEO_FORMATS = {
    ".avi": "AVI",
}

SUPPORTED_ANALYZER_EXTENSIONS = tuple(
    (*IMAGE_FORMATS, *AUDIO_FORMATS, *VIDEO_FORMATS)
)


@dataclass(frozen=True)
class AnalyzerFileType:
    """Classification used to select an Analyzer backend."""

    path: str
    media_type: str
    format_name: str
    extension: str


def detect_file_type(file_path: str) -> AnalyzerFileType:
    """Detect the supported media family and print-friendly format name."""
    path = Path(file_path).resolve(strict=True)
    extension = path.suffix.lower()

    if extension in IMAGE_FORMATS:
        try:
            with Image.open(path) as image:
                if image.format != "PNG":
                    raise ValueError("The selected .png file is not a PNG image.")
                image.verify()
                format_name = image.format or IMAGE_FORMATS[extension]
        except OSError as exc:
            raise ValueError(f"Cannot read image file: {path.name}") from exc
        return AnalyzerFileType(str(path), "image", format_name.upper(), extension)

    if extension in AUDIO_FORMATS:
        return AnalyzerFileType(
            str(path), "audio", AUDIO_FORMATS[extension], extension
        )

    if extension in VIDEO_FORMATS:
        return AnalyzerFileType(
            str(path), "video", VIDEO_FORMATS[extension], extension
        )

    supported = ", ".join(SUPPORTED_ANALYZER_EXTENSIONS)
    raise ValueError(f"Unsupported file format '{extension}'. Supported: {supported}")
