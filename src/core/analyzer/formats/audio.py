"""Audio Analyzer placeholders."""

from typing import Any

from src.core.analyzer.file_types import AnalyzerFileType


def analyze_file_structure(file_info: AnalyzerFileType) -> dict[str, Any]:
    print(f"[File Structure] format={file_info.format_name} media=audio")
    return _placeholder("File Structure", file_info)


def analyze_metadata(file_info: AnalyzerFileType) -> dict[str, Any]:
    print(f"[Metadata] format={file_info.format_name} media=audio")
    return _placeholder("Metadata", file_info)


def analyze_bit_statistics(file_info: AnalyzerFileType, **_parameters) -> dict[str, Any]:
    print(f"[Bit Statistics] format={file_info.format_name} media=audio (placeholder)")
    return _placeholder("Bit Statistics", file_info)


def _placeholder(tab_name: str, file_info: AnalyzerFileType) -> dict[str, Any]:
    return {
        "status": "placeholder",
        "tab": tab_name,
        "media_type": file_info.media_type,
        "format": file_info.format_name,
        "path": file_info.path,
    }
