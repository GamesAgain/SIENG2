import os
import base64
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any
from src.core.analyzer.external_tools.exiftool_wrapper import extract_metadata
from src.core.analyzer.modules.metadata_analyzer import MetadataAnalyzer
from src.core.analyzer.external_tools.binwalk_wrapper import run_binwalk, entropy_scan
from src.core.analyzer.external_tools.hachoir_wrapper import extract_file_structure

class BaseFormatHandler(ABC):
    # Entropy analysis only tells hidden-data from carrier on a low-entropy (uncompressed) medium.
    # On compressed carriers (PNG/JPEG/MJPG-AVI) the whole file is already ~1.0, so the header ->
    # compressed-stream transition looks identical to an embedded encrypted blob. Reliable formats
    # opt in; the others skip the anomaly to avoid false positives.
    _entropy_reliable = False

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
        # hachoir, binwalk and the entropy scan are independent external tools (binwalk alone is
        # ~4s and dominates). subprocess.run releases the GIL, so running them on a small thread
        # pool genuinely overlaps their wall-time; meanwhile we read the raw bytes and run the
        # in-process integrity checks on this thread.
        with ThreadPoolExecutor(max_workers=3) as pool:
            f_hachoir = pool.submit(extract_file_structure, self.file_path)
            f_binwalk = pool.submit(run_binwalk, self.file_path)
            f_entropy = pool.submit(entropy_scan, self.file_path) if self._entropy_reliable else None

            # Raw-byte integrity: overlay (from the format's own declared end, not the
            # parser's consumed size) + format-specific tampering signals (PNG CRC / RIFF JUNK)
            with open(self.file_path, "rb") as f:
                raw = f.read()
            integrity = self._integrity_report(raw)

            hachoir_data = f_hachoir.result()
            binwalk_data = f_binwalk.result()
            entropy = f_entropy.result() if f_entropy else {"high_entropy_offsets": []}

        # entropy analysis: an interior jump into near-random data flags an embedded encrypted blob
        # (only meaningful on low-entropy carriers - see _entropy_reliable).
        for offset in entropy.get("high_entropy_offsets", []):
            integrity.setdefault("anomalies", []).append({
                "type": "high_entropy",
                "detail": f"High-entropy (encrypted/compressed) region begins at offset 0x{offset:X} "
                          f"- possible hidden encrypted payload",
            })

        content_end = integrity.get("content_end")
        has_overlay = content_end is not None and self.file_size > content_end
        overlay_size = (self.file_size - content_end) if has_overlay else 0
        # first bytes of the appended data, so the GUI can show the user *what* was hidden
        # (a colored node + hex/text preview) instead of only reporting that something exists.
        overlay_preview_b64 = (base64.b64encode(raw[content_end:content_end + 512]).decode("ascii")
                               if has_overlay else "")

        return {
            "hachoir_raw": hachoir_data,
            "binwalk_raw": binwalk_data,
            "actual_size_bytes": self.file_size,
            "integrity_anomalies": integrity.get("anomalies", []),
            "overlay_analysis": {
                "has_overlay": has_overlay,
                "overlay_offset": content_end if has_overlay else None,
                "overlay_size_bytes": overlay_size,
                "preview_b64": overlay_preview_b64,
                "message": f"Found {overlay_size} bytes of appended data (Overlay)." if has_overlay else "No overlay data found."
            }
        }

    def _integrity_report(self, raw: bytes) -> Dict[str, Any]:
        """Format-specific raw-byte checks. Overridden per format; default = nothing
        (content_end None means overlay detection is skipped for that format)."""
        return {"content_end": None, "anomalies": []}

    def add_mediainfo(self, structure_results: Dict[str, Any]):
        """Attach mediainfo's stream summary and flag bytes the streams don't account for (beyond
        any trailing overlay we already report). Used by the audio/video (RIFF) handlers."""
        from src.core.analyzer.external_tools.mediainfo_wrapper import probe
        mi = probe(self.file_path)
        if mi.get("error"):
            return
        structure_results["mediainfo"] = mi

        overlay = structure_results.get("overlay_analysis", {})
        overlay_size = overlay.get("overlay_size_bytes", 0) if overlay.get("has_overlay") else 0
        hidden_gap = mi.get("unaccounted_bytes", 0) - overlay_size
        # generous floor: container headers/index legitimately aren't counted as stream bytes,
        # so only a large unexplained gap is worth raising.
        if hidden_gap > max(16384, int(mi.get("file_size", 0) * 0.10)):
            structure_results.setdefault("integrity_anomalies", []).append({
                "type": "stream_gap",
                "detail": f"{hidden_gap} bytes are inside the container but not part of any media "
                          f"stream (mediainfo) - possible hidden data",
            })

    @abstractmethod
    def analyze(self) -> Dict[str, Any]:
        """
        Abstract method to be implemented by format-specific handlers.
        Should return a dictionary containing all analysis results.
        """
        pass
