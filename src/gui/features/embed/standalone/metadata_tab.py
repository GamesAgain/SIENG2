from pathlib import Path

from mutagen import MutagenError
from PyQt6.QtWidgets import QFileDialog, QFrame, QMessageBox, QVBoxLayout

from src.core.stego.metadata_handlers.mp3_handler import MetadataMP3Handler
from src.core.stego.metadata_handlers.png_handler import MetadataPNGHandler
from src.gui.components.widgets.execution_bar import ExecutionBar
from src.gui.features.embed.forms.metadata_form import MetadataInputForm
from src.gui.services.worker import FunctionWorker

FILE_FILTERS = {".png": "PNG image (*.png)", ".mp3": "MP3 audio (*.mp3)"}


class MetadataStandaloneTab(QFrame):
    """Edit the metadata of a PNG / MP3 and save it as a new file (the original is never changed)."""

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
            fields = "\n".join(f"• {name}" for name in self.inputs_form.key_labels(secret_keys))
            message = f"Saved to:\n{path}\n\nThe receiver will see these fields:\n{fields}"
        else:
            message = (f"Saved to:\n{path}\n\n"
                       "No fields were added or modified, so the receiver will see nothing.")
        QMessageBox.information(self, "Metadata saved", message)

    def confirm_drop_unsupported(self, frames: list[str]) -> bool:
        """MP3 frames ID3v2.3 cannot keep are not in the editor, so ask before removing them."""
        names = "\n".join(f"• {name}" for name in frames)
        answer = QMessageBox.question(
            self, "Remove unsupported frames?",
            f"This MP3 has frames that cannot be saved as ID3v2.3:\n{names}\n\n"
            "They are not shown in the editor. Remove them and save?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def ask_save_path(self, source: Path) -> Path | None:
        """Save As dialog with '<name>_metadata.<ext>'. None = the user cancelled."""
        suffix = source.suffix.lower()
        default_path = source.with_name(f"{source.stem}_metadata{suffix}")
        output_path, _ = QFileDialog.getSaveFileName(
            self, f"Save {suffix[1:].upper()} with metadata", str(default_path), FILE_FILTERS[suffix])
        if not output_path:
            return None

        path = Path(output_path)
        if path.suffix.lower() != suffix:
            # เติมนามสกุลเอง -> dialog ไม่ได้ถามเรื่องทับไฟล์ชื่อนี้ จึงต้องถามเอง
            path = path.with_suffix(suffix)
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
        drop_unsupported = False
        if source.suffix.lower() == ".mp3":
            try:
                unsupported = MetadataMP3Handler().read_unsupported(str(source))
            except (OSError, ValueError, MutagenError) as error:
                self.show_save_error(str(error))
                return
            if unsupported:
                if not self.confirm_drop_unsupported(unsupported):
                    self.execution_bar.update_progress(0, "Not saved.")
                    return
                drop_unsupported = True

        path = self.ask_save_path(source)
        if path is None:
            self.execution_bar.update_progress(0, "Not saved.")
            return
        if path.resolve() == source.resolve():
            self.show_save_error("Choose a different file name. The original file is kept unchanged.")
            return

        if source.suffix.lower() == ".mp3":
            worker = FunctionWorker(MetadataMP3Handler().write_frames, str(source), str(path), entries, drop_unsupported)
        else:
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
