from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QFrame, QMessageBox, QVBoxLayout

from src.core.stego.lsb_pp import LSBPP, get_max_message_bytes
from src.gui.components.widgets.execution_bar import ExecutionBar
from src.gui.components.widgets.key_validation import inspect_public_key
from src.gui.features.embed.forms.lsb_form import LSBInputForm, LSBInputsDraft
from src.gui.services.key_registry import KeyRegistry
from src.gui.services.worker import FunctionWorker


class LSBStandaloneTab(QFrame):
    """Compose the LSB input form and standalone execution controls."""

    def __init__(self, key_registry: KeyRegistry | None = None, parent=None):
        super().__init__(parent)
        self.key_registry = key_registry
        self.embed_worker = None
        self.last_embed_result: tuple[bytes, str] | None = None
        self.pending_embed_result = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.inputs = LSBInputForm(
            key_registry=self.key_registry,
            is_config=False,
        )
        self.execution_bar = ExecutionBar()

        layout.addWidget(self.inputs, 1)
        layout.addWidget(self.execution_bar, 0)
        self.execution_bar.execute_requested.connect(self.on_embed_execute)

    @staticmethod
    def encryption_args(draft: LSBInputsDraft) -> tuple[str | None, str | None]:
        if not draft.encryption_enabled:
            return None, None
        if draft.encryption_mode == "password":
            return draft.password, None
        if draft.encryption_mode == "public_key":
            return None, draft.public_key_path
        raise ValueError("Unsupported encryption mode.")

    def validate_embed_inputs(self, draft: LSBInputsDraft):
        if not isinstance(draft.cover, str) or self.inputs.cover_mode_toggle.mode() == "linked":
            raise ValueError("Select a manual cover image for standalone embedding.")
        if not Path(draft.cover).is_file():
            raise ValueError("The selected cover image no longer exists.")
        if self.inputs.isCalculating:
            raise ValueError("Wait for cover capacity calculation to finish.")
        if self.inputs.capacity_bits is None:
            raise ValueError("Could not calculate cover capacity. Select a valid cover image.")
        if not draft.payload_text:
            raise ValueError("Enter a payload message or load a text file.")

        password, public_key_path = self.encryption_args(draft)
        if draft.encryption_enabled:
            if draft.encryption_mode == "password":
                if not password:
                    raise ValueError("Enter a password.")
                if not self.inputs.passwords_match():
                    raise ValueError("Password and confirmation do not match.")
            else:
                if not public_key_path:
                    raise ValueError("Select a valid RSA public key.")
                result = inspect_public_key(public_key_path)
                if not result.valid:
                    raise ValueError(result.message)

        max_bytes = get_max_message_bytes(self.inputs.capacity_bits, password, public_key_path)
        if len(draft.payload_text.encode("utf-8")) > max_bytes:
            raise ValueError(f"Payload exceeds cover capacity ({max_bytes} bytes available).")

    def on_embed_execute(self):
        if self.embed_worker is not None:
            return
        draft = self.inputs.get_inputs()
        try:
            self.validate_embed_inputs(draft)
        except (OSError, TypeError, ValueError) as error:
            self.show_embed_error(str(error))
            return

        password, public_key_path = self.encryption_args(draft)
        worker = FunctionWorker(
            LSBPP().embed,
            cover_image_path=draft.cover,
            message=draft.payload_text,
            password=password,
            public_key_path=public_key_path,
            report_progress=True,
        )
        self.embed_worker = worker
        self.pending_embed_result = None
        worker.progress.connect(self.execution_bar.update_progress)
        worker.done.connect(self.on_embed_done)
        worker.finished.connect(self.release_embed_worker)
        self.execution_bar.reset()
        self.execution_bar.set_busy(True)
        self.inputs.setEnabled(False)
        worker.start()

    def on_embed_done(self, result):
        # Process dialogs after finished, so a modal dialog cannot interrupt
        # worker cleanup through its nested Qt event loop.
        self.pending_embed_result = result

    def release_embed_worker(self):
        worker = self.embed_worker
        self.embed_worker = None
        if worker is not None:
            worker.deleteLater()
        self.inputs.setEnabled(True)
        self.execution_bar.set_busy(False)
        result = self.pending_embed_result
        self.pending_embed_result = None
        if isinstance(result, dict) and "error" in result:
            self.show_embed_error(str(result["error"]))
        elif (
            isinstance(result, tuple) and len(result) == 2
            and isinstance(result[0], bytes) and isinstance(result[1], str)
        ):
            self.last_embed_result = result
            self.save_embed_result()
        else:
            self.show_embed_error("Embedding returned an invalid result.")

    def save_embed_result(self):
        """Save the latest result; retain its bytes on cancel or write failure."""
        if self.last_embed_result is None:
            return
        png_bytes, filename = self.last_embed_result
        output_path, _ = QFileDialog.getSaveFileName(self, "Save stego image", filename, "PNG image (*.png)")
        if not output_path:
            self.execution_bar.update_progress(100, "Embedding complete; not saved.")
            return
        path = Path(output_path)
        if path.suffix.lower() != ".png":
            path = path.with_suffix(".png")
            if path.exists() and QMessageBox.question(
                self, "Replace file?", f"{path.name} already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                self.execution_bar.update_progress(100, "Embedding complete; not saved.")
                return
        try:
            path.write_bytes(png_bytes)
        except OSError as error:
            self.show_embed_error(f"Embedding complete, but could not save PNG: {error}")
            return
        self.execution_bar.update_progress(100, f"Saved: {path}")

    def show_embed_error(self, message: str):
        self.execution_bar.status_label.setText(f"Status: {message}")
        QMessageBox.warning(self, "LSB++ embedding", message)
