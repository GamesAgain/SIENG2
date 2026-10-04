from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, 
    QLabel, QLineEdit, QListWidget, 
    QListWidgetItem, QMessageBox, QPushButton, 
    QVBoxLayout)
from PyQt6.QtCore import QSize, Qt

from src.gui.components.dialogs.key_inspection_dialog import inspect_key_with_password_prompt
from src.gui.components.widgets.key_list import KeyListItemWidget
from src.gui.services.key_registry import KeyRegistry

KEY_FILTER = "RSA key files (*.pem *.der *.pub *.key);;All files (*.*)"
FINGERPRINT_ROLE = Qt.ItemDataRole.UserRole.value + 1 # Qt.ItemDataRole.UserRole เก็บ RSA file path + 1 มาเพื่อเก็บ fingerprint

class KeyPickerDialog(QDialog):
    def __init__(self, registry: KeyRegistry, role: str, verify_form: bool = False, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.role = role
        self.verify_form = verify_form
        self.selected_path: str | None = None
        self.fingerprint: str | None = None
        self.fingerprint_edit: QLineEdit | None = None
        self.setWindowTitle(f"Choose RSA {role.title()} Key")
        self.setMinimumSize(560, 390)
        self.build_ui()
        self.refresh()

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(f"Saved RSA {self.role.title()} Keys")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        hint_text = "Only keys with the correct role are shown. Missing files cannot be selected."
        if self.verify_form:
            hint_text = (
                "Select a saved key or enter its SHA-256 fingerprint. "
                "Missing files cannot be selected."
            )
        hint = QLabel(hint_text)
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.key_list = QListWidget()
        self.key_list.setObjectName("keyList")
        self.key_list.itemDoubleClicked.connect(lambda item: self.accept_selected())
        self.key_list.itemSelectionChanged.connect(self.on_key_selection_changed)
        layout.addWidget(self.key_list, 1)

        buttons_layout = QHBoxLayout()
        browse_button = QPushButton("Browse Another File")
        browse_button.setObjectName("SecondaryBtn")
        browse_button.clicked.connect(self.browse_file)
        buttons_layout.addWidget(browse_button)
        
        # แสดง Fingerprint QLineEdit เมื่อเปิด  Verify pair key
        if self.verify_form:
            fingerprint_layout = QHBoxLayout()
            self.fingerprint_edit = QLineEdit()
            self.fingerprint_edit.setObjectName("formInput")
            self.fingerprint_edit.setPlaceholderText(
                "SHA-256 fingerprint, e.g. AA:BB:CC:..."
            )
            self.fingerprint_edit.textChanged.connect(self.update_button)
            fingerprint_layout.addWidget(self.fingerprint_edit)
            layout.addLayout(fingerprint_layout)

            self.clear_selection_button = QPushButton("Clear Key Selection")
            self.clear_selection_button.setObjectName("SecondaryBtn")
            self.clear_selection_button.clicked.connect(self.clear_key_selection)
            buttons_layout.addWidget(self.clear_selection_button)
            
        buttons_layout.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("SecondaryBtn")
        cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_button)

        self.use_button = QPushButton("Use Selected Key")
        self.use_button.setObjectName("PrimaryActionBtn")
        self.use_button.setEnabled(False)
        self.use_button.clicked.connect(self.accept_selected)
        buttons_layout.addWidget(self.use_button)
        layout.addLayout(buttons_layout)
        self.update_button()

    def refresh(self) -> None:
        self.key_list.clear()
        records = self.registry.records(self.role) if self.registry else []
        for record in records:
            size = f"RSA-{record.key_size}" if record.key_size else "RSA key"
            status = "" if record.exists else "  •  File missing"
            protection = "  •  Encrypted" if record.encrypted else ""
            
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, record.path)
            item.setData(FINGERPRINT_ROLE, record.fingerprint)
            item.setToolTip(record.path)
            item.setSizeHint(QSize(0, 62))
            if not record.exists:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled) # หักเอาสถานะ "Enabled" ออก โดยไม่ไปยุ่งกับสถานะอื่นๆ ที่ไอเท็มนั้นมีอยู่เดิม
            self.key_list.addItem(item)
            self.key_list.setItemWidget(item, KeyListItemWidget(record.label, f"{size} [{record.encoding}/{record.container}{protection}{status}]"))
            

        if not records:
            item = QListWidgetItem("No saved keys yet. You can browse a file for this operation.")
            item.setSizeHint(QSize(0, 48))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.key_list.addItem(item)

    def on_key_selection_changed(self) -> None:
        for row in range(self.key_list.count()):
            item = self.key_list.item(row)
            widget = self.key_list.itemWidget(item)
            if isinstance(widget, KeyListItemWidget):
                widget.set_selected(item.isSelected())
        self.update_button()

    def update_button(self) -> None:
        selected_items = self.key_list.selectedItems()
        item = selected_items[0] if selected_items else None
        has_selected_key = bool(item and item.data(Qt.ItemDataRole.UserRole))

        if not self.verify_form:
            self.use_button.setEnabled(has_selected_key)
            return

        if has_selected_key:
            self.use_button.setText("Use Selected Key")
            self.use_button.setEnabled(True)
            self.clear_selection_button.setEnabled(True)
            return

        self.use_button.setText("Verify Fingerprint")
        has_entered_fingerprint = bool(self.fingerprint_edit.text().strip())
        self.use_button.setEnabled(has_entered_fingerprint)
        self.clear_selection_button.setEnabled(False)

    def clear_key_selection(self) -> None:
        self.key_list.clearSelection()
        self.key_list.setCurrentItem(None)

    def accept_selected(self) -> None:
        selected_items = self.key_list.selectedItems()
        item = selected_items[0] if selected_items else None
        selected_path = item.data(Qt.ItemDataRole.UserRole) if item else None

        if not self.verify_form:
            if not selected_path:
                return
            self.selected_path = selected_path
            self.accept()
            return

        if selected_path:
            selected_fingerprint = item.data(FINGERPRINT_ROLE)
            if not selected_fingerprint:
                info = inspect_key_with_password_prompt(self, selected_path)
                if not info or info.role != self.role:
                    return
                selected_fingerprint = info.fingerprint
            self.fingerprint = selected_fingerprint
        else:
            entered_fingerprint = self.fingerprint_edit.text().strip()
            self.fingerprint = entered_fingerprint.upper()

        self.selected_path = selected_path
        self.accept()

    def browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose RSA Key", "", KEY_FILTER)
        if not path:
            return
        info = inspect_key_with_password_prompt(self, path)
        if not info:
            return
        if info.role != self.role:
            QMessageBox.warning(self, "Invalid RSA Key", f"Choose an RSA {self.role} key file.")
            return

        if self.verify_form:
            self.fingerprint = info.fingerprint

        self.selected_path = path
        self.accept()
