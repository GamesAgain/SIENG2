from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QFrame, QMessageBox, QVBoxLayout

from src.gui.components.widgets.execution_bar import ExecutionBar
from src.gui.features.embed.forms.lsb_form import LSBInputForm
from src.gui.services.key_registry import KeyRegistry
from src.core.stego.lsb_pp import LSBPP
from src.gui.services.worker import FunctionWorker

class LSBStandaloneTab(QFrame):

    def __init__(self, key_registry: KeyRegistry | None = None, parent=None):
        super().__init__(parent)

        self.key_registry = key_registry
        self.embed_worker = None
        self.embed_result = None

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.inputs_form = LSBInputForm(
            key_registry=self.key_registry,
            is_config=False,
        )
        self.execution_bar = ExecutionBar("Embed Data")

        layout.addWidget(self.inputs_form, 1)
        layout.addWidget(self.execution_bar)

        self.execution_bar.execute_requested.connect(self.on_embed_execute)
        self.inputs_form.draft_status.connect(self.on_draft_status_changed)
        self.inputs_form.update_draft_status()
    
    # --- Helpers ---

    def show_embed_error(self, message: str):
        self.execution_bar.set_error()
        QMessageBox.warning(self, "LSB++ embedding", message)

    def save_embed_result(self):
        if self.embed_result is None:
            return

        filename, png_bytes = self.embed_result
        self.embed_result = None  # clear memory

        output_path, _ = QFileDialog.getSaveFileName(self, "Save stego image", filename, "PNG image (*.png)")

        if not output_path:
            self.execution_bar.update_progress(100, "Embedding complete; not saved.")
            return

        path = Path(output_path)

        if path.suffix.lower() != ".png":
            path = path.with_suffix(".png")

        try:
            path.write_bytes(png_bytes)
        except OSError as error:
            self.show_embed_error(
                f"Embedding complete, but could not save PNG: {error}"
            )
            return

        self.execution_bar.update_progress(100, f"Saved: {path}")

    # --- Actions ---

    def on_embed_execute(self):
        if self.embed_worker is not None:
            return

        try:
            draft = self.inputs_form.get_inputs()
        except ValueError as error:
            self.show_embed_error(str(error))
            return

        password, public_key_path = draft.encryption_args()

        worker = FunctionWorker(
            LSBPP().embed,
            cover_image_path=draft.cover,
            message=draft.payload_text,
            public_key_path=public_key_path,
            password=password,
            report_progress=True,
        )

        self.embed_worker = worker
        self.embed_result = None
        
        # set worker connection
        worker.progress.connect(self.execution_bar.update_progress)
        worker.done.connect(self.on_embed_done)
        worker.finished.connect(self.release_embed_worker)
        
        # set up UI to embedding state
        self.execution_bar.reset()
        self.execution_bar.set_busy(True)
        self.execution_bar.set_status("Embedding...")
        self.inputs_form.setEnabled(False)

        worker.start()

    def on_draft_status_changed(self, ready: bool):
        if self.embed_worker is not None:
            return

        if ready:
            self.execution_bar.update_progress(0, "Ready")
        else:
            self.execution_bar.update_progress(0, "Waiting for inputs...")

    # --- Worker Callbacks ---

    def on_embed_done(self, result):
        self.embed_result = result

    def release_embed_worker(self):
        result = self.embed_result

        if self.embed_worker is not None:
            self.embed_worker.deleteLater()

        self.embed_worker = None

        # restore UI state
        self.inputs_form.setEnabled(True)
        self.execution_bar.set_busy(False)

        if isinstance(result, dict) and "error" in result:
            self.show_embed_error(result["error"])
            return

        if isinstance(result, tuple) and len(result) == 2:
            self.save_embed_result()
            return

        self.show_embed_error("Embedding returned an invalid result.")