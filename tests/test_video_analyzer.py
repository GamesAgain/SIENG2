"""Backend equivalence and offscreen upload/detail integration using lossless AVI."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import asdict, replace
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import wave

import cv2
import numpy as np
from PIL import Image
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton, QFrame, QLabel
from PyQt6.QtGui import QFont, QFontDatabase

from src.core.analyzer import detect_file_type, analyze_bit_statistics
from src.core.analyzer.formats.video import analyze_video_frame_details
from src.core.analyzer.bit_statistics.video.video_io import iter_frames
from src.gui.features.analyzer.analysis_parameters_dialog import AnalysisParameters, AnalysisParametersDialog
from src.gui.features.analyzer.analysis_runner import run_bit_statistics_analysis
from src.gui.features.analyzer.analysis_export import export_analysis
from src.gui.features.analyzer.analyzer_page import AnalyzerPage
from src.gui.features.analyzer.bit_statistics_tab import BitStatisticsTab
from src.path import DEFAULT_QSS_PATH


class VideoAnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
        cls.app.setFont(QFont("Segoe UI", 10))
        cls.app.setStyleSheet(DEFAULT_QSS_PATH.read_text(encoding="utf-8"))
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.avi = cls.root / "stego.avi"
        rng = np.random.default_rng(42)
        cover = rng.integers(0, 256, (64, 80, 3), dtype=np.uint8)
        cls.frames = []
        writer = cv2.VideoWriter(str(cls.avi), cv2.VideoWriter_fourcc(*"FFV1"), 25, (80, 64))
        if not writer.isOpened():
            raise RuntimeError("FFV1 lossless AVI encoder unavailable")
        for i in range(6):
            frame = cover.copy()
            if i < 3:
                frame = (frame & 254) | rng.integers(0, 2, frame.shape, dtype=np.uint8)
            cls.frames.append(frame)
            writer.write(frame[:, :, ::-1])
        writer.release()
        cls.png = cls.root / "frame.png"
        Image.fromarray(cls.frames[0]).save(cls.png)
        cls.params = AnalysisParameters(prefix_step=25, segment_percent=50, segment_step=25)
        cls.result = run_bit_statistics_analysis(str(cls.avi), cls.params)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def wait_for(self, predicate, timeout=20):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertTrue(predicate(), "Async operation did not finish")

    def test_lossless_decode_and_original_detector_equivalence(self):
        frames = [frame for _, frame in iter_frames(str(self.avi))]
        for actual, expected in zip(frames, self.frames):
            np.testing.assert_array_equal(actual, expected)
        source = Path(__file__).resolve().parents[3] / "games_workspace" / "video_detector"
        sys.path.insert(0, str(source))
        try:
            for key, filename, class_name, kwargs in (
                ("chi_square", "chi_square", "ChiSquareVideo", {"min_expected": 5}),
                ("rs", "rs_analysis", "RSVideo", {}),
                ("spa", "spa", "SPAVideo", {"j": 30, "min_pairs": 100}),
            ):
                name = "reference_" + filename
                spec = importlib.util.spec_from_file_location(name, source / (filename + ".py"))
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                detector = getattr(module, class_name)(64, 80, prefix_step=25,
                    segment_percent=50, segment_step=25, **kwargs)
                for frame in frames:
                    detector.add(frame)
                expected = detector.finish()["targets"]
                actual = getattr(self.result, key)["targets"]
                for channel in expected:
                    for field in expected[channel]:
                        def plain(value):
                            if isinstance(value, list):
                                return [asdict(item) for item in value]
                            return asdict(value)
                        self.assertEqual(plain(actual[channel][field]), plain(expected[channel][field]),
                                         (key, channel, field))
        finally:
            sys.path.remove(str(source))

    def test_exact_frame_matches_png_for_all_detectors(self):
        frame = analyze_video_frame_details(str(self.avi), 0, self.params)
        image = run_bit_statistics_analysis(str(self.png), self.params)
        for detector in ("chi_square", "rs", "spa"):
            actual, expected = frame[detector], getattr(image, detector)
            for channel in expected:
                for field in expected[channel]:
                    def plain(value):
                        return [asdict(item) for item in value] if isinstance(value, list) else asdict(value)
                    self.assertEqual(plain(actual[channel][field]), plain(expected[channel][field]),
                                     (detector, channel, field))

    def test_scope_aliases_export_and_cancel(self):
        result = run_bit_statistics_analysis(str(self.avi), replace(self.params, start_frame=2, frame_count=3))
        self.assertEqual(result.video_info["decoded_frame_count"], 3)
        self.assertEqual(result.video_info["start_frame"], 2)
        self.assertEqual(result.video_info["end_frame"], 5)
        for name in ("chi_square", "rs", "spa"):
            target = getattr(result, name)["targets"]["Whole"]
            self.assertIs(target["progressive_prefix"], target["temporal_prefix"])
            self.assertIs(target["frame_segments"], target["temporal_segments"])
            self.assertEqual(target["progressive_prefix"][-1].end, 3)
        destination = self.root / "export.json"
        export_analysis(result, destination)
        document = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(document["media_type"], "video")
        self.assertEqual(document["file"]["start_frame"], 2)
        self.assertIn("statistics", document["results"]["spa"]["targets"]["Whole"])
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            analyze_bit_statistics(str(self.avi), cancel_check=lambda: True)
        with self.assertRaisesRegex(ValueError, "No frames"):
            analyze_bit_statistics(str(self.avi), start_frame=100)

    def test_all_video_views_channels_and_png_switch(self):
        tab = BitStatisticsTab()
        tab.resize(1300, 900)
        tab.set_analysis_result(self.result)
        panel = tab.video_panel
        panel.cache[0] = analyze_video_frame_details(str(self.avi), 0, self.params)
        tab.show()
        for detector in ("chi_square", "rs", "spa"):
            tab.select_detector(detector)
            for channel in ("Whole", "R", "G", "B"):
                panel.select_channel(channel)
                panel.select_level("whole")
                tabs = ["prefix", "segments", "raw"]
                if detector != "chi_square":
                    tabs.insert(0, "overview")
                for view in tabs:
                    panel.select_tab(view)
                    self.app.processEvents()
                    self.assertFalse(panel.grab().isNull())
                    scope_buttons = [b for b in panel.body.findChildren(QPushButton)
                                     if b.text() in ("Whole Video", "Per Frame") and not b.isHidden()]
                    self.assertEqual(len(scope_buttons), 2)
                    self.assertTrue(all(b.objectName() == "analysisChannelButton" for b in scope_buttons))
                    cards = panel.body.findChildren(QFrame, "analysisSummaryCard")
                    self.assertEqual(len(cards), 2)
                    self.assertFalse(any("All Frames" in b.text() for b in panel.body.findChildren(QPushButton)))
                panel.select_level("frame")
                for view in ({"chi_square": ("prefix", "segments", "raw", "timeline"),
                              "rs": ("distribution", "prefix", "raw", "timeline"),
                              "spa": ("distribution", "raw", "timeline")}[detector]):
                    panel.select_frame_tab(view)
                    self.app.processEvents()
                    self.assertFalse(panel.grab().isNull())
        panel.select_frame(1)
        self.wait_for(lambda: panel.pending_frame is None)
        self.assertIsNone(panel.frame_error)
        self.assertIn(1, panel.cache)
        self.wait_for(lambda: not panel.workers)
        tab.set_analysis_result(run_bit_statistics_analysis(str(self.png), self.params))
        self.assertIsNone(tab.video_panel)
        for name in ("chi_square", "rs", "spa"):
            tab.select_detector(name)
            self.app.processEvents()
        tab.close()

    def test_upload_run_invalidation_and_audio(self):
        page = AnalyzerPage()
        warnings = []
        original = QMessageBox.warning
        QMessageBox.warning = lambda *args: warnings.append(args[2])
        try:
            page.on_file_selected(str(self.avi))
            self.assertEqual(page.file_type.media_type, "video")
            self.assertEqual(page.run_analysis_button.text(), "Run Analysis")
            page.on_run_analysis_clicked()
            self.wait_for(lambda: page.analysis_result is not None or warnings)
            self.assertEqual(warnings, [])
            self.assertEqual(page.analysis_result.media_type, "video")
            self.wait_for(lambda: not page._analysis_workers)
            page.on_run_analysis_clicked()
            page.on_file_selected(str(self.png))
            self.wait_for(lambda: not page._analysis_workers)
            self.assertIsNone(page.analysis_result)
            page.on_run_analysis_clicked()
            self.wait_for(lambda: page.analysis_result is not None or warnings)
            self.assertEqual(warnings, [])
            self.assertEqual(page.analysis_result.media_type, "image")
            self.wait_for(lambda: not page._analysis_workers)
            wav = self.root / "placeholder.wav"
            with wave.open(str(wav), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(1)
                output.setframerate(8000)
                output.writeframes(self.frames[0][:, :, 0].ravel().tobytes())
            page.on_file_selected(str(wav))
            self.assertEqual(page.run_analysis_button.text(), "Run Analysis")
            page.on_run_analysis_clicked()
            self.wait_for(lambda: page.analysis_result is not None or warnings)
            self.assertEqual(warnings, [])
            self.assertEqual(page.analysis_result.media_type, "audio")
            dialog = AnalysisParametersDialog(self.params, media_type="video")
            dialog.start_frame_input.setValue(2)
            dialog.frame_count_input.setValue(3)
            dialog._save_parameters()
            self.assertEqual(dialog.parameters.start_frame, 2)
            self.assertEqual(dialog.parameters.frame_count, 3)
            fake = self.root / "fake.png"
            Image.fromarray(self.frames[0]).save(fake, format="JPEG")
            with self.assertRaises(ValueError):
                detect_file_type(str(fake))
        finally:
            QMessageBox.warning = original
            page.cancel_analysis()
            for worker in list(page._analysis_workers.values()):
                worker.wait()
            page.close()

    def test_full_main_window_and_visual_snapshots(self):
        from src.gui.app.main_window import MainWindow
        window = MainWindow()
        window.show()
        page = window.page_stack.widget(3)
        window.page_stack.setCurrentIndex(3)
        page.on_file_selected(str(self.avi))
        page.analysis_result = self.result
        page.bit_statistics_tab.analysis_parameters = self.params
        page.bit_statistics_tab.set_analysis_result(self.result)
        page.tabs.setCurrentWidget(page.bit_statistics_tab)
        self.app.processEvents()
        output = Path(__file__).resolve().parents[1] / ".pytest-tmp"
        output.mkdir(exist_ok=True)
        self.assertTrue(window.grab().save(str(output / "avi-whole.png")))
        panel = page.bit_statistics_tab.video_panel
        panel.cache[0] = analyze_video_frame_details(str(self.avi), 0, self.params)
        page.bit_statistics_tab.select_detector("spa")
        panel.select_level("frame")
        self.app.processEvents()
        self.assertTrue(window.grab().save(str(output / "avi-frame-spa.png")))
        page.bit_statistics_tab.clear_analysis_result()
        window.close()


if __name__ == "__main__":
    unittest.main()
