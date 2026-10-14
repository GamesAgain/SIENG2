"""Public entry points for the Analyzer backend."""

from src.core.analyzer.dispatcher import (
    analyze_bit_statistics,
    analyze_file_structure,
    analyze_metadata,
    announce_tab,
    handle_uploaded_file,
)
from src.core.analyzer.file_types import (
    AnalyzerFileType,
    SUPPORTED_ANALYZER_EXTENSIONS,
    detect_file_type,
)

__all__ = [
    "AnalyzerFileType",
    "SUPPORTED_ANALYZER_EXTENSIONS",
    "analyze_bit_statistics",
    "analyze_file_structure",
    "analyze_metadata",
    "announce_tab",
    "detect_file_type",
    "handle_uploaded_file",
]
