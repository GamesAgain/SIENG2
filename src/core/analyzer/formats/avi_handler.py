from typing import Dict, Any
from src.core.analyzer.formats.base_handler import BaseFormatHandler

class AVIHandler(BaseFormatHandler):
    def analyze(self) -> Dict[str, Any]:
        """
        Analyzes AVI specific structure and its metadata.
        """
        print(f"[AVIHandler] Analyzing file: {self.file_path}")
        
        # 1. Analyze Metadata
        metadata_results = self.analyze_metadata()
        
        # 2. Extract raw structure
        structure_results = self.extract_raw_structure()
        
        hachoir_raw = structure_results.get("hachoir_raw", {})
        if "structure" in hachoir_raw:
            suspicious_count = self._tag_suspicious_chunks(hachoir_raw["structure"])
            structure_results["suspicious_chunk_count"] = suspicious_count
            structure_results["has_suspicious_chunks"] = suspicious_count > 0
        
        return {
            "format": "AVI",
            "file_size": self.file_size,
            "metadata_analysis": metadata_results,
            "structure_analysis": structure_results
        }

    def _tag_suspicious_chunks(self, chunks_list: list) -> int:
        STANDARD_AVI_CHUNKS = [
            "riff", "avi", "list", "hdrl", "avih", "strl", "strh", "strf", 
            "movi", "idx1", "junk", "vprp", "dmlh", "strd", "strn"
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
                # RIFF (AVI) format often uses 'id' instead of 'tag'
                if sub.get("name", "").lower() in ["tag", "id"]:
                    tag_value = sub.get("value", "").replace('"', '').strip().lower()
                    break
                    
            if tag_value and tag_value not in STANDARD_AVI_CHUNKS:
                # AVI streams often use tags like '00dc', '01wb', etc. for video/audio frames
                if len(tag_value) == 4 and (tag_value.endswith("dc") or tag_value.endswith("wb") or tag_value.endswith("db") or tag_value.endswith("pc")):
                    pass # Allow standard AVI stream chunks
                else:
                    is_suspicious = True
                    suspicious_reason = f"Non-standard AVI chunk tag: '{tag_value}'"
                
            if is_suspicious:
                chunk["is_suspicious"] = True
                chunk["suspicious_reason"] = suspicious_reason
                suspicious_count += 1
                
            if isinstance(sub_chunks, list) and len(sub_chunks) > 0:
                suspicious_count += self._tag_suspicious_chunks(sub_chunks)
                
        return suspicious_count
