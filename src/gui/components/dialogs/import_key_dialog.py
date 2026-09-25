
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, 
    QHBoxLayout, QLabel, QLineEdit, 
    QMessageBox, QPushButton, QVBoxLayout)

from src.gui.components.dialogs.key_inspection_dialog import inspect_key_with_password_prompt
from src.gui.services.key_registry import KeyRegistry

KEY_FILTER = "RSA key files (*.pem *.der *.pub *.key);;All files (*.*)"

class ImportKeyDialog(QDialog):
    
    def __init__(self, registry: KeyRegistry, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.imported_record = None
        self.selected_info = None
        self.setWindowTitle("Import Existing RSA Key")
        self.setMinimumWidth(560)
        self.build_ui()
        
    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        
        # -- Display Name --
        form = QFormLayout()
        display_name_label = QLabel("Display name :")
        display_name_label.setObjectName("dialogFormLabel")
        self.label_edit = QLineEdit()
        self.label_edit.setObjectName("formInput")
        self.label_edit.setPlaceholderText("Example: Alice public key")
        form.addRow(display_name_label, self.label_edit)
        
        # -- Key file --
        file_row = QHBoxLayout()
        key_file_label = QLabel("Key file :")
        key_file_label.setObjectName("dialogFormLabel")
        self.path_edit = QLineEdit()
        self.path_edit.setObjectName("formInput")
        self.path_edit.setPlaceholderText("No file selected...")
        self.path_edit.setReadOnly(True)
        browse_button = QPushButton("Browse")
        browse_button.setObjectName("SecondaryBtn")
        browse_button.clicked.connect(self.browse_file)
        file_row.addWidget(self.path_edit, 1)
        file_row.addWidget(browse_button)
        form.addRow(key_file_label, file_row)
        
        layout.addLayout(form)

        note = QLabel("Encrypted private keys ask for a password when selected. The password is never saved.")
        note.setObjectName("hintLabel")
        layout.addWidget(note)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("SecondaryBtn")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        import_button = QPushButton("Import Key")
        import_button.setObjectName("PrimaryActionBtn")
        import_button.clicked.connect(self.import_key)
        buttons.addWidget(import_button)
        layout.addLayout(buttons)
        
    def browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import RSA Key", "", KEY_FILTER)
        if path:
            info = inspect_key_with_password_prompt(self, path)
            if not info:
                return
            self.selected_info = info
            self.path_edit.setText(path)
            if not self.label_edit.text().strip():
                self.label_edit.setText(Path(path).stem)

    def import_key(self) -> None:
        if not self.selected_info:
            QMessageBox.warning(self, "Import RSA Key", "Choose a key file first.")
            return
        self.imported_record = self.registry.add(self.label_edit.text(), self.selected_info)
        self.accept()
