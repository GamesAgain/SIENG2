from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QFrame, QMessageBox, QVBoxLayout

from src.gui.components.widgets.execution_bar import ExecutionBar
from src.gui.features.embed.forms.metadata_form import MetadataInputForm
from src.gui.services.metadata_png_execution import save_png_metadata
from src.gui.services.metadata_mp3_execution import save_mp3_metadata
from src.gui.services.worker import FunctionWorker


class MetadataStandaloneTab(QFrame):
    """Metadata forms and standalone PNG/MP3 save execution."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.save_worker = None
        self.pending_save_result = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.inputs = MetadataInputForm(is_config=False)
        layout.addWidget(self.inputs, 1)
        self.execution_bar = ExecutionBar("Save Metadata")
        self.execution_bar.hide()
        layout.addWidget(self.execution_bar)
        self.inputs.target_file_changed.connect(self.on_target_file_changed)
        self.execution_bar.execute_requested.connect(self.on_save_execute)

    def on_target_file_changed(self, file_path: str) -> None:
        self.execution_bar.setVisible(Path(file_path).suffix.lower() in {".png", ".mp3"})
        self.execution_bar.reset()

    def on_save_execute(self) -> None:
        if self.save_worker is not None:
            return
        source = self.inputs.target_file_path
        try:
            if not source or Path(source).suffix.lower() not in {".png", ".mp3"} or not Path(source).is_file():
                raise ValueError("Select an existing PNG or MP3 file first.")
            extension = Path(source).suffix.lower()
            if extension == ".png":
                payload = self.inputs.png_form.get_inputs().entries
                save_function = save_png_metadata
            else:
                payload = self.inputs.mp3_form.get_inputs()
                save_function = save_mp3_metadata
        except (OSError, ValueError) as error:
            self.show_save_error(str(error))
            return

        path = Path(source)
        destination, _ = QFileDialog.getSaveFileName(
            self, f"Save {extension[1:].upper()} Metadata",
            str(path.with_name(f"{path.stem}_metadata{extension}")),
            "PNG image (*.png)" if extension == ".png" else "MP3 audio (*.mp3)",
        )
        if not destination:
            return
        target = Path(destination)
        if target.suffix.lower() != extension:
            target = target.with_suffix(extension)
            if target.exists() and QMessageBox.question(
                self, "Replace file?", f"{target.name} already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return

        worker = FunctionWorker(save_function, source, str(target), payload, report_progress=True)
        self.save_worker = worker
        self.pending_save_result = None
        worker.progress.connect(self.execution_bar.update_progress)
        worker.done.connect(self.on_save_done)
        worker.finished.connect(self.release_save_worker)
        self.execution_bar.reset()
        self.execution_bar.set_busy(True)
        self.inputs.setEnabled(False)
        worker.start()

    def on_save_done(self, result) -> None:
        self.pending_save_result = result

    def release_save_worker(self) -> None:
        worker = self.save_worker
        self.save_worker = None
        if worker is not None:
            worker.deleteLater()
        self.inputs.setEnabled(True)
        self.execution_bar.set_busy(False)
        result = self.pending_save_result
        self.pending_save_result = None
        if isinstance(result, dict) and "error" in result:
            self.show_save_error(str(result["error"]))
        elif isinstance(result, str) and Path(result).is_file():
            self.inputs.cover_drop_zone.clear_file()
            self.inputs.cover_drop_zone.process_file(result)
            if self.inputs.target_file_path == result:
                self.execution_bar.update_progress(100, f"Saved and verified: {result}")
        else:
            self.show_save_error("Saving returned an invalid result.")

    def show_save_error(self, message: str) -> None:
        self.execution_bar.set_status(message)
        QMessageBox.warning(self, "Metadata", message)
