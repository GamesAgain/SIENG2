from typing import Dict, Any
from PIL import Image
import numpy as np
from src.core.analyzer.formats.base_handler import BaseFormatHandler
from src.core.analyzer.modules.statistical_analyzer import StatisticalAnalyzer

class PNGHandler(BaseFormatHandler):
    def analyze(self) -> Dict[str, Any]:
        """
        Analyzes PNG specific structure and its metadata.
        """
        print(f"[PNGHandler] Analyzing file: {self.file_path}")
        
        metadata_results = self.analyze_metadata()
        structure_results = self.extract_raw_structure()
        
        hachoir_raw = structure_results.get("hachoir_raw", {})
        if "structure" in hachoir_raw:
            suspicious_count = self._tag_suspicious_chunks(hachoir_raw["structure"])
            structure_results["suspicious_chunk_count"] = suspicious_count
            structure_results["has_suspicious_chunks"] = suspicious_count > 0
            
        stat_results = {}
        try:
            with Image.open(self.file_path) as img:
                arr = np.array(img.convert("RGB"))
                stat_analyzer = StatisticalAnalyzer(arr)
                stat_results = stat_analyzer.analyze()
        except Exception as e:
            stat_results = {"error": f"Failed to extract PNG array for stat: {e}"}
        
        return {
            "format": "PNG",
            "file_size": self.file_size,
            "metadata_analysis": metadata_results,
            "structure_analysis": structure_results,
            "statistical_analysis": stat_results
        }

    def _tag_suspicious_chunks(self, chunks_list: list, parent_name: str = "") -> int:
        STANDARD_PNG_CHUNKS = [
            "ihdr", "plte", "idat", "iend", "trns", "chrm", "gama", 
            "iccp", "sbit", "srgb", "text", "ztxt", "itxt", "bkgd", 
            "hist", "phys", "splt", "time"
        ]
        
        suspicious_count = 0
        for chunk in chunks_list:
            chunk_name = chunk.get("name", "").lower()
            is_suspicious = False
            suspicious_reason = ""
            
            if "raw" in chunk_name or "unknown" in chunk_name:
                if "compress" not in chunk_name and "compress" not in parent_name:
                    is_suspicious = True
                    suspicious_reason = f"Unparsed or raw data found: '{chunk_name}'"
            
            sub_chunks = chunk.get("sub_chunks", [])
            tag_value = None
            for sub in sub_chunks:
                if sub.get("name", "").lower() == "tag":
                    tag_value = sub.get("value", "").replace('"', '').lower()
                    break
                    
            if tag_value and tag_value not in STANDARD_PNG_CHUNKS:
                is_suspicious = True
                suspicious_reason = f"Non-standard PNG chunk tag: '{tag_value}'"
                
            if is_suspicious:
                chunk["is_suspicious"] = True
                chunk["suspicious_reason"] = suspicious_reason
                suspicious_count += 1
                
            if isinstance(sub_chunks, list) and len(sub_chunks) > 0:
                suspicious_count += self._tag_suspicious_chunks(sub_chunks, parent_name=chunk_name)
                
        return suspicious_count
