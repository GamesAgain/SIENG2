"""Route Analyzer operations to the backend for the uploaded media type."""

from importlib import import_module
from typing import Any

from src.core.analyzer.file_types import AnalyzerFileType, detect_file_type


def handle_uploaded_file(file_path: str) -> AnalyzerFileType:
    """Classify an uploaded file and print the selected backend."""
    file_info = detect_file_type(file_path)
    print(
        f"[Analyzer Upload] format={file_info.format_name} "
        f"media={file_info.media_type} file={file_info.path}"
    )
    return file_info


def analyze_file_structure(file_path: str) -> dict[str, Any]:
    """Dispatch the File Structure tab backend."""
    file_info = detect_file_type(file_path)
    return _backend(file_info).analyze_file_structure(file_info)


def analyze_metadata(file_path: str) -> dict[str, Any]:
    """Dispatch the Metadata tab backend."""
    file_info = detect_file_type(file_path)
    return _backend(file_info).analyze_metadata(file_info)


def analyze_bit_statistics(file_path: str, **parameters) -> dict[str, Any]:
    """Dispatch Bit Statistics; image is implemented, other media are placeholders."""
    file_info = detect_file_type(file_path)
    return _backend(file_info).analyze_bit_statistics(file_info, **parameters)


def announce_tab(file_path: str, tab_name: str) -> None:
    """Print tab routing without starting a potentially expensive analysis."""
    file_info = detect_file_type(file_path)
    print(
        f"[Analyzer Tab] tab={tab_name} format={file_info.format_name} "
        f"media={file_info.media_type}"
    )


def _backend(file_info: AnalyzerFileType):
    return import_module(f"src.core.analyzer.formats.{file_info.media_type}")
