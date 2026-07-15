from typing import Dict, Any
import numpy as np
from scipy.io import wavfile
from src.core.analyzer.formats.base_handler import BaseFormatHandler
from src.core.analyzer.modules.statistical_analyzer import StatisticalAnalyzer

class WAVHandler(BaseFormatHandler):
    def analyze(self) -> Dict[str, Any]:
        """
        Analyzes WAV specific structure and its metadata.
        """
        print(f"[WAVHandler] Analyzing file: {self.file_path}")
        
        # 1. Analyze Metadata
        metadata_results = self.analyze_metadata()
        
        # 2. Extract raw structure
        structure_results = self.extract_raw_structure()
        
        hachoir_raw = structure_results.get("hachoir_raw", {})
        if "structure" in hachoir_raw:
            suspicious_count = self._tag_suspicious_chunks(hachoir_raw["structure"])
            structure_results["suspicious_chunk_count"] = suspicious_count
            structure_results["has_suspicious_chunks"] = suspicious_count > 0
            
        stat_results = {}
        try:
            _, data = wavfile.read(self.file_path)
            lsb_data = np.uint8(data & 0xFF)
            flat = lsb_data.flatten()
            
            stat_analyzer = StatisticalAnalyzer(flat)
            stat_results = stat_analyzer.analyze()
        except Exception as e:
            stat_results = {"error": f"Failed to extract WAV array for stat: {e}"}
        
        return {
            "format": "WAV",
            "file_size": self.file_size,
            "metadata_analysis": metadata_results,
            "structure_analysis": structure_results,
            "statistical_analysis": stat_results
        }

    def _tag_suspicious_chunks(self, chunks_list: list) -> int:
        STANDARD_WAV_CHUNKS = [
            "riff", "wave", "fmt", "data", "fact", "list", "info", "bext", "junk", "pad", "disp", "adtl"
        ]
        
        suspicious_count = 0
        for chunk in chunks_list:
            chunk_name = chunk.get("name", "").lower()
            is_suspicious = False
            suspicious_reason = ""
            
            if "raw" in chunk_name or "unknown" in chunk_name:
                is_suspicious = True
                suspicious_reason = f"Unparsed or raw data found: '{chunk_name}'"
            
            sub_chunks = chunk.get("sub_chunks", [])
            tag_value = None
            for sub in sub_chunks:
                # RIFF (WAV) format often uses 'id' instead of 'tag'
                if sub.get("name", "").lower() in ["tag", "id"]:
                    tag_value = sub.get("value", "").replace('"', '').strip().lower()
                    break
                    
            if tag_value and tag_value not in STANDARD_WAV_CHUNKS:
                is_suspicious = True
                suspicious_reason = f"Non-standard WAV chunk tag: '{tag_value}'"
                
            if is_suspicious:
                chunk["is_suspicious"] = True
                chunk["suspicious_reason"] = suspicious_reason
                suspicious_count += 1
                
            if isinstance(sub_chunks, list) and len(sub_chunks) > 0:
                suspicious_count += self._tag_suspicious_chunks(sub_chunks)
                
        return suspicious_count


