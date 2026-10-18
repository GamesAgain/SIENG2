from pathlib import Path

from PyQt6.QtCore import QSize, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
)

from src.gui.components.gui_utils import (
    create_icon_state,
    format_file_size,
    truncate_text_middle,
)
from src.gui.components.widgets.file_info_bar import FileInfoBar
from src.gui.components.widgets.files_drop import FileDropWidget
from src.core.analyzer.handle import (
    analyze,
    analyze_avi_frame_chi_square,
    analyze_avi_frame_rs,
)
from src.core.analyzer.models.analysis import AnalysisResult
from src.gui.features.analyzer.tabs.bit_statistics_tab import BitStatisticsTab
from src.gui.features.analyzer.tabs.file_structure_tab import FileStructureTab
from src.gui.features.analyzer.tabs.metadata_tab import MetadataTab
from src.gui.features.analyzer.inspection_runner import (
    InspectionResult,
    fingerprint_file,
    run_inspection,
)
from src.gui.services.worker import FunctionWorker
from src.path import svg_path


class AnalyzerPage(QFrame):
    analysis_requested = pyqtSignal(str)
    analysis_completed = pyqtSignal(object)
    analysis_failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_path: str | None = None
        self.analysis_result: AnalysisResult | None = None
        self._analysis_request_id = 0
        self._analysis_workers: dict[int, FunctionWorker] = {}
        self._inspection_workers: dict[int, FunctionWorker] = {}
        self._frame_analysis_workers: dict[
            tuple[int, str, int],
            FunctionWorker,
        ] = {}
        self._analysis_function = analyze
        self._inspection_function = run_inspection
        self.inspection_result: InspectionResult | None = None
        self._bit_pending = False
        self._inspection_pending = False
        self.setup_ui()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        self.drop_zone = FileDropWidget(
            text="Drop file here or click to browse",
            sub_text="Supported: .png, .wav, .avi",
            icon_path=str(svg_path("file.svg")),
            allowed_extensions=[".png", ".wav", ".avi"],
            show_preview=False,
        )

        self.drop_zone.setFixedHeight(100)
        self.drop_zone.file_selected.connect(self.on_file_selected)
        layout.addWidget(self.drop_zone)

        self.file_info_bar = FileInfoBar()
        self.file_info_bar.change_file_requested.connect(
            self.on_change_file_clicked
        )
        self.run_analysis_button = self.file_info_bar.add_extra_button(
            "Run Analysis"
        )
        self.run_analysis_button.clicked.connect(self.on_run_analysis_clicked)
        self.file_info_bar.hide()
        layout.addWidget(self.file_info_bar)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("siengTabs")
        self.tabs.setIconSize(QSize(16, 16))
        self.structure_tab = FileStructureTab()
        self.tabs.addTab(
            self.structure_tab,
            create_icon_state(str(svg_path("file-search.svg"))),
            "File Structure",
        )
        self.metadata_tab = MetadataTab()
        self.tabs.addTab(
            self.metadata_tab,
            create_icon_state(str(svg_path("tags.svg"))),
            "Metadata",
        )
        self.bit_statistics_tab = BitStatisticsTab()
        self.bit_statistics_tab.frame_detail_requested.connect(
            self._on_frame_detail_requested
        )
        self.tabs.addTab(
            self.bit_statistics_tab,
            create_icon_state(str(svg_path("chart-histogram.svg"))),
            "Bit Statistics",
        )
        layout.addWidget(self.tabs, 1)

    def on_file_selected(self, file_path: str) -> None:
        """Store a supported file selected through browse or drag-and-drop."""
        if not file_path:
            self._invalidate_analysis()
            self.file_path = None
            self.file_info_bar.hide()
            self.drop_zone.show()
            return

        try:
            path = Path(file_path).resolve(strict=True)
            if not path.is_file():
                raise ValueError("The selected path is not a file.")

            extension = path.suffix.lower()
            if extension not in {".png", ".wav", ".avi"}:
                raise ValueError(
                    f"Unsupported file format: {extension or '(no extension)'}"
                )

            size_text = format_file_size(path.stat().st_size)
        except (OSError, ValueError) as exc:
            self.drop_zone.clear_file()
            QMessageBox.warning(self, "Invalid file", str(exc))
            return

        self._invalidate_analysis()
        self.file_path = str(path)
        self.file_info_bar.update_info(
            self.file_path,
            truncate_text_middle(path.name, 70),
            f"{size_text} · Ready for analysis",
            [(extension[1:].upper(), "blue")],
        )
        self.drop_zone.hide()
        self.file_info_bar.show()

    def _invalidate_analysis(self) -> None:
        """Make pending callbacks stale and clear results from the old file."""
        self._analysis_request_id += 1
        for worker in self._inspection_workers.values():
            worker.requestInterruption()
        self.analysis_result = None
        self.inspection_result = None
        self._bit_pending = False
        self._inspection_pending = False
        self._clear_analysis_results()
        if hasattr(self, "run_analysis_button"):
            self._set_analysis_running(False)

    def _clear_analysis_results(self) -> None:
        """Restore every result tab to its waiting state."""
        for name in ("structure_tab", "metadata_tab", "bit_statistics_tab"):
            tab = getattr(self, name, None)
            if tab is not None:
                tab.clear_analysis_result()

    def _set_analysis_running(self, running: bool) -> None:
        self.run_analysis_button.setEnabled(not running)
        self.run_analysis_button.setText(
            "Analyzing..." if running else "Run Analysis"
        )

    def _refresh_running_state(self) -> None:
        self._set_analysis_running(self._bit_pending or self._inspection_pending)

    def _cleanup_analysis_worker(self, request_id: int) -> None:
        self._analysis_workers.pop(request_id, None)

    def _cleanup_inspection_worker(self, request_id: int) -> None:
        self._inspection_workers.pop(request_id, None)

    def _cleanup_frame_worker(
        self,
        key: tuple[int, str, int],
    ) -> None:
        self._frame_analysis_workers.pop(key, None)

    def _on_frame_detail_requested(
        self,
        detector: str,
        frame_index: int,
    ) -> None:
        """Analyze one AVI frame without blocking or replacing the page."""
        if not self.file_path or self.analysis_result is None:
            return
        if self.analysis_result.file.format != "AVI":
            return

        functions = {
            "chi_square": analyze_avi_frame_chi_square,
            "rs": analyze_avi_frame_rs,
        }
        function = functions.get(detector)
        if function is None:
            return

        request_id = self._analysis_request_id
        key = (request_id, detector, frame_index)
        if key in self._frame_analysis_workers:
            return

        worker = FunctionWorker(
            function,
            self.file_path,
            frame_index,
            self.analysis_result.parameters,
        )
        self._frame_analysis_workers[key] = worker
        worker.done.connect(
            lambda result, current_key=key: self._frame_detail_finished(
                current_key,
                result,
            )
        )
        worker.finished.connect(
            lambda current_key=key: self._cleanup_frame_worker(
                current_key
            )
        )
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _frame_detail_finished(
        self,
        key: tuple[int, str, int],
        result: object,
    ) -> None:
        """Keep only frame details belonging to the current AVI result."""
        request_id, detector, frame_index = key
        if request_id != self._analysis_request_id:
            return
        if isinstance(result, dict) and result.get("error"):
            self.bit_statistics_tab.set_frame_detail_error(
                detector,
                frame_index,
                str(result["error"]),
            )
            return
        self.bit_statistics_tab.set_frame_detail(detector, result)

    def on_change_file_clicked(self) -> None:
        # clear_file emits an empty path; on_file_selected owns the reset.
        self.drop_zone.clear_file()

    def on_run_analysis_clicked(self) -> None:
        """Run the selected file analysis outside the GUI thread."""
        if not self.file_path:
            return

        parameters = self.bit_statistics_tab.analysis_parameters
        try:
            parameters.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Analysis Parameters", str(exc))
            return

        self._analysis_request_id += 1
        request_id = self._analysis_request_id
        file_path = self.file_path

        self.analysis_result = None
        self.inspection_result = None
        self._clear_analysis_results()
        self.structure_tab.set_inspection_status("Inspecting file structure...")
        self.metadata_tab.set_inspection_status("Inspecting metadata...")
        self._bit_pending = True
        self._inspection_pending = True
        self._set_analysis_running(True)

        worker = FunctionWorker(
            self._analysis_function,
            file_path,
            parameters,
        )
        self._analysis_workers[request_id] = worker
        worker.done.connect(
            lambda result, current_id=request_id: self._analysis_finished(
                current_id,
                result,
            )
        )
        worker.finished.connect(
            lambda current_id=request_id: self._cleanup_analysis_worker(
                current_id
            )
        )
        worker.finished.connect(worker.deleteLater)
        worker.start()

        inspection_worker = FunctionWorker(self._inspection_function, file_path)
        if hasattr(inspection_worker, "_kwargs"):
            inspection_worker._kwargs["cancel_check"] = (
                inspection_worker.isInterruptionRequested
            )
        self._inspection_workers[request_id] = inspection_worker
        inspection_worker.done.connect(
            lambda result, current_id=request_id: self._inspection_finished(
                current_id,
                result,
            )
        )
        inspection_worker.finished.connect(
            lambda current_id=request_id: self._cleanup_inspection_worker(
                current_id
            )
        )
        inspection_worker.finished.connect(inspection_worker.deleteLater)
        inspection_worker.start()
        self.analysis_requested.emit(file_path)

    def _inspection_finished(self, request_id: int, result: object) -> None:
        """Accept inspection only when it still belongs to the selected file."""
        if request_id != self._analysis_request_id:
            return
        self._inspection_pending = False
        if isinstance(result, dict) and result.get("error"):
            detail = str(result["error"])
            self.structure_tab.set_inspection_status(
                "Structure inspection could not be completed."
            )
            self.metadata_tab.set_inspection_status(
                "Metadata inspection could not be completed."
            )
            QMessageBox.warning(
                self,
                "Structure and Metadata Inspection",
                "The inspection could not be completed.\n\n"
                f"Details:\n{detail}",
            )
            self._refresh_running_state()
            return
        if not isinstance(result, InspectionResult) or not self.file_path:
            detail = "Inspector returned an invalid result."
            self.structure_tab.set_inspection_status(
                "Structure inspection could not be completed."
            )
            self.metadata_tab.set_inspection_status(
                "Metadata inspection could not be completed."
            )
            QMessageBox.warning(
                self, "Structure and Metadata Inspection", detail
            )
            self._refresh_running_state()
            return
        try:
            valid = (
                result.file_path == str(Path(self.file_path).resolve())
                and result.file_fingerprint == fingerprint_file(self.file_path)
            )
        except OSError:
            valid = False
        if not valid:
            detail = "The file changed during inspection. Run it again."
            self.structure_tab.set_inspection_status(detail)
            self.metadata_tab.set_inspection_status(detail)
            QMessageBox.warning(
                self, "Structure and Metadata Inspection", detail
            )
            self._refresh_running_state()
            return
        self.inspection_result = result
        self.structure_tab.load_data(result.data)
        self.metadata_tab.load_data(result.data)
        self._refresh_running_state()

    def _analysis_finished(self, request_id: int, result: object) -> None:
        """Display only the newest result for the currently selected file."""
        if request_id != self._analysis_request_id:
            return

        if isinstance(result, dict) and result.get("error"):
            self._analysis_error(str(result["error"]))
            return
        if not isinstance(result, AnalysisResult):
            self._analysis_error("The analyzer returned an invalid result.")
            return
        if not self.file_path:
            return
        if Path(result.file.path) != Path(self.file_path):
            return

        self.analysis_result = result
        self.structure_tab.set_analysis_result(result)
        self.metadata_tab.set_analysis_result(result)
        if self.inspection_result is not None:
            self.structure_tab.set_inspection_status("Structure inspection is ready.")
            self.metadata_tab.set_inspection_status("Metadata inspection is ready.")
        self.bit_statistics_tab.set_analysis_result(result)
        self._bit_pending = False
        self._refresh_running_state()
        self.tabs.setCurrentWidget(self.bit_statistics_tab)
        self.analysis_completed.emit(result)

    def _analysis_error(self, message: str) -> None:
        """Reset the page after the current analysis fails."""
        self.analysis_result = None
        self._clear_analysis_results()
        self._bit_pending = False
        self._refresh_running_state()
        self.analysis_failed.emit(message)
        QMessageBox.warning(self, "Analysis Failed", message)
