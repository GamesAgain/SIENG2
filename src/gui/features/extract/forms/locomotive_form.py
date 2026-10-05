from dataclasses import dataclass, field
import io
from pathlib import Path
import zipfile

from PyQt6.QtCore import QFileInfo, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFileIconProvider, QFrame, QHBoxLayout, QLabel, QLayout, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from src.gui.components.gui_utils import (
    add_password_visibility_toggle, add_shadow_effect, create_icon_pixmap,
    format_file_size, truncate_text_middle,
)
from src.gui.components.widgets.files_drop import MultiFileDropWidget
from src.gui.components.widgets.key_source import KeySourceWidget
from src.gui.components.widgets.key_validation import KeyValidationLabel, inspect_private_key
from src.gui.components.widgets.selection_toggle import SelectionToggle
from src.gui.components.widgets.toggle_switch import ToggleSwitch
from src.gui.components.widgets.visibility_stack import VisibilityStack
from src.gui.services.key_registry import KeyRegistry
from src.path import svg_path


ICON_SIZE = 16


@dataclass
class LocomotiveExtractInputs:
    stego_file_paths: list[str]
    private_key_path: str | None = None
    password: str | None = field(default=None, repr=False)


class LocomotiveExtractForm(QFrame):
    """Multiple stego PNGs, decryption controls and text/file result pages."""

    def __init__(self, key_registry: KeyRegistry | None = None, parent=None):
        super().__init__(parent)
        self.key_registry = key_registry
        self.result_filename = ""
        self.result_data: bytes | None = None
        self.result_files: list[tuple[str, bytes]] = []
        self.result_is_zip = False
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 11, 0, 0)

        sub_layout = QHBoxLayout()
        left_widget = QFrame()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        # Recalculate the scroll content minimum when file rows or modes change.
        left_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        left_layout.addWidget(self.build_stego_file_card(), 1)
        left_layout.addWidget(self.build_decryption_card(), 0)

        # Scroll when Private Key controls need more height than the window offers.
        left_scroll = QScrollArea()
        left_scroll.setObjectName("transparentScroll")
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setWidget(left_widget)

        sub_layout.addWidget(left_scroll, 1)
        sub_layout.addWidget(self.build_result_card(), 1)
        main_layout.addLayout(sub_layout)

    def build_stego_file_card(self):
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)

        title_container = QFrame()
        title_layout = QHBoxLayout(title_container)
        icon = QLabel()
        icon.setPixmap(create_icon_pixmap(svg_path("photo.svg"), size=ICON_SIZE))
        title = QLabel("Stego Files (PNGs)")
        title.setObjectName("cardTitle")
        title_layout.addWidget(icon)
        title_layout.addWidget(title)
        title_layout.addStretch()

        self.stego_drop_zone = MultiFileDropWidget(
            text="Drop stego PNG files here or click to browse",
            sub_text="Supports one or multiple PNG files",
            icon_path=str(svg_path("photo.svg")),
            allowed_extensions=[".png"],
        )
        # Protect the preview itself; selected file rows need extra space below it.
        self.stego_drop_zone.drop_zone.setMinimumHeight(115)
        self.stego_drop_zone.scroll_area.setMinimumHeight(180)
        self.stego_drop_zone.files_changed.connect(self.update_stego_list_height)
        self.stego_drop_zone.files_changed.connect(self.on_stego_files_changed)

        layout.addWidget(title_container)
        layout.addWidget(self.stego_drop_zone, 1)
        return card

    def update_stego_list_height(self, files: list[str]):
        scroll = self.stego_drop_zone.scroll_area
        if len(files) == 1:
            # One row leaves the remaining space available to the image preview.
            height = self.stego_drop_zone.list_container.minimumSizeHint().height()
            scroll.setFixedHeight(height + 2 * scroll.frameWidth())
        else:
            # Restore the scrollable list when there are multiple files.
            scroll.setMaximumHeight(16777215)
            scroll.setMinimumHeight(180)

    def build_decryption_card(self):
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(11, 11, 11, 2)
        layout.setSpacing(6)

        title_container = QFrame()
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)
        self.decrypt_toggle_switch = ToggleSwitch()
        self.decrypt_toggle_switch.setChecked(True)
        icon = QLabel()
        icon.setPixmap(create_icon_pixmap(svg_path("shield-lock.svg"), "#a78bfa", ICON_SIZE))
        title = QLabel("Decryption Options")
        title.setObjectName("cardTitle")
        title_layout.addWidget(self.decrypt_toggle_switch)
        title_layout.addWidget(icon)
        title_layout.addWidget(title)
        title_layout.addStretch()
        title_layout.addWidget(self.build_decrypt_selection())

        self.decrypt_stack = VisibilityStack()
        self.decrypt_stack.addWidget(self.build_symmetric_mode())
        self.decrypt_stack.addWidget(self.build_asymmetric_mode())

        self.decrypt_mode_toggle.mode_changed.connect(self.on_decrypt_mode_changed)
        self.decrypt_toggle_switch.toggled.connect(self.decrypt_stack.setVisible)
        layout.addWidget(title_container)
        layout.addWidget(self.decrypt_stack)
        return card

    def build_decrypt_selection(self):
        self.decrypt_mode_toggle = SelectionToggle([
            {
                "text": "Password", "value": "password", "variant": "password",
                "color_checked": "#a78bfa", "icon_path": svg_path("key.svg"),
                "icon_size": 14,
            },
            {
                "text": "Private Key", "value": "private_key", "variant": "public_key",
                "color_checked": "#34D399", "icon_path": svg_path("lock.svg"),
                "icon_size": 14,
            },
        ])
        # Reuse the compact encryption selector styling for decryption too.
        self.decrypt_mode_toggle.setProperty("variant", "encryption")
        return self.decrypt_mode_toggle

    def build_symmetric_mode(self):
        page = QFrame()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 8)
        label = QLabel("Password")
        label.setObjectName("formLabel")
        self.password_input = QLineEdit()
        self.password_input.setObjectName("formInput")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter passphrase...")
        add_password_visibility_toggle(self.password_input)
        layout.addWidget(label)
        layout.addWidget(self.password_input)
        return page

    def build_asymmetric_mode(self):
        page = QFrame()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 8)
        # KeySourceWidget opens its picker with verify_form=False already.
        self.private_key_source = KeySourceWidget("private", self.key_registry)
        # Let the wrapper include both the preview and the selected file row.
        self.private_key_source.drop_zone.setMinimumHeight(0)
        self.private_key_source.drop_zone.drop_zone.setMinimumHeight(115)
        layout.addWidget(self.private_key_source)

        label = QLabel("Private Key Password (Optional)")
        label.setObjectName("formLabel")
        self.key_password_input = QLineEdit()
        self.key_password_input.setObjectName("formInput")
        self.key_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_password_input.setPlaceholderText("Enter key password...")
        add_password_visibility_toggle(self.key_password_input)
        layout.addWidget(label)
        layout.addWidget(self.key_password_input)
        self.private_key_status = KeyValidationLabel()
        layout.addWidget(self.private_key_status)

        self.private_key_source.key_selected.connect(self.validate_private_key)
        self.key_password_input.editingFinished.connect(self.validate_private_key)
        return page

    def build_result_card(self):
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        title_container = QFrame()
        title_layout = QHBoxLayout(title_container)
        icon = QLabel()
        icon.setPixmap(create_icon_pixmap(svg_path("file-search.svg"), size=ICON_SIZE))
        title = QLabel("Extraction Result")
        title.setObjectName("cardTitle")
        title_layout.addWidget(icon)
        title_layout.addWidget(title)
        title_layout.addStretch()

        # Extraction selects Text or Files according to the recovered payload.
        self.result_tabs = QTabWidget()
        self.result_tabs.setObjectName("siengTabs")
        self.result_tabs.addTab(self.build_text_result_page(), "Text")
        self.result_tabs.addTab(self.build_files_result_page(), "Files")
        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("DangerBtn")
        self.clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_button.setEnabled(False)
        actions = QHBoxLayout()
        actions.addWidget(self.clear_button)
        actions.addStretch()
        self.clear_button.clicked.connect(self.clear_result)
        layout.addWidget(title_container)
        layout.addWidget(self.result_tabs, 1)
        layout.addLayout(actions)
        return card

    def build_text_result_page(self):
        page = QFrame()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        self.result_text_area = QPlainTextEdit()
        self.result_text_area.setObjectName("payloadTextArea")
        self.result_text_area.setReadOnly(True)
        self.result_text_area.setPlaceholderText("Extracted message will appear here...")
        self.copy_button = QPushButton("Copy")
        self.copy_button.setObjectName("SecondaryBtn")
        self.export_button = QPushButton("Export .txt")
        self.export_button.setObjectName("SecondaryBtn")
        actions = QHBoxLayout()
        actions.addStretch()
        for button in (self.copy_button, self.export_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setEnabled(False)
            actions.addWidget(button)
        self.copy_button.clicked.connect(self.copy_result)
        self.export_button.clicked.connect(self.export_result)
        layout.addWidget(self.result_text_area, 1)
        layout.addLayout(actions)
        return page

    def build_files_result_page(self):
        page = QFrame()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        # Reuse the StepCard canvas background/border without changing shared QSS.
        self.result_files_canvas = QFrame()
        self.result_files_canvas.setObjectName("pipelineCanvas")
        canvas_layout = QVBoxLayout(self.result_files_canvas)
        canvas_layout.setContentsMargins(8, 8, 8, 8)
        self.result_files_scroll = QScrollArea()
        self.result_files_scroll.setObjectName("transparentScroll")
        self.result_files_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.result_files_scroll.setWidgetResizable(True)
        self.result_files_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.result_files_container = QWidget()
        self.result_files_container.setObjectName("transparentScrollContent")
        self.result_files_layout = QVBoxLayout(self.result_files_container)
        self.result_files_layout.setContentsMargins(0, 0, 0, 0)
        self.result_files_layout.setSpacing(8)
        self.result_files_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.files_empty_label = QLabel("Extracted files will appear here...")
        self.files_empty_label.setObjectName("hintLabel")
        self.files_empty_label.setWordWrap(True)
        self.result_files_layout.addWidget(self.files_empty_label)
        self.result_files_scroll.setWidget(self.result_files_container)
        canvas_layout.addWidget(self.result_files_scroll)
        self.save_files_button = QPushButton("Save All...")
        self.save_files_button.setObjectName("SecondaryBtn")
        self.save_files_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_files_button.setEnabled(False)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.save_files_button)
        self.save_files_button.clicked.connect(self.save_files_result)
        layout.addWidget(self.result_files_canvas, 1)
        layout.addLayout(actions)
        return page

    def build_result_file_row(self, filename: str, data: bytes):
        """Build a read-only preview row for a recovered file."""
        row = QFrame()
        row.setObjectName("fileItemRow")
        row.setFixedHeight(64)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        icon = QLabel()
        icon.setFixedSize(40, 40)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview = QPixmap()
        if preview.loadFromData(data):
            icon.setPixmap(preview.scaled(
                40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            icon.setPixmap(QFileIconProvider().icon(QFileInfo(filename)).pixmap(32, 32))
        name = QLabel(truncate_text_middle(filename, max_length=40))
        name.setObjectName("fileItemName")
        name.setToolTip(filename)
        size = QLabel(format_file_size(len(data)))
        size.setObjectName("fileItemSize")
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.addWidget(name)
        text_layout.addWidget(size)
        layout.addWidget(icon)
        layout.addLayout(text_layout, 1)
        return row

    def on_decrypt_mode_changed(self, mode: str):
        self.decrypt_stack.setCurrentIndex(0 if mode == "password" else 1)

    def get_inputs(self) -> LocomotiveExtractInputs:
        inputs = LocomotiveExtractInputs(stego_file_paths=list(self.stego_drop_zone.selected_files))
        # Ignore values left in inactive decryption fields.
        if self.decrypt_toggle_switch.isChecked():
            if self.decrypt_mode_toggle.mode() == "password":
                inputs.password = self.password_input.text()
            else:
                inputs.private_key_path = self.private_key_source.drop_zone.file_path or None
                inputs.password = self.key_password_input.text() or None
        return inputs

    def validate_inputs(self, inputs: LocomotiveExtractInputs):
        if not inputs.stego_file_paths:
            raise ValueError("Select at least one stego PNG file.")
        for filename in inputs.stego_file_paths:
            path = Path(filename)
            if not path.is_file():
                raise ValueError(f"Stego file no longer exists: {path.name}")
            with path.open("rb") as file:
                if path.suffix.lower() != ".png" or file.read(8) != b"\x89PNG\r\n\x1a\n":
                    raise ValueError(f"Not a valid PNG file: {path.name}")
        if not self.decrypt_toggle_switch.isChecked():
            return
        if self.decrypt_mode_toggle.mode() == "password":
            if not inputs.password:
                raise ValueError("Enter a password.")
        else:
            if not inputs.private_key_path:
                raise ValueError("Select an RSA private key.")
            result = inspect_private_key(inputs.private_key_path, inputs.password)
            self.private_key_status.set_result(result)
            if not result.valid:
                raise ValueError(result.message)

    def validate_private_key(self, _file_path=None):
        path = self.private_key_source.drop_zone.file_path
        if not path:
            self.private_key_status.clear_result()
            return
        result = inspect_private_key(path, self.key_password_input.text() or None)
        self.private_key_status.set_result(result)

    def on_stego_files_changed(self, _files: list[str]):
        self.clear_result()

    def clear_result(self):
        self.result_filename = ""
        self.result_data = None
        self.result_files = []
        self.result_is_zip = False
        self.result_text_area.clear()
        # Keep the empty-state label; remove only the old file rows.
        while self.result_files_layout.count() > 1:
            row = self.result_files_layout.takeAt(1).widget()
            if row is not None:
                row.hide()
                row.deleteLater()
        self.files_empty_label.show()
        self.result_tabs.setCurrentIndex(0)
        for button in (self.clear_button, self.copy_button, self.export_button, self.save_files_button):
            button.setEnabled(False)
        self.save_files_button.setText("Save As...")

    def show_result(self, filename: str, data: bytes):
        self.clear_result()
        # Core uses this reserved name for raw text; ordinary .txt files stay files.
        if filename == "secret_message.txt":
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = None
            if text is not None:
                self.result_text_area.setPlainText(text)
                self.clear_button.setEnabled(True)
                self.copy_button.setEnabled(bool(text))
                self.export_button.setEnabled(bool(text))
                return

        files = [(filename, data)]
        # Only the system-generated ZIP name is expanded for the list preview.
        if filename == "secret_files.zip" and zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                files = [(item.filename, archive.read(item))
                         for item in archive.infolist() if not item.is_dir()]
            self.result_is_zip = True
        self.result_filename = filename
        self.result_data = data
        self.result_files = files
        self.files_empty_label.setVisible(not files)
        for name, content in files:
            self.result_files_layout.addWidget(self.build_result_file_row(name, content))
        self.save_files_button.setText("Save ZIP..." if self.result_is_zip else "Save As...")
        self.save_files_button.setEnabled(True)
        self.clear_button.setEnabled(True)
        self.result_tabs.setCurrentIndex(1)

    def copy_result(self):
        QApplication.clipboard().setText(self.result_text_area.toPlainText())

    def export_result(self):
        text = self.result_text_area.toPlainText()
        if not text:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export extracted text", "extracted.txt", "Text files (*.txt)",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".txt":
            path = path.with_suffix(".txt")
            # The file dialog only checked the original name for replacement.
            if path.exists() and QMessageBox.question(
                self, "Replace file?", f"{path.name} already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
        try:
            path.write_text(text, encoding="utf-8", newline="")
        except OSError as error:
            QMessageBox.warning(self, "Export Text", str(error))

    def save_files_result(self):
        if self.result_data is None:
            return
        # Save the original payload bytes, including the original ZIP package.
        name = Path(self.result_filename).name
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save extracted file", name,
            "ZIP files (*.zip)" if self.result_is_zip else "All files (*)",
        )
        if not filename:
            return
        path = Path(filename)
        if self.result_is_zip and path.suffix.lower() != ".zip":
            path = path.with_suffix(".zip")
            if path.exists() and QMessageBox.question(
                self, "Replace file?", f"{path.name} already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
        try:
            path.write_bytes(self.result_data)
        except OSError as error:
            QMessageBox.warning(self, "Save Extracted File", str(error))
