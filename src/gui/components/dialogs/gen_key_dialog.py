from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, 
    QFileDialog, QFormLayout, QHBoxLayout, 
    QLabel, QLineEdit, QMessageBox, 
    QPushButton, QVBoxLayout)

from src.core.crypto.key_management import (
    generate_and_save_keypair, 
    inspect_private_key_file, 
    inspect_public_key_file)

from src.gui.components.gui_utils import add_password_visibility_toggle
from src.gui.services.key_registry import KeyRegistry
from src.gui.services.worker import FunctionWorker

class GenerateKeyDialog(QDialog):
    def __init__(self, registry: KeyRegistry, parent=None):
        super().__init__(parent)
        
        self.registry = registry
        self.generated_paths = None
        self.worker = None
        
        self.setWindowTitle("Generate RSA Key Pair")
        self.setMinimumWidth(560)
        self.build_ui()
        self.update_password_state()

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # -- Key Name --
        key_name_label = QLabel("Key name :")
        key_name_label.setObjectName("dialogFormLabel")

        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("formInput")
        self.name_edit.setPlaceholderText("Example: Alice key")

        form.addRow(key_name_label, self.name_edit)

        # -- Key Size --
        key_size_label = QLabel("Key size :")
        key_size_label.setObjectName("dialogFormLabel")

        self.key_size_combo = QComboBox()
        self.key_size_combo.setObjectName("formInput")
        self.key_size_combo.addItem("RSA-2048", 2048)
        self.key_size_combo.addItem("RSA-3072 (Recommended)", 3072)
        self.key_size_combo.addItem("RSA-4096", 4096)
        self.key_size_combo.setCurrentIndex(1)

        form.addRow(key_size_label, self.key_size_combo)

        # -- File Encoding --
        file_encoding_label = QLabel("File encoding :")
        file_encoding_label.setObjectName("dialogFormLabel")

        self.file_encoding_combo = QComboBox()
        self.file_encoding_combo.setObjectName("formInput")
        self.file_encoding_combo.addItems(["PEM", "DER"])

        form.addRow(file_encoding_label, self.file_encoding_combo)

        # -- Save Destination --
        save_to_label = QLabel("Save to :")
        save_to_label.setObjectName("dialogFormLabel")

        save_to_row = QHBoxLayout()

        self.save_path_edit = QLineEdit(str(Path.home()))
        self.save_path_edit.setObjectName("formInput")

        browse_button = QPushButton("Browse")
        browse_button.setObjectName("SecondaryBtn")
        browse_button.clicked.connect(self.choose_directory)

        save_to_row.addWidget(self.save_path_edit, 1)
        save_to_row.addWidget(browse_button)

        form.addRow(save_to_label, save_to_row)

        # -- Protect Private Key --
        self.protect_checkbox = QCheckBox("Protect private key with a password")
        self.protect_checkbox.setChecked(True)
        self.protect_checkbox.toggled.connect(self.update_password_state)

        form.addRow("", self.protect_checkbox)

        # -- Password --
        password_label = QLabel("Password :")
        password_label.setObjectName("dialogFormLabel")

        self.password_edit = QLineEdit()
        self.password_edit.setObjectName("formInput")
        self.password_edit.setEchoMode(
            QLineEdit.EchoMode.Password
        )
        self.password_edit.setPlaceholderText("Private key password")

        form.addRow(password_label, self.password_edit)

        # -- Confirm Password --
        confirm_label = QLabel("Confirm :")
        confirm_label.setObjectName("dialogFormLabel")

        self.confirm_edit = QLineEdit()
        self.confirm_edit.setObjectName("formInput")
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit.setPlaceholderText("Confirm private key password")

        add_password_visibility_toggle( self.password_edit,self.confirm_edit)

        form.addRow(confirm_label, self.confirm_edit)

        layout.addLayout(form)

        # -- Hint --
        note = QLabel("Exports .pem/.der files. SIENG2 never stores the password.")
        note.setObjectName("hintLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        # -- Buttons --
        buttons = QHBoxLayout()
        buttons.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("SecondaryBtn")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)

        self.generate_button = QPushButton("Generate Key Pair")
        self.generate_button.setObjectName("PrimaryActionBtn")
        self.generate_button.clicked.connect(self.generate)
        buttons.addWidget(self.generate_button)

        layout.addLayout(buttons)

    def choose_directory(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Save RSA Key Pair")
        if path:
            self.save_path_edit.setText(path)

    def update_password_state(self) -> None:
        enabled = self.protect_checkbox.isChecked()
        self.password_edit.setEnabled(enabled)
        self.confirm_edit.setEnabled(enabled)

    def generate(self) -> None:
        password = None
        if self.protect_checkbox.isChecked():
            password = self.password_edit.text()
            if not password:
                QMessageBox.warning(self, "Generate RSA Key Pair", "Enter a private key password.")
                return
            if password != self.confirm_edit.text():
                QMessageBox.warning(self, "Generate RSA Key Pair", "The passwords do not match.")
                return

        self.generate_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.generate_button.setText("Generating...")
        self.worker = FunctionWorker(
            generate_and_save_keypair,
            self.save_path_edit.text(),
            self.name_edit.text(),
            key_size=self.key_size_combo.currentData(),
            password=password,
            encoding=self.file_encoding_combo.currentText(),
        )
        self.worker.done.connect(lambda result: self.generation_done(result, password))
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def generation_done(self, result, password) -> None:
        if isinstance(result, dict) and result.get("error"):
            QMessageBox.warning(self, "Generate RSA Key Pair", result["error"])
            self.generate_button.setEnabled(True)
            self.cancel_button.setEnabled(True)
            self.generate_button.setText("Generate Key Pair")
            return

        private_path, public_path = result
        private_info = inspect_private_key_file(private_path, password)
        public_info = inspect_public_key_file(public_path)
        base_label = self.name_edit.text().strip()
        self.registry.add(f"{base_label} (Private)", private_info)
        self.registry.add(f"{base_label} (Public)", public_info)
        self.generated_paths = private_path, public_path
        self.password_edit.clear()
        self.confirm_edit.clear()
        self.accept()