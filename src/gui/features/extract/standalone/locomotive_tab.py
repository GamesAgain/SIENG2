from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QFrame, QMessageBox, QVBoxLayout

import zipfile

from src.core.stego.locomotive import Locomotive
from src.gui.components.widgets.execution_bar import ExecutionBar
from src.gui.features.extract.forms.locomotive_form import LocomotiveExtractForm
from src.gui.services.key_registry import KeyRegistry
from src.gui.services.worker import FunctionWorker


class LocomotiveStandaloneTab(QFrame):
    """Validate form inputs, extract in a worker, then display text or recovered files."""

    def __init__(self, key_registry: KeyRegistry | None = None, parent=None):
        super().__init__(parent)
        self.extract_worker = None
        self.pending_extract_result = None
        self.setup_ui(key_registry)

    def setup_ui(self, key_registry):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.inputs = LocomotiveExtractForm(key_registry)
        self.execution_bar = ExecutionBar("Extract Data")
        layout.addWidget(self.inputs, 1)
        layout.addWidget(self.execution_bar)
        self.execution_bar.execute_requested.connect(self.on_extract_execute)
        self.inputs.clear_button.clicked.connect(self.execution_bar.reset)
        self.inputs.stego_drop_zone.files_changed.connect(self.on_stego_files_changed)

    def on_stego_files_changed(self, _files):
        self.execution_bar.reset()

    def on_extract_execute(self):
        if self.extract_worker is not None:
            return
        inputs = self.inputs.get_inputs()
        try:
            self.inputs.validate_inputs(inputs)
        except (OSError, TypeError, ValueError) as error:
            self.show_extract_error(str(error))
            return

        self.inputs.clear_result()
        worker = FunctionWorker(
            Locomotive().extract,
            stego_image_paths=inputs.stego_file_paths,
            private_key_path=inputs.private_key_path,
            password=inputs.password,
            report_progress=True,
        )
        worker.setParent(self)
        self.extract_worker = worker
        self.pending_extract_result = None
        worker.progress.connect(self.execution_bar.update_progress)
        worker.done.connect(self.on_extract_done)
        worker.finished.connect(self.release_extract_worker)
        self.execution_bar.reset()
        self.execution_bar.set_busy(True)
        self.inputs.setEnabled(False)
        self.window().installEventFilter(self)
        worker.start()

    def on_extract_done(self, result):
        # Wait for finished before showing a modal error or enabling another run.
        self.pending_extract_result = result

    def release_extract_worker(self):
        worker = self.extract_worker
        self.extract_worker = None
        if worker is not None:
            worker.deleteLater()
        self.window().removeEventFilter(self)
        self.inputs.setEnabled(True)
        self.execution_bar.set_busy(False)
        result = self.pending_extract_result
        self.pending_extract_result = None
        if (isinstance(result, tuple) and len(result) == 2
                and isinstance(result[0], str) and isinstance(result[1], bytes)):
            try:
                self.inputs.show_result(result[0], result[1])
            except (OSError, ValueError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as error:
                self.inputs.clear_result()
                self.show_extract_error(str(error))
                return
            self.execution_bar.update_progress(100, "Extraction complete.")
        elif isinstance(result, dict) and "error" in result:
            self.show_extract_error(str(result["error"]))
        else:
            self.show_extract_error("Extraction returned an invalid result.")

    def show_extract_error(self, message: str):
        self.execution_bar.update_progress(0, message)
        QMessageBox.warning(self, "Locomotive Extraction", message)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Close and self.extract_worker is not None:
            event.ignore()
            self.execution_bar.set_status("Wait for extraction to finish before closing.")
            return True
        return super().eventFilter(watched, event)
