import os
from abc import ABC, abstractmethod
from typing import Dict, Any
from src.core.analyzer.external_tools.exiftool_wrapper import extract_metadata
from src.core.analyzer.modules.metadata_analyzer import MetadataAnalyzer
from src.core.analyzer.external_tools.binwalk_wrapper import run_binwalk
from src.core.analyzer.external_tools.hachoir_wrapper import extract_file_structure

class BaseFormatHandler(ABC):
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    def analyze_metadata(self) -> Dict[str, Any]:
        raw_exif = extract_metadata(self.file_path)
        if not raw_exif:
            return {"error": "Failed to extract metadata or no metadata found."}
            
        analyzer = MetadataAnalyzer(raw_exif)
        return analyzer.analyze()

    def extract_raw_structure(self) -> Dict[str, Any]:
        hachoir_data = extract_file_structure(self.file_path)
        binwalk_data = run_binwalk(self.file_path)

        # Raw-byte integrity: overlay (from the format's own declared end, not the
        # parser's consumed size) + format-specific tampering signals (PNG CRC / RIFF JUNK)
        with open(self.file_path, "rb") as f:
            raw = f.read()
        integrity = self._integrity_report(raw)

        content_end = integrity.get("content_end")
        has_overlay = content_end is not None and self.file_size > content_end
        overlay_size = (self.file_size - content_end) if has_overlay else 0

        return {
            "hachoir_raw": hachoir_data,
            "binwalk_raw": binwalk_data,
            "actual_size_bytes": self.file_size,
            "integrity_anomalies": integrity.get("anomalies", []),
            "overlay_analysis": {
                "has_overlay": has_overlay,
                "overlay_size_bytes": overlay_size,
                "message": f"Found {overlay_size} bytes of appended data (Overlay)." if has_overlay else "No overlay data found."
            }
        }

    def _integrity_report(self, raw: bytes) -> Dict[str, Any]:
        """Format-specific raw-byte checks. Overridden per format; default = nothing
        (content_end None means overlay detection is skipped for that format)."""
        return {"content_end": None, "anomalies": []}

    @abstractmethod
    def analyze(self) -> Dict[str, Any]:
        """
        Abstract method to be implemented by format-specific handlers.
        Should return a dictionary containing all analysis results.
        """
        pass
