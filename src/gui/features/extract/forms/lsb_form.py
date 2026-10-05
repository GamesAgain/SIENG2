from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLayout, QLineEdit,
    QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QVBoxLayout,
)

from src.gui.components.gui_utils import (
    add_password_visibility_toggle, add_shadow_effect, create_icon_pixmap,
)
from src.gui.components.widgets.files_drop import FileDropWidget
from src.gui.components.widgets.key_source import KeySourceWidget
from src.gui.components.widgets.key_validation import KeyValidationLabel, inspect_private_key
from src.gui.components.widgets.selection_toggle import SelectionToggle
from src.gui.components.widgets.toggle_switch import ToggleSwitch
from src.gui.components.widgets.visibility_stack import VisibilityStack
from src.gui.services.key_registry import KeyRegistry
from src.path import svg_path


ICON_SIZE = 16


@dataclass
class LSBExtractInputs:
    stego_file_path: str
    private_key_path: str | None = None
    password: str | None = field(default=None, repr=False)


class LSBExtractForm(QFrame):
    """Stego/decryption inputs on the left and read-only results on the right."""

    def __init__(self, key_registry: KeyRegistry | None = None, parent=None):
        super().__init__(parent)
        self.key_registry = key_registry
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
        title = QLabel("Stego File (PNG)")
        title.setObjectName("cardTitle")
        title_layout.addWidget(icon)
        title_layout.addWidget(title)
        title_layout.addStretch()

        self.stego_drop_zone = FileDropWidget(
            text="Drop stego PNG file here or click to browse",
            sub_text="Supported: PNG",
            icon_path=str(svg_path("photo.svg")),
            allowed_extensions=[".png"],
        )
        # Protect the preview itself; selected file rows need extra space below it.
        self.stego_drop_zone.drop_zone.setMinimumHeight(180)
        self.stego_drop_zone.file_selected.connect(self.on_stego_file_selected)

        layout.addWidget(title_container)
        layout.addWidget(self.stego_drop_zone, 1)
        return card

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
        icon.setPixmap(create_icon_pixmap(svg_path("message.svg"), size=ICON_SIZE))
        title = QLabel("Extraction Result")
        title.setObjectName("cardTitle")
        title_layout.addWidget(icon)
        title_layout.addWidget(title)
        title_layout.addStretch()

        self.result_text_area = QPlainTextEdit()
        self.result_text_area.setObjectName("payloadTextArea")
        self.result_text_area.setReadOnly(True)
        self.result_text_area.setPlaceholderText("Extracted message will appear here...")

        buttons_layout = QHBoxLayout()
        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("DangerBtn")
        self.copy_button = QPushButton("Copy")
        self.copy_button.setObjectName("SecondaryBtn")
        self.export_button = QPushButton("Export .txt")
        self.export_button.setObjectName("SecondaryBtn")
        buttons_layout.addWidget(self.clear_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.copy_button)
        buttons_layout.addWidget(self.export_button)
        for button in (self.clear_button, self.copy_button, self.export_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setEnabled(False)

        self.clear_button.clicked.connect(self.clear_result)
        self.copy_button.clicked.connect(self.copy_result)
        self.export_button.clicked.connect(self.export_result)
        layout.addWidget(title_container)
        layout.addWidget(self.result_text_area, 1)
        layout.addLayout(buttons_layout)
        return card

    def on_decrypt_mode_changed(self, mode: str):
        self.decrypt_stack.setCurrentIndex(0 if mode == "password" else 1)

    def get_inputs(self) -> LSBExtractInputs:
        inputs = LSBExtractInputs(stego_file_path=self.stego_drop_zone.file_path)
        # Ignore values left in inactive decryption fields.
        if self.decrypt_toggle_switch.isChecked():
            if self.decrypt_mode_toggle.mode() == "password":
                inputs.password = self.password_input.text()
            else:
                inputs.private_key_path = self.private_key_source.drop_zone.file_path or None
                inputs.password = self.key_password_input.text() or None
        return inputs

    def validate_inputs(self, inputs: LSBExtractInputs):
        if not inputs.stego_file_path:
            raise ValueError("Select a stego PNG file.")
        path = Path(inputs.stego_file_path)
        if not path.is_file():
            raise ValueError("The selected stego file no longer exists.")
        with path.open("rb") as file:
            if path.suffix.lower() != ".png" or file.read(8) != b"\x89PNG\r\n\x1a\n":
                raise ValueError("Select a valid PNG file.")
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

    def on_stego_file_selected(self, _file_path: str):
        self.clear_result()

    def show_result(self, text: str):
        self.result_text_area.setPlainText(text)
        for button in (self.clear_button, self.copy_button, self.export_button):
            button.setEnabled(bool(text))

    def clear_result(self):
        self.show_result("")

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
