from typing import Dict, Any
import cv2
import numpy as np
from src.core.analyzer.formats.base_handler import BaseFormatHandler
from src.core.analyzer.modules.statistical_analyzer import StatisticalAnalyzer
from src.core.analyzer.modules.structure_integrity import riff_integrity

class AVIHandler(BaseFormatHandler):
    def _integrity_report(self, raw: bytes) -> Dict[str, Any]:
        return riff_integrity(raw)

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

        self.add_mediainfo(structure_results)

        stat_results = {}
        try:
            cap = cv2.VideoCapture(self.file_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            if total_frames <= 0:
                ret, frame = cap.read()
                frames_to_process = [frame] if ret else []
            else:
                num_samples = min(total_frames, 5) # Sample up to 5 frames
                frame_indices = np.linspace(0, total_frames - 1, num_samples, dtype=int)
                
                frames_to_process = []
                for idx in frame_indices:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                    ret, frame = cap.read()
                    if ret:
                        frames_to_process.append(frame)
            cap.release()
            
            if frames_to_process:
                accumulated_results = []
                for frame in frames_to_process:
                    arr = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    stat_analyzer = StatisticalAnalyzer(arr)
                    res = stat_analyzer.analyze()
                    if "error" not in res:
                        accumulated_results.append(res)
                
                if accumulated_results:
                    stat_results = self._average_stat_results(accumulated_results)
                else:
                    stat_results = {"error": "Failed to extract valid statistical data from frames"}
            else:
                stat_results = {"error": "Failed to extract frames from AVI"}
        except Exception as e:
            stat_results = {"error": f"Failed to read AVI for stat: {e}"}
        
        return {
            "format": "AVI",
            "file_size": self.file_size,
            "metadata_analysis": metadata_results,
            "structure_analysis": structure_results,
            "statistical_analysis": stat_results
        }

    def _average_stat_results(self, results_list: list) -> Dict[str, Any]:
        if not results_list:
            return {}
            
        averaged = {}
        for method in results_list[0].keys():
            if method == "error":
                continue
                
            averaged[method] = {}
            for key in results_list[0][method].keys():
                if isinstance(results_list[0][method][key], (int, float, bool)):
                    averaged[method][key] = 0.0
                    
            count = len(results_list)
            for res in results_list:
                for key in res.get(method, {}).keys():
                    if key in averaged[method] and isinstance(res[method][key], (int, float, bool)):
                        averaged[method][key] += float(res[method][key])
                        
            for key in averaged[method].keys():
                averaged[method][key] /= count
                if isinstance(results_list[0][method].get(key), bool):
                    averaged[method][key] = averaged[method][key] >= 0.5
                    
        return averaged

    def _tag_suspicious_chunks(self, chunks_list: list) -> int:
        STANDARD_AVI_CHUNKS = [
            "riff", "avi", "list", "hdrl", "avih", "strl", "strh", "strf",
            "movi", "idx1", "junk", "vprp", "dmlh", "strd", "strn",
            # RIFF INFO list tags (encoder/software/artist/etc. metadata) - standard, written by
            # ffmpeg/opencv on nearly every AVI (e.g. 'isft' = Software). Omitting these made a
            # normal encoded AVI look suspicious.
            "info", "iarl", "iart", "icms", "icmt", "icop", "icrd", "icrp", "idim", "idpi",
            "ieng", "ignr", "ikey", "ilgt", "imed", "inam", "iplt", "iprd", "isbj", "isft",
            "ishp", "isrc", "isrf", "itch", "itrk", "idit", "ismp",
        ]
        
        suspicious_count = 0
        for chunk in chunks_list:
            sub_chunks = chunk.get("sub_chunks", [])

            # Flag chunks whose fourCC tag isn't a standard AVI chunk type (e.g. an injected
            # 'stEg' carrier). The old "raw/unparsed data" name heuristic was dropped - it
            # false-flagged the raw video/audio stream payload on every valid AVI. Data hidden
            # in a padding (JUNK) chunk is caught by riff_integrity instead.
            tag_value = None
            for sub in sub_chunks:
                # RIFF (AVI) format often uses 'id' instead of 'tag'
                if sub.get("name", "").lower() in ["tag", "id"]:
                    tag_value = sub.get("value", "").replace('"', '').strip().lower()
                    break

            if tag_value and tag_value not in STANDARD_AVI_CHUNKS:
                # AVI streams use tags like '00dc', '01wb', etc. for video/audio frames - not anomalies
                is_stream_chunk = len(tag_value) == 4 and tag_value.endswith(("dc", "wb", "db", "pc"))
                if not is_stream_chunk:
                    chunk["is_suspicious"] = True
                    chunk["suspicious_reason"] = f"Non-standard AVI chunk tag: '{tag_value}'"
                    suspicious_count += 1

            if isinstance(sub_chunks, list) and len(sub_chunks) > 0:
                suspicious_count += self._tag_suspicious_chunks(sub_chunks)

        return suspicious_count


