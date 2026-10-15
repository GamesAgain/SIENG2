"""Structure/metadata contract and GUI regressions without requiring Docker."""

import os
import struct
import tempfile
import unittest
import zlib
import json
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from src.core.analyzer.inspection import service
from src.core.analyzer.inspection import bridge
from src.gui.features.analyzer.analysis_runner import fingerprint_file
from src.gui.features.analyzer.inspection_runner import InspectionResult
from src.gui.features.analyzer.inspection_tabs import FileStructureTab, MetadataTab
from src.gui.features.analyzer.analysis_export import export_analysis


def png_chunk(kind, payload=b""):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


class InspectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_png_crc_and_overlay(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "carrier.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", b"1234567890123") + png_chunk(b"IEND") + b"payload")
            report = service._png_integrity(path)
            self.assertEqual(report["anomalies"], [])
            self.assertEqual(path.stat().st_size - report["content_end"], 7)
            raw = bytearray(path.read_bytes())
            raw[20] ^= 1
            path.write_bytes(raw)
            self.assertEqual(service._png_integrity(path)["anomalies"][0]["type"], "crc_error")

    def test_riff_junk_and_avix_are_not_false_overlay(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "carrier.avi"
            junk = b"JUNK" + struct.pack("<I", 32) + bytes(range(32))
            first = b"RIFF" + struct.pack("<I", 4 + len(junk)) + b"AVI " + junk
            second = b"RIFF" + struct.pack("<I", 4) + b"AVIX"
            path.write_bytes(first + second)
            result = service._riff_integrity(path)
            self.assertEqual(result["content_end"], path.stat().st_size)
            self.assertEqual(result["anomalies"][0]["type"], "junk_stuffed")

    def test_tool_failure_is_partial_not_clean(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "carrier.wav"
            path.write_bytes(b"RIFF\x04\x00\x00\x00WAVE")
            with patch.object(service, "_metadata", return_value={"status": "error", "error": "exiftool missing", "raw_data": {}}), \
                 patch.object(service, "_hachoir", return_value={"structure": [], "error": "hachoir failed"}), \
                 patch.object(service, "_binwalk", return_value={"signatures": [], "error": "binwalk missing"}), \
                 patch.object(service, "_mediainfo", return_value={"error": "mediainfo missing"}):
                result = service.inspect_file(str(path))
            self.assertEqual(result["structure_analysis"]["status"], "partial")
            self.assertEqual(result["metadata_analysis"]["status"], "error")
            structure = FileStructureTab()
            metadata = MetadataTab()
            structure.load_data(result)
            metadata.load_data(result)
            self.assertIn("incomplete", structure.summary_list.item(0).text())
            self.assertIn("failed", metadata.status_label.text())

    def test_metadata_markers_and_timezone(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "carrier.png"
            path.write_bytes(b"x")
            output = json.dumps([{"File:FileCreateDate": "2026:10:15 12:00:00+07:00",
                                  "PNG:Comment": "flag{example}"}])
            with patch.object(service, "_command", return_value=(output, None)):
                result = service._metadata(path)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(len(result["text_anomalies"]), 1)
            self.assertEqual(result["time_anomalies"], [])

    def test_tab_render_and_stale_result(self):
        from src.gui.features.analyzer.analyzer_page import AnalyzerPage
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "carrier.wav"
            path.write_bytes(b"RIFF\x04\x00\x00\x00WAVE")
            page = AnalyzerPage()
            page.on_file_selected(str(path))
            data = {"structure_analysis": {"hachoir_raw": {"structure": [{"name": "RIFF", "size_bytes": 12}]},
                                           "binwalk_raw": {"signatures": [{"offset": 0, "description": "RIFF"}]},
                                           "integrity_anomalies": [], "overlay_analysis": {}, "errors": []},
                    "metadata_analysis": {"raw_data": {"File:FileType": "WAV"}, "error": None}}
            page._analysis_request_id += 1
            request = page._analysis_request_id
            result = InspectionResult(str(path.resolve()), fingerprint_file(str(path)), data)
            page._inspection_finished(request, result)
            self.assertEqual(page.file_structure_tab.tree_widget.topLevelItemCount(), 1)
            self.assertEqual(page.metadata_tab.metadata_table.rowCount(), 1)
            page._invalidate_analysis()
            page._inspection_finished(request, result)
            self.assertEqual(page.metadata_tab.metadata_table.rowCount(), 0)
            page.deleteLater()

    def test_shared_inspection_is_in_export(self):
        from dataclasses import dataclass

        @dataclass
        class Parameters:
            spa_min_pairs: int = 100

        @dataclass
        class Result:
            media_type: str
            parameters: Parameters
            file_path: str
            file_fingerprint: object
            chi_square: dict
            rs: dict
            spa: dict
            image_info: dict
            video_info: dict
            audio_info: dict

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.wav"
            path.write_bytes(b"RIFF\x04\x00\x00\x00WAVE")
            report = Result("audio", Parameters(), str(path), fingerprint_file(str(path)), {}, {}, {}, {}, {}, {})
            output = Path(temp) / "result.json"
            export_analysis(report, output, {"structure_analysis": {"status": "ok"},
                                             "metadata_analysis": {"status": "error"}})
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["schema_version"], 5)
            self.assertEqual(data["inspection"]["metadata_analysis"]["status"], "error")

    def test_docker_bridge_mounts_only_selected_file_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.wav"
            path.write_bytes(b"RIFF\x04\x00\x00\x00WAVE")
            payload = {"structure_analysis": {}, "metadata_analysis": {}}
            with patch.object(bridge.subprocess, "Popen") as popen:
                process = popen.return_value
                process.communicate.return_value = (json.dumps(payload).encode(), b"")
                process.returncode = 0
                result = bridge.inspect(str(path))
            command = popen.call_args.args[0]
            self.assertEqual(result, payload)
            self.assertIn("--network", command)
            self.assertIn("none", command)
            self.assertIn(f"{path.resolve()}:/data/input.wav:ro", command)


if __name__ == "__main__":
    unittest.main()
