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
        
        parsed_size = hachoir_data.get("parsed_size_bytes", 0)
        has_overlay = False
        overlay_size = 0
        
        structure_list = hachoir_data.get("structure", [])
        if structure_list:
            last_chunk = structure_list[-1]
            if "raw[" in last_chunk.get("name", "").lower():
                has_overlay = True
                overlay_size = last_chunk.get("size_bytes", 0)
                parsed_size -= overlay_size
        
        if parsed_size > 0 and self.file_size > parsed_size:
            has_overlay = True
            overlay_size = self.file_size - parsed_size
            
        return {
            "hachoir_raw": hachoir_data,
            "binwalk_raw": binwalk_data,
            "actual_size_bytes": self.file_size,
            "overlay_analysis": {
                "has_overlay": has_overlay,
                "overlay_size_bytes": overlay_size,
                "message": f"Found {overlay_size} bytes of appended data (Overlay)." if has_overlay else "No overlay data found."
            }
        }

    @abstractmethod
    def analyze(self) -> Dict[str, Any]:
        """
        Abstract method to be implemented by format-specific handlers.
        Should return a dictionary containing all analysis results.
        """
        pass
