"""PCM decoding, detector parity, and offscreen detail integration."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
import wave

import numpy as np
from PyQt6.QtWidgets import QApplication, QLabel, QTableWidget, QTableView

from src.core.analyzer.bit_statistics.chi_square import chi_square_pov
from src.core.analyzer.bit_statistics.rs_analysis import rs_core, estimate_rs_payload
from src.core.analyzer.bit_statistics.spa import collect_spa_statistics, estimate_spa
from src.core.analyzer.bit_statistics.audio.wav_io import read_wav
from src.core.analyzer.bit_statistics.audio.detectors import chi_counts, chi_result, spa_statistics
from src.core.analyzer import detect_file_type
from src.gui.features.analyzer.analysis_parameters_dialog import AnalysisParameters
from src.gui.features.analyzer.analysis_runner import run_bit_statistics_analysis
from src.gui.features.analyzer.bit_statistics_tab import BitStatisticsTab
from src.gui.features.analyzer.analysis_export import export_analysis
from src.path import DEFAULT_QSS_PATH


class AudioAnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        rng = np.random.default_rng(17)
        cls.samples8 = rng.integers(0, 256, (2000, 2), dtype=np.uint8)
        cls.samples16 = rng.integers(-200, 200, (2000, 2), dtype=np.int16)
        for bits, samples in ((8, cls.samples8), (16, cls.samples16)):
            with wave.open(str(cls.root / f"pcm{bits}.wav"), "wb") as output:
                output.setnchannels(2)
                output.setsampwidth(bits // 8)
                output.setframerate(8000)
                output.writeframes(samples.tobytes())
        cls.params = AnalysisParameters(prefix_step=25, segment_percent=50, segment_step=25)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_pcm_values_and_signed_lsb(self):
        for bits, expected in ((8, self.samples8), (16, self.samples16)):
            info, actual = read_wav(str(self.root / f"pcm{bits}.wav"))
            self.assertEqual(info["bits_per_sample"], bits)
            self.assertEqual(info["channel_names"], ["Left", "Right"])
            np.testing.assert_array_equal(actual, expected)
        self.assertEqual(int(self.samples16[0, 0]) ^ 1,
                         int(np.asarray(self.samples16[0, 0], dtype=np.int32) ^ 1))

    def test_eight_bit_matches_image_statistics(self):
        result = run_bit_statistics_analysis(str(self.root / "pcm8.wav"), self.params)
        left = self.samples8[:, 0].reshape(1, -1)
        self.assertEqual(asdict(result.chi_square["Left"]["whole"]),
                         asdict(chi_square_pov(left, self.params.min_expected)))
        self.assertEqual(asdict(result.rs["Left"]["whole"]), asdict(rs_core(left)))
        self.assertEqual(asdict(result.rs["Left"]["payload"]),
                         asdict(estimate_rs_payload(left)))
        statistics = collect_spa_statistics(left)
        self.assertEqual(asdict(result.spa["Left"]["statistics"]), asdict(statistics))
        self.assertEqual(asdict(result.spa["Left"]["estimate"]),
                         asdict(estimate_spa(statistics)))
        self.assertEqual(result.chi_square["Whole"]["whole"].sample_count, 4000)
        self.assertEqual(result.spa["Whole"]["statistics"].pair_count, 2000)
        self.assertEqual(result.rs["Whole"]["whole"].total_groups, 1000)

    def test_sixteen_bit_ranges_and_gui(self):
        result = run_bit_statistics_analysis(str(self.root / "pcm16.wav"), self.params)
        self.assertEqual(result.media_type, "audio")
        self.assertEqual(result.audio_info["samples_per_channel"], 2000)
        for detector in (result.chi_square, result.rs, result.spa):
            self.assertEqual(list(detector), ["Whole", "Left", "Right"])
            self.assertEqual(detector["Left"]["progressive_prefix"][-1].end, 2000)
            self.assertEqual(detector["Left"]["segments"][-1].end, 2000)
        self.assertEqual(asdict(result.chi_square["Left"]["whole"]),
                         asdict(result.chi_square["Left"]["progressive_prefix"][-1].chi_square))
        self.assertEqual(asdict(result.rs["Left"]["whole"]),
                         asdict(result.rs["Left"]["progressive_prefix"][-1].measurement.rs))
        self.assertEqual(asdict(result.spa["Left"]["estimate"]),
                         asdict(result.spa["Left"]["progressive_prefix"][-1].estimate))
        tab = BitStatisticsTab()
        tab.set_analysis_result(result)
        self.assertTrue(any("PCM 16-bit" in label.text() for label in tab.findChildren(QLabel)))
        self.assertTrue(tab.findChildren(QTableWidget))
        tab.select_detector("rs")
        tab._select_detail_tab("segments")
        self.assertTrue(tab.findChildren(QTableView))
        tab.select_detector("spa")
        tab._select_detail_tab("raw")
        self.assertTrue(tab.findChildren(QTableWidget))
        tab.close()

    def test_unsupported_pcm_width(self):
        path = self.root / "pcm24.wav"
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(3)
            output.setframerate(8000)
            output.writeframes(bytes(60))
        with self.assertRaisesRegex(ValueError, "8/16-bit"):
            read_wav(str(path))
        fake = self.root / "fake.wav"
        fake.write_bytes(b"not a WAVE file")
        with self.assertRaisesRegex(ValueError, "RIFF/WAVE"):
            detect_file_type(str(fake))

    def test_signed_pov_and_pair_counts(self):
        values = np.array([-2] * 500 + [-1] * 100 + [0] * 500 + [1] * 100,
                          dtype=np.int16)
        cover = chi_result(chi_counts(values, 16), 5)
        rng = np.random.default_rng(8)
        embedded = (values.astype(np.int32) & ~1) | rng.integers(0, 2, len(values))
        stego = chi_result(chi_counts(embedded, 16), 5)
        self.assertEqual(cover.valid_pairs, 2)
        self.assertEqual(stego.valid_pairs, 2)
        self.assertGreater(stego.p_value, cover.p_value)
        self.assertEqual(spa_statistics(np.array([-2, -1, 0, 1], dtype=np.int16)).pair_count, 2)

    def test_audio_tabs_channels_and_export(self):
        result = run_bit_statistics_analysis(str(self.root / "pcm8.wav"), self.params)
        self.app.setStyleSheet(DEFAULT_QSS_PATH.read_text(encoding="utf-8"))
        tab = BitStatisticsTab()
        tab.resize(1400, 900)
        tab.show()
        tab.set_analysis_result(result)
        self.app.processEvents()
        snapshots = Path(__file__).resolve().parents[1] / ".pytest-tmp"
        snapshots.mkdir(exist_ok=True)
        self.assertTrue(tab.grab().save(str(snapshots / "wav-chi-square.png")))
        for detector in ("chi_square", "rs", "spa"):
            tab.select_detector(detector)
            for channel in ("Whole", "Left", "Right"):
                tab._select_channel(channel)
                for selected in ("distribution", "prefix", "segments", "raw"):
                    tab._select_detail_tab(selected)
                    self.assertTrue(tab.findChildren(QTableView) or tab.findChildren(QTableWidget))
        destination = self.root / "audio.json"
        export_analysis(result, destination)
        document = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(document["media_type"], "audio")
        self.assertEqual(document["file"]["bits_per_sample"], 8)
        self.assertEqual(document["results"]["spa"]["Left"]["segments"][-1]["end"], 2000)
        tab.close()


if __name__ == "__main__":
    unittest.main()
