import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image
from PyQt6.QtWidgets import QFileDialog, QFrame, QMessageBox, QVBoxLayout

from src.core.stego.locomotive import Locomotive
from src.gui.components.widgets.execution_bar import ExecutionBar
from src.gui.components.widgets.key_validation import inspect_public_key
from src.gui.features.embed.forms.locomotive_form import LocomotiveInputForm, LocomotiveInputsDraft
from src.gui.services.key_registry import KeyRegistry
from src.gui.services.worker import FunctionWorker

class LocomotiveStandaloneTab(QFrame):
    """Compose the Locomotive input form and standalone execution controls."""
    
    def __init__(self, key_registry: KeyRegistry | None = None, parent=None):
        super().__init__(parent)
        self.key_registry = key_registry
        self.embed_worker = None
        self.last_embed_result: list[tuple[str, bytes]] | None = None
        self.pending_embed_result = None
        self.setup_ui()
            
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.inputs = LocomotiveInputForm(
            key_registry=self.key_registry,
            is_config=False,
        )
        self.execution_bar = ExecutionBar("Embed Data")

        layout.addWidget(self.inputs, 1)
        layout.addWidget(self.execution_bar, 0)
        self.execution_bar.execute_requested.connect(self.on_embed_execute)

    @staticmethod
    def encryption_args(draft: LocomotiveInputsDraft) -> tuple[str | None, str | None]:
        if not draft.encryption_enabled:
            return None, None
        if draft.encryption_mode == "password":
            return draft.password, None
        if draft.encryption_mode == "public_key":
            return None, draft.public_key_path
        raise ValueError("Unsupported encryption mode.")

    def validate_embed_inputs(self, draft: LocomotiveInputsDraft):
        if not draft.covers or self.inputs.cover_mode_toggle.mode() == "linked":
            raise ValueError("Select at least one manual PNG cover image.")
        for cover in draft.covers:
            if not isinstance(cover.source, str):
                raise ValueError("Standalone embedding requires manual cover paths.")
            path = Path(cover.source)
            if not path.is_file() or path.suffix.lower() != ".png":
                raise ValueError(f"PNG cover is unavailable: {path.name}")
            with Image.open(path) as image:
                if image.format != "PNG":
                    raise ValueError(f"Cover is not a PNG image: {path.name}")
                image.verify()

        if draft.payload_mode == "files":
            if not draft.payload_files or self.inputs.payload_mode_toggle.mode() == "linked":
                raise ValueError("Select at least one manual payload file.")
            for source in draft.payload_files:
                if not isinstance(source, str) or not Path(source).is_file():
                    raise ValueError("A payload file is unavailable or is not a manual path.")
        elif draft.payload_mode == "text":
            if not draft.payload_text:
                raise ValueError("Enter a payload message.")
        else:
            raise ValueError("Unsupported payload mode.")

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
            Locomotive().embed,
            cover_image_paths=[cover.source for cover in draft.covers],
            file_paths=draft.payload_files if draft.payload_mode == "files" else None,
            raw_text=draft.payload_text if draft.payload_mode == "text" else None,
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
        elif isinstance(result, list) and result and all(
            isinstance(item, tuple) and len(item) == 2
            and isinstance(item[0], str) and item[0]
            and isinstance(item[1], bytes) for item in result
        ):
            self.last_embed_result = result
            self.save_embed_result()
        else:
            self.show_embed_error("Embedding returned an invalid result.")

    def save_embed_result(self):
        if not self.last_embed_result:
            return
        outputs = self.last_embed_result
        if len(outputs) == 1:
            filename, data = outputs[0]
            destination, _ = QFileDialog.getSaveFileName(
                self, "Save stego image", filename, "PNG image (*.png)"
            )
            if not destination:
                self.execution_bar.update_progress(100, "Embedding complete; not saved.")
                return
            path = Path(destination)
            changed_extension = path.suffix.lower() != ".png"
            if changed_extension:
                path = path.with_suffix(".png")
            targets = [(path, data)]
            existing = [path] if changed_extension and path.exists() else []
        else:
            directory = QFileDialog.getExistingDirectory(self, "Save Locomotive outputs")
            if not directory:
                self.execution_bar.update_progress(100, "Embedding complete; not saved.")
                return
            targets = []
            used_names = set()
            for filename, data in outputs:
                name = Path(filename).name
                candidate = name
                index = 2
                while candidate.casefold() in used_names:
                    candidate = f"{Path(name).stem}_{index}{Path(name).suffix}"
                    index += 1
                used_names.add(candidate.casefold())
                targets.append((Path(directory) / candidate, data))
            existing = [path for path, _ in targets if path.exists()]

        if existing and QMessageBox.question(
            self, "Replace files?", f"Replace {len(existing)} existing file(s)?\n"
            + "\n".join(str(path) for path in existing),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            self.execution_bar.update_progress(100, "Embedding complete; not saved.")
            return

        saved = 0
        for path, data in targets:
            try:
                self.write_output(path, data)
            except OSError as error:
                self.show_embed_error(f"Saved {saved}/{len(targets)} files; could not save {path.name}: {error}")
                return
            saved += 1
        self.execution_bar.update_progress(100, f"Saved {saved} file(s) to {targets[0][0].parent}")

    @staticmethod
    def write_output(path: Path, data: bytes):
        # Commit each complete file atomically; a failed write preserves the old file.
        temporary_path = None
        try:
            with NamedTemporaryFile(dir=path.parent, prefix=".loco-", suffix=".tmp", delete=False) as output:
                temporary_path = Path(output.name)
                output.write(data)
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def show_embed_error(self, message: str):
        self.execution_bar.status_label.setText(f"Status: {message}")
        QMessageBox.warning(self, "Locomotive embedding", message)
