from typing import Dict, Any
import numpy as np
from scipy.io import wavfile
from src.core.analyzer.formats.base_handler import BaseFormatHandler
from src.core.analyzer.modules.statistical_analyzer import StatisticalAnalyzer
from src.core.analyzer.modules.structure_integrity import riff_integrity

class WAVHandler(BaseFormatHandler):
    _entropy_reliable = True  # PCM audio is low-entropy, so an embedded encrypted blob stands out

    def _integrity_report(self, raw: bytes) -> Dict[str, Any]:
        return riff_integrity(raw)

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

        self.add_mediainfo(structure_results)

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
            "riff", "wave", "fmt", "data", "fact", "list", "info", "bext", "junk", "pad", "disp", "adtl",
            # RIFF INFO list tags (software/artist/comment/etc.) - standard metadata a WAV can carry
            "iarl", "iart", "icms", "icmt", "icop", "icrd", "icrp", "idim", "idpi", "ieng",
            "ignr", "ikey", "ilgt", "imed", "inam", "iplt", "iprd", "isbj", "isft", "ishp",
            "isrc", "isrf", "itch", "itrk", "idit", "ismp",
        ]
        
        suspicious_count = 0
        for chunk in chunks_list:
            sub_chunks = chunk.get("sub_chunks", [])

            # Flag chunks whose fourCC tag isn't a standard WAV chunk type (e.g. an injected
            # 'stEg' carrier). The old "raw/unparsed data" name heuristic was dropped - it
            # false-flagged the 'data' audio-payload chunk on every valid WAV (its samples are
            # raw bytes a parser can't decompose). Data hidden in a padding (JUNK) chunk is
            # caught by riff_integrity instead.
            tag_value = None
            for sub in sub_chunks:
                # RIFF (WAV) format often uses 'id' instead of 'tag'
                if sub.get("name", "").lower() in ["tag", "id"]:
                    tag_value = sub.get("value", "").replace('"', '').strip().lower()
                    break

            if tag_value and tag_value not in STANDARD_WAV_CHUNKS:
                chunk["is_suspicious"] = True
                chunk["suspicious_reason"] = f"Non-standard WAV chunk tag: '{tag_value}'"
                suspicious_count += 1

            if isinstance(sub_chunks, list) and len(sub_chunks) > 0:
                suspicious_count += self._tag_suspicious_chunks(sub_chunks)

        return suspicious_count


