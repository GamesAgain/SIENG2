from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QFrame, QMessageBox, QVBoxLayout

from src.core.stego.locomotive import Locomotive
from src.gui.components.widgets.execution_bar import ExecutionBar
from src.gui.features.embed.forms.locomotive_form import LocomotiveInputForm
from src.gui.services.key_registry import KeyRegistry
from src.gui.services.worker import FunctionWorker

class LocomotiveStandaloneTab(QFrame):
    """Compose the Locomotive input form and standalone execution controls."""

    def __init__(self, key_registry: KeyRegistry | None = None, parent=None):
        super().__init__(parent)

        self.key_registry = key_registry
        self.embed_worker = None
        self.embed_result = None

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.inputs_form = LocomotiveInputForm(
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
        QMessageBox.warning(self, "Locomotive embedding", message)

    def save_embed_result(self):
        if not self.embed_result:
            return

        outputs = self.embed_result  # list[(filename, png_bytes)]
        self.embed_result = None  # clear memory

        if len(outputs) == 1:
            # One output: the OS save dialog already asks before replacing a file.
            filename, png_bytes = outputs[0]
            output_path, _ = QFileDialog.getSaveFileName(self, "Save stego image", filename, "PNG image (*.png)")

            if not output_path:
                self.execution_bar.update_progress(100, "Embedding complete; not saved.")
                return

            path = Path(output_path)

            if path.suffix.lower() != ".png":
                path = path.with_suffix(".png")

            targets = [(path, png_bytes)]
        else:
            # Several outputs: the folder dialog does not ask about existing files, so ask here.
            directory = QFileDialog.getExistingDirectory(self, "Save Locomotive outputs")

            if not directory:
                self.execution_bar.update_progress(100, "Embedding complete; not saved.")
                return

            targets = [(Path(directory) / Path(name).name, png_bytes) for name, png_bytes in outputs]
            existing = [path for path, _ in targets if path.exists()]

            if existing and QMessageBox.question(
                self, "Replace files?",
                f"Replace {len(existing)} existing file(s)?\n" + "\n".join(str(path) for path in existing),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                self.execution_bar.update_progress(100, "Embedding complete; not saved.")
                return

        saved = 0
        for path, png_bytes in targets:
            try:
                path.write_bytes(png_bytes)
            except OSError as error:
                self.show_embed_error(
                    f"Embedding complete, but saved {saved}/{len(targets)} file(s); could not save {path.name}: {error}"
                )
                return
            saved += 1

        if saved == 1:
            self.execution_bar.update_progress(100, f"Saved: {targets[0][0]}")
        else:
            self.execution_bar.update_progress(100, f"Saved {saved} files to {targets[0][0].parent}")

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
            Locomotive().embed,
            cover_image_paths=draft.covers,
            file_paths=draft.payload_files if draft.payload_mode == "files" else None,
            raw_text=draft.payload_text if draft.payload_mode == "text" else None,
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
            self.embed_result = None
            self.show_embed_error(result["error"])
            return

        if isinstance(result, list) and result:
            self.save_embed_result()
            return

        self.embed_result = None
        self.show_embed_error("Embedding returned an invalid result.")
