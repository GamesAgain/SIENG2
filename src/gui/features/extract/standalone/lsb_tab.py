from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QFrame, QMessageBox, QVBoxLayout

from src.core.stego.lsb_pp import LSBPP
from src.gui.components.widgets.execution_bar import ExecutionBar
from src.gui.features.extract.forms.lsb_form import LSBExtractForm
from src.gui.services.key_registry import KeyRegistry
from src.gui.services.worker import FunctionWorker


class LSBStandaloneTab(QFrame):
    """Validate form inputs, extract in a worker, then display the text result."""

    def __init__(self, key_registry: KeyRegistry | None = None, parent=None):
        super().__init__(parent)
        self.extract_worker = None
        self.pending_extract_result = None
        self.setup_ui(key_registry)

    def setup_ui(self, key_registry):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.inputs = LSBExtractForm(key_registry)
        self.execution_bar = ExecutionBar("Extract Data")
        layout.addWidget(self.inputs, 1)
        layout.addWidget(self.execution_bar)
        self.execution_bar.execute_requested.connect(self.on_extract_execute)
        self.inputs.clear_button.clicked.connect(self.execution_bar.reset)
        self.inputs.stego_drop_zone.file_selected.connect(self.on_stego_file_selected)

    def on_stego_file_selected(self, _file_path):
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
            LSBPP().extract,
            stego_image_path=inputs.stego_file_path,
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
        if isinstance(result, str):
            self.inputs.show_result(result)
            self.execution_bar.update_progress(100, "Extraction complete.")
        elif isinstance(result, dict) and "error" in result:
            self.show_extract_error(str(result["error"]))
        else:
            self.show_extract_error("Extraction returned an invalid result.")

    def show_extract_error(self, message: str):
        self.execution_bar.update_progress(0, message)
        QMessageBox.warning(self, "LSB++ Extraction", message)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Close and self.extract_worker is not None:
            event.ignore()
            self.execution_bar.set_status("Wait for extraction to finish before closing.")
            return True
        return super().eventFilter(watched, event)
