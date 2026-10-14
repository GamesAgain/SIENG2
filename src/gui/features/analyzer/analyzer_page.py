from pathlib import Path

from PyQt6.QtCore import QSize, pyqtSignal
from PyQt6.QtWidgets import QFrame, QLabel, QMessageBox, QTabWidget, QVBoxLayout

from src.core.analyzer import (
    AnalyzerFileType,
    SUPPORTED_ANALYZER_EXTENSIONS,
    analyze_bit_statistics,
    analyze_file_structure,
    analyze_metadata,
    announce_tab,
    handle_uploaded_file,
)
from src.gui.components.gui_utils import create_icon_state, format_file_size, truncate_text_middle
from src.gui.components.widgets.files_drop import FileDropWidget
from src.gui.components.widgets.file_info_bar import FileInfoBar
from src.gui.features.analyzer.analysis_runner import (
    BitStatisticsAnalysisResult,
    fingerprint_file,
    run_bit_statistics_analysis,
)
from src.gui.features.analyzer.bit_statistics_tab import BitStatisticsTab
from src.gui.services.worker import FunctionWorker
from src.path import svg_path


class AnalyzerPage(QFrame):
    """File selection and placeholder tabs for the Analyzer feature."""

    analysis_requested = pyqtSignal(str)
    analysis_completed = pyqtSignal(object)
    analysis_failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_path: str | None = None
        self.file_type: AnalyzerFileType | None = None
        self.analysis_result: BitStatisticsAnalysisResult | None = None
        self._analysis_request_id = 0
        self._analysis_workers: dict[int, FunctionWorker] = {}
        self._analysis_function = run_bit_statistics_analysis
        self.setup_ui()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        self.drop_zone = FileDropWidget(
            text="Drop file here or click to browse",
            sub_text="Supported: .png, .wav, .avi",
            icon_path=str(svg_path("file.svg")),
            allowed_extensions=list(SUPPORTED_ANALYZER_EXTENSIONS),
            show_preview=False,
        )
        self.drop_zone.setFixedHeight(100)
        self.drop_zone.file_selected.connect(self.on_file_selected)
        layout.addWidget(self.drop_zone)

        self.file_info_bar = FileInfoBar()
        self.file_info_bar.change_file_requested.connect(self.on_change_file_clicked)
        self.run_analysis_button = self.file_info_bar.add_extra_button("Run Analysis")
        self.run_analysis_button.clicked.connect(self.on_run_analysis_clicked)
        self.cancel_analysis_button = self.file_info_bar.add_extra_button("Cancel")
        self.cancel_analysis_button.clicked.connect(self.cancel_analysis)
        self.cancel_analysis_button.hide()
        self.file_info_bar.hide()
        layout.addWidget(self.file_info_bar)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("siengTabs")
        self.tabs.setIconSize(QSize(16, 16))
        self.tabs.addTab(self.make_placeholder("File Structure"), create_icon_state(str(svg_path("file-search.svg"))), "File Structure")
        self.tabs.addTab(self.make_placeholder("Metadata"), create_icon_state(str(svg_path("tags.svg"))), "Metadata")
        self.bit_statistics_tab = BitStatisticsTab()
        self.tabs.addTab(self.bit_statistics_tab, create_icon_state(str(svg_path("chart-histogram.svg"))), "Bit Statistics")
        self.tabs.currentChanged.connect(self.on_analyzer_tab_changed)
        layout.addWidget(self.tabs, 1)

    def make_placeholder(self, title: str) -> QFrame:
        """Keep tab layout ready for the analysis widgets added later."""
        page = QFrame()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(16, 16, 16, 16)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_title = QLabel(title)
        card_title.setObjectName("cardTitle")
        hint = QLabel("Analysis results will appear here.")
        hint.setObjectName("hintLabel")
        card_layout.addWidget(card_title)
        card_layout.addWidget(hint)
        card_layout.addStretch()
        page_layout.addWidget(card, 1)
        return page

    def on_file_selected(self, file_path: str) -> None:
        """Show file details after browse or drop."""
        if not file_path:
            self._invalidate_analysis()
            self.file_path = None
            self.file_type = None
            self.file_info_bar.hide()
            self.drop_zone.show()
            return
        path = Path(file_path).resolve()
        try:
            file_type = handle_uploaded_file(str(path))
            size_text = format_file_size(path.stat().st_size)
        except (OSError, ValueError) as exc:
            self.drop_zone.clear_file()
            QMessageBox.warning(self, "Invalid file", str(exc))
            return

        detail = f"{size_text} | {file_type.media_type.title()} | {file_type.format_name}"
        self._invalidate_analysis()
        self.file_path = str(path)
        self.file_type = file_type
        self.bit_statistics_tab.set_media_type(file_type.media_type)
        self.file_info_bar.update_info(
            self.file_path,
            truncate_text_middle(path.name, 70),
            detail,
            [(file_type.format_name, "blue")],
        )
        self.run_analysis_button.setText(
            "Run Placeholder" if file_type.media_type == "audio" else "Run Analysis"
        )
        self.drop_zone.hide()
        self.file_info_bar.show()
        self._dispatch_current_tab()

    def on_change_file_clicked(self) -> None:
        # clear_file emits an empty path; on_file_selected owns the reset.
        self.drop_zone.clear_file()

    def on_run_analysis_clicked(self) -> None:
        """Run all bit-statistics detectors outside the UI thread."""
        if not self.file_path or not self.file_type:
            return

        if self.file_type.media_type == "audio":
            analyze_bit_statistics(self.file_path)
            return

        parameters = self.bit_statistics_tab.analysis_parameters
        validation_error = parameters.validation_error()
        if validation_error:
            QMessageBox.warning(self, "Analysis Parameters", validation_error)
            return

        self._analysis_request_id += 1
        request_id = self._analysis_request_id
        image_path = self.file_path
        self.analysis_result = None
        self.bit_statistics_tab.clear_analysis_result()
        self._set_analysis_running(True)

        worker = FunctionWorker(self._analysis_function, image_path, parameters, report_progress=True)
        worker._kwargs["cancel_check"] = worker.isInterruptionRequested
        worker.progress.connect(lambda percent, message, current_id=request_id:
                                self._analysis_progress(current_id, percent, message))
        self._analysis_workers[request_id] = worker
        worker.done.connect(
            lambda result, current_id=request_id: self._analysis_finished(
                current_id, result
            )
        )
        worker.finished.connect(
            lambda current_id=request_id: self._cleanup_analysis_worker(current_id)
        )
        worker.finished.connect(worker.deleteLater)
        worker.start()
        self.analysis_requested.emit(image_path)

    def _analysis_finished(self, request_id: int, result) -> None:
        """Accept only the newest result for the currently selected file."""
        if request_id != self._analysis_request_id:
            return

        if isinstance(result, dict) and result.get("error"):
            self._analysis_error(result["error"])
            return
        if not isinstance(result, BitStatisticsAnalysisResult):
            self._analysis_error("The analyzer returned an invalid result.")
            return
        if not self.file_path or result.file_path != str(Path(self.file_path).resolve()):
            return

        try:
            current_fingerprint = fingerprint_file(self.file_path)
        except (OSError, RuntimeError) as exc:
            self._analysis_error(str(exc))
            return
        if current_fingerprint != result.file_fingerprint:
            self._analysis_error(
                "The selected file changed after analysis. Run it again."
            )
            return

        self.analysis_result = result
        self.bit_statistics_tab.set_analysis_result(result)
        self._set_analysis_running(False)
        self.tabs.setCurrentWidget(self.bit_statistics_tab)
        self.analysis_completed.emit(result)

    def _analysis_error(self, message: str) -> None:
        self.analysis_result = None
        self.bit_statistics_tab.clear_analysis_result()
        self._set_analysis_running(False)
        self.analysis_failed.emit(message)
        QMessageBox.warning(self, "Analysis Failed", message)

    def _invalidate_analysis(self) -> None:
        """Make pending callbacks stale and clear results from the old file."""
        self._analysis_request_id += 1
        for worker in self._analysis_workers.values():
            worker.requestInterruption()
        self.analysis_result = None
        if hasattr(self, "bit_statistics_tab"):
            self.bit_statistics_tab.clear_analysis_result()
        if hasattr(self, "run_analysis_button"):
            self._set_analysis_running(False)

    def _set_analysis_running(self, running: bool) -> None:
        self.run_analysis_button.setEnabled(not running)
        self.cancel_analysis_button.setVisible(running)
        if running:
            button_text = "Analyzing..."
        elif self.file_type and self.file_type.media_type == "audio":
            button_text = "Run Placeholder"
        else:
            button_text = "Run Analysis"
        self.run_analysis_button.setText(button_text)

    def cancel_analysis(self) -> None:
        self._invalidate_analysis()

    def _analysis_progress(self, request_id, percent, message):
        if request_id == self._analysis_request_id:
            self.run_analysis_button.setText(f"{percent}% · {message}")

    def on_analyzer_tab_changed(self, _index: int) -> None:
        """Dispatch the selected placeholder tab for the current file."""
        self._dispatch_current_tab()

    def _dispatch_current_tab(self) -> None:
        if not self.file_path:
            return

        tab_name = self.tabs.tabText(self.tabs.currentIndex())
        if tab_name == "File Structure":
            analyze_file_structure(self.file_path)
        elif tab_name == "Metadata":
            analyze_metadata(self.file_path)
        else:
            announce_tab(self.file_path, tab_name)

    def _cleanup_analysis_worker(self, request_id: int) -> None:
        self._analysis_workers.pop(request_id, None)
