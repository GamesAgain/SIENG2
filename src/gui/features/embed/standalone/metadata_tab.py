from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QFrame, QMessageBox, QVBoxLayout

from src.core.stego.metadata_handlers.png_handler import MetadataPNGHandler
from src.gui.components.widgets.execution_bar import ExecutionBar
from src.gui.features.embed.forms.metadata_form import MetadataInputForm
from src.gui.services.worker import FunctionWorker


class MetadataStandaloneTab(QFrame):
    """Edit the text metadata of a PNG and save it as a new file (the original is never changed)."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.save_worker = None
        self.save_result = None
        self.save_path = None

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.inputs_form = MetadataInputForm()
        self.execution_bar = ExecutionBar("Save Metadata")
        self.execution_bar.hide()  # แสดงเมื่อเลือกไฟล์แล้ว

        layout.addWidget(self.inputs_form, 1)
        layout.addWidget(self.execution_bar)

        self.execution_bar.execute_requested.connect(self.on_save_execute)
        self.inputs_form.target_file_changed.connect(self.on_target_file_changed)

    # --- Helpers ---

    def show_save_error(self, message: str):
        self.execution_bar.set_error("Not saved.")
        QMessageBox.warning(self, "Metadata", message)

    def show_save_success(self, path: Path, secret_keys: list[str]):
        """Tell the user which fields the receiver will see (the added/modified ones)."""
        if secret_keys:
            fields = "\n".join(f"• {key}" for key in secret_keys)
            message = f"Saved to:\n{path}\n\nThe receiver will see these fields:\n{fields}"
        else:
            message = (f"Saved to:\n{path}\n\n"
                       "No fields were added or modified, so the receiver will see nothing.")
        QMessageBox.information(self, "Metadata saved", message)

    def ask_save_path(self, source: Path) -> Path | None:
        """Save As dialog with '<name>_metadata.png'. None = the user cancelled."""
        default_path = source.with_name(f"{source.stem}_metadata.png")
        output_path, _ = QFileDialog.getSaveFileName(self, "Save PNG with metadata", str(default_path), "PNG image (*.png)")
        if not output_path:
            return None

        path = Path(output_path)
        if path.suffix.lower() != ".png":
            # เติม .png เอง -> dialog ไม่ได้ถามเรื่องทับไฟล์ชื่อนี้ จึงต้องถามเอง
            path = path.with_suffix(".png")
            if path.exists() and QMessageBox.question(
                self, "Replace file?", f"{path.name} already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return None
        return path

    # --- Actions ---

    def on_target_file_changed(self, file_path: str):
        self.execution_bar.setVisible(bool(file_path))
        self.execution_bar.reset()

    def on_save_execute(self):
        if self.save_worker is not None:
            return

        try:
            entries = self.inputs_form.get_entries()
        except ValueError as error:
            self.show_save_error(str(error))
            return

        source = Path(self.inputs_form.target_file_path)
        path = self.ask_save_path(source)
        if path is None:
            self.execution_bar.update_progress(0, "Not saved.")
            return
        if path.resolve() == source.resolve():
            self.show_save_error("Choose a different file name. The original file is kept unchanged.")
            return

        worker = FunctionWorker(MetadataPNGHandler().write_text, str(source), str(path), entries)

        self.save_worker = worker
        self.save_result = None
        self.save_path = path

        # set worker connection
        worker.done.connect(self.on_save_done)
        worker.finished.connect(self.release_save_worker)

        # set up UI to saving state
        self.execution_bar.reset()
        self.execution_bar.set_busy(True)
        self.execution_bar.set_status("Saving...")
        self.inputs_form.setEnabled(False)

        worker.start()

    # --- Worker Callbacks ---

    def on_save_done(self, result):
        self.save_result = result

    def release_save_worker(self):
        result = self.save_result
        path = self.save_path

        if self.save_worker is not None:
            self.save_worker.deleteLater()

        self.save_worker = None
        self.save_result = None
        self.save_path = None

        # restore UI state
        self.inputs_form.setEnabled(True)
        self.execution_bar.set_busy(False)

        if isinstance(result, dict) and "error" in result:
            self.show_save_error(result["error"])
            return

        if isinstance(result, list):
            # editor ยังอยู่กับไฟล์ต้นฉบับ: Save อีกรอบก็เทียบกับต้นฉบับเหมือนเดิม
            self.execution_bar.update_progress(100, f"Saved: {path}")
            self.show_save_success(path, result)
            return

        self.show_save_error("Saving returned an invalid result.")
