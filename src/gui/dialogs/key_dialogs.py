from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from src.core.crypto.key_management import (
    generate_and_save_keypair,
    inspect_key_file,
    inspect_private_key_file,
    inspect_public_key_file,
)
from src.gui.components.password_visibility import add_password_visibility_toggle
from src.gui.components.worker import FunctionWorker
from src.gui.services.key_registry import KeyRegistry


KEY_FILTER = "RSA key files (*.pem *.der *.pub *.key);;All files (*.*)"


class KeyPickerDialog(QDialog):
    def __init__(self, registry: KeyRegistry, role: str, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.role = role
        self.selected_path: str | None = None
        self.setWindowTitle(f"Choose RSA {role.title()} Key")
        self.setMinimumSize(560, 390)
        self.build_ui()
        self.refresh()

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(f"Saved RSA {self.role.title()} Keys")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        hint = QLabel("Only keys with the correct role are shown. Missing files cannot be selected.")
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.key_list = QListWidget()
        self.key_list.setObjectName("keyPickerList")
        self.key_list.itemDoubleClicked.connect(lambda _item: self.accept_selected())
        self.key_list.itemSelectionChanged.connect(self.update_button)
        layout.addWidget(self.key_list, 1)

        buttons = QHBoxLayout()
        browse_button = QPushButton("Browse Another File")
        browse_button.setObjectName("SecondaryBtn")
        browse_button.clicked.connect(self.browse_file)
        buttons.addWidget(browse_button)
        buttons.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("SecondaryBtn")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)

        self.use_button = QPushButton("Use Selected Key")
        self.use_button.setObjectName("PrimaryActionBtn")
        self.use_button.setEnabled(False)
        self.use_button.clicked.connect(self.accept_selected)
        buttons.addWidget(self.use_button)
        layout.addLayout(buttons)

    def refresh(self) -> None:
        self.key_list.clear()
        records = self.registry.records(self.role) if self.registry else []
        for record in records:
            size = f"RSA-{record.key_size}" if record.key_size else "RSA key"
            status = "" if record.exists else "  •  File missing"
            protection = "  •  Encrypted" if record.encrypted else ""
            item = QListWidgetItem(
                f"{record.label}\n{size}  •  {record.encoding}/{record.container}{protection}{status}"
            )
            item.setData(Qt.ItemDataRole.UserRole, record.path)
            item.setToolTip(record.path)
            item.setSizeHint(QSize(0, 62))
            if not record.exists:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.key_list.addItem(item)

        if not records:
            item = QListWidgetItem("No saved keys yet. You can browse a file for this operation.")
            item.setSizeHint(QSize(0, 48))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.key_list.addItem(item)

    def update_button(self) -> None:
        item = self.key_list.currentItem()
        self.use_button.setEnabled(bool(item and item.data(Qt.ItemDataRole.UserRole)))

    def accept_selected(self) -> None:
        item = self.key_list.currentItem()
        if item and item.data(Qt.ItemDataRole.UserRole):
            self.selected_path = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose RSA Key", "", KEY_FILTER)
        if not path:
            return
        try:
            if self.role == "public":
                inspect_public_key_file(path)
            else:
                inspect_private_key_file(path)
        except (OSError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "Invalid RSA Key", str(error))
            return
        self.selected_path = path
        self.accept()


class ImportKeyDialog(QDialog):
    def __init__(self, registry: KeyRegistry, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.imported_record = None
        self.setWindowTitle("Import Existing RSA Key")
        self.setMinimumWidth(560)
        self.build_ui()

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Import Existing RSA Key")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        form = QFormLayout()
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("Example: Alice public key")
        form.addRow("Display name", self.label_edit)

        file_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        browse_button = QPushButton("Browse")
        browse_button.setObjectName("SecondaryBtn")
        browse_button.clicked.connect(self.browse_file)
        file_row.addWidget(self.path_edit, 1)
        file_row.addWidget(browse_button)
        form.addRow("Key file", file_row)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Only needed to inspect an encrypted private key")
        add_password_visibility_toggle(self.password_edit)
        form.addRow("Key password", self.password_edit)
        layout.addLayout(form)

        note = QLabel("The password is used only during import and is never saved.")
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
            self.path_edit.setText(path)
            if not self.label_edit.text().strip():
                self.label_edit.setText(Path(path).stem)

    def import_key(self) -> None:
        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "Import RSA Key", "Choose a key file first.")
            return
        password = self.password_edit.text() or None
        try:
            info = inspect_key_file(path, password)
            self.imported_record = self.registry.add(self.label_edit.text(), info)
        except (OSError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "Import RSA Key", str(error))
            return
        self.password_edit.clear()
        self.accept()


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
        title = QLabel("Generate RSA Key Pair")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Example: Alice key")
        form.addRow("Key name", self.name_edit)

        self.size_combo = QComboBox()
        self.size_combo.addItem("RSA-2048", 2048)
        self.size_combo.addItem("RSA-3072 (Recommended)", 3072)
        self.size_combo.addItem("RSA-4096", 4096)
        self.size_combo.setCurrentIndex(1)
        form.addRow("Key size", self.size_combo)

        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(["PEM", "DER"])
        form.addRow("File encoding", self.encoding_combo)

        destination_row = QHBoxLayout()
        self.directory_edit = QLineEdit(str(Path.home()))
        destination_button = QPushButton("Browse")
        destination_button.setObjectName("SecondaryBtn")
        destination_button.clicked.connect(self.choose_directory)
        destination_row.addWidget(self.directory_edit, 1)
        destination_row.addWidget(destination_button)
        form.addRow("Save to", destination_row)

        self.protect_checkbox = QCheckBox("Protect private key with a password")
        self.protect_checkbox.setObjectName("protectPrivateKeyCheckbox")
        self.protect_checkbox.setChecked(True)
        self.protect_checkbox.toggled.connect(self.update_password_state)
        form.addRow("", self.protect_checkbox)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Private key password")
        add_password_visibility_toggle(self.password_edit)
        form.addRow("Password", self.password_edit)

        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit.setPlaceholderText("Confirm private key password")
        add_password_visibility_toggle(self.confirm_edit)
        form.addRow("Confirm", self.confirm_edit)
        layout.addLayout(form)

        note = QLabel("Exports .pem/.der files. SIENG2 never stores the password.")
        note.setObjectName("hintLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

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
            self.directory_edit.setText(path)

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
            self.directory_edit.text(),
            self.name_edit.text(),
            key_size=self.size_combo.currentData(),
            password=password,
            encoding=self.encoding_combo.currentText(),
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
