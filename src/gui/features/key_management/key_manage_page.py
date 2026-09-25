from pathlib import Path
import subprocess

from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog,
    QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)
from PyQt6.QtCore import QSize, QUrl, Qt
from PyQt6.QtGui import QDesktopServices

from src.gui.components.dialogs.gen_key_dialog import GenerateKeyDialog
from src.gui.components.dialogs.import_key_dialog import ImportKeyDialog
from src.gui.components.dialogs.key_picker_dialog import KeyPickerDialog
from src.gui.components.dialogs.key_inspection_dialog import inspect_key_with_password_prompt
from src.gui.components.gui_utils import add_shadow_effect
from src.gui.components.widgets.key_list_widget import KeyListItemWidget
from src.gui.services.key_registry import KeyRegistry

KEY_FILTER = "RSA key files (*.pem *.der *.pub *.key);;All files (*.*)"

class KeyManagementPage(QFrame):
    
    def __init__(self, registry: KeyRegistry, parent=None):
        super().__init__(parent)
        
        self.registry = registry
        
        self.setup_ui()
        
        self.registry.changed.connect(self.refresh) # ADD, REMOVE, DATA_CHANGE
        self.refresh()
        
        
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        
        # -- Page title --
        header = QHBoxLayout()
        heading = QVBoxLayout()
        self.title_label = QLabel("Key Management")
        self.title_label.setObjectName("pageTitle")
        subtitle = QLabel("Manage reusable RSA key references for Embed and Extract.")
        subtitle.setObjectName("hintLabel")
        heading.addWidget(self.title_label)
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch()
        
        # -- Import & Generate Key Section --
        self.import_button = QPushButton("Import Existing Key")
        self.import_button.setObjectName("SecondaryBtn")
        self.import_button.clicked.connect(self.open_import_dialog)
        self.generate_button = QPushButton("Generate Key Pair")
        self.generate_button.setObjectName("PrimaryActionBtn")
        self.generate_button.clicked.connect(self.open_generate_dialog)

        action_size = self.generate_button.sizeHint()
        self.import_button.setFixedSize(action_size)
        self.generate_button.setFixedSize(action_size)
        header.addWidget(self.import_button)
        header.addWidget(self.generate_button)
        layout.addLayout(header)
        
        # -- Save keys & Key Details Layout--
        content_layout = QHBoxLayout()
        content_layout.setSpacing(14)
        
        # -- Saved Keys Card --
        list_card = QFrame()
        list_card.setObjectName("card")
        add_shadow_effect(list_card)
        list_layout = QVBoxLayout(list_card)
        list_title = QLabel("Saved Keys")
        list_title.setObjectName("cardTitle")
        list_layout.addWidget(list_title)
        self.key_list = QListWidget()
        self.key_list.setObjectName("keyList")
        self.key_list.currentItemChanged.connect(self.on_key_selection_changed)
        list_layout.addWidget(self.key_list, 1)
        content_layout.addWidget(list_card, 5)
        
        # -- Key Details Card --
        detail_card = QFrame()
        detail_card.setObjectName("card")
        add_shadow_effect(detail_card)
        detail_layout = QVBoxLayout(detail_card)
        detail_title = QLabel("Key Details")
        detail_title.setObjectName("cardTitle")
        detail_layout.addWidget(detail_title)
        
        # --- Details Section ---
        self.detail_grid = QGridLayout()
        self.detail_grid.setColumnStretch(1, 1)
        self.detail_values = {}
        fields = ["Name", "Role", "Algorithm", "Format", "Protection", "Fingerprint", "File"]
        for row, field in enumerate(fields):
            label = QLabel(f'{field} :')
            label.setObjectName("formLabel")
            value = QLabel("—")
            value.setObjectName("keyDetailValue")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.detail_grid.addWidget(label, row, 0, Qt.AlignmentFlag.AlignBaseline)
            self.detail_grid.addWidget(value, row, 1, Qt.AlignmentFlag.AlignBaseline)
            self.detail_values[field] = value
            if field == "Fingerprint":
                self.copy_fingerprint_button = QPushButton("Copy")
                self.copy_fingerprint_button.setObjectName("CopyFingerprintBtn")
                self.copy_fingerprint_button.setToolTip("Copy fingerprint")
                self.copy_fingerprint_button.setEnabled(False)
                self.copy_fingerprint_button.clicked.connect(self.copy_fingerprint)
                self.detail_grid.addWidget(
                    self.copy_fingerprint_button,
                    row,
                    2,
                    Qt.AlignmentFlag.AlignBaseline,
                )
        detail_layout.addLayout(self.detail_grid)
        detail_layout.addStretch()
        
        # --- Action Button Section ---
        first_row = QHBoxLayout()
        self.verify_button = QPushButton("Verify Pair")
        self.verify_button.setObjectName("SecondaryBtn")
        self.verify_button.clicked.connect(self.verify_pair)
        first_row.addWidget(self.verify_button)
        self.edit_name_button = QPushButton("Edit Display Name")
        self.edit_name_button.setObjectName("SecondaryBtn")
        self.edit_name_button.clicked.connect(self.edit_display_name)
        first_row.addWidget(self.edit_name_button)
        detail_layout.addLayout(first_row)
        
        second_row = QHBoxLayout()
        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.setObjectName("SecondaryBtn")
        self.open_folder_button.clicked.connect(self.open_locate_file)
        second_row.addWidget(self.open_folder_button)
        self.remove_button = QPushButton("Remove from List")
        self.remove_button.setObjectName("DangerBtn")
        self.remove_button.clicked.connect(self.remove_selected)
        second_row.addWidget(self.remove_button)
        detail_layout.addLayout(second_row)
        
        content_layout.addWidget(detail_card, 6)
        layout.addLayout(content_layout, 1)
        self.set_actions_enabled(False)
    
    
    # --- Event handler ---
    def current_record(self):
        item = self.key_list.currentItem()
        if not item:
            return None
        return self.registry.get(item.data(Qt.ItemDataRole.UserRole))
    
    def refresh(self):
        current_id = self.current_record().id if self.current_record() else None
        self.key_list.clear()
        selected_item = None
        for record in self.registry.records():
            size = f"RSA-{record.key_size}" if record.key_size else "RSA"
            role = "Private Key" if record.role == "private" else "Public Key"
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            item.setData(
                Qt.ItemDataRole.AccessibleTextRole,
                f"{record.label}, {role} [{size}]",
            )
            item.setToolTip(record.path)
            item.setSizeHint(QSize(0, 62))
            self.key_list.addItem(item)
            self.key_list.setItemWidget(item, KeyListItemWidget(record.label, f"{role} [{size}]"))
            if record.id == current_id:
                selected_item = item
        if not self.key_list.count():
            empty_item = QListWidgetItem("No keys yet. Generate a pair or import an existing key.")
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags) # ล้างคุณสมบัติทุกอย่าง
            empty_item.setSizeHint(QSize(0, 52))
            self.key_list.addItem(empty_item)
            self.copy_fingerprint_button.setVisible(False)
            self.show_details()
        elif selected_item:
            self.key_list.setCurrentItem(selected_item)
            self.copy_fingerprint_button.setVisible(True)
        else:
            self.key_list.setCurrentRow(0)
            self.copy_fingerprint_button.setVisible(True)
            
    def on_key_selection_changed(self, current, previous) -> None:
        for item, selected in ((previous, False), (current, True)):
            if item is None:
                continue
            widget = self.key_list.itemWidget(item)
            if isinstance(widget, KeyListItemWidget):
                widget.set_selected(selected)
        self.show_details()
    
    def show_details(self) -> None:
        record = self.current_record()
        if record is None:
            for value in self.detail_values.values():
                value.setText("—")
            self.copy_fingerprint_button.setEnabled(False)
            self.set_actions_enabled(False)
            return

        values = {
            "Name": record.label,
            "Role": record.role.title(),
            "Algorithm": f"RSA-{record.key_size}" if record.key_size else "RSA (password required to inspect)",
            "Format": f"{record.encoding} / {record.container}",
            "Protection": self.protection_text(record),
            "Fingerprint": record.fingerprint or "Password required to calculate",
            "File": record.path if record.exists else f"Missing: {record.path}",
        }
        for field, value in values.items():
            self.detail_values[field].setText(value)
        self.copy_fingerprint_button.setEnabled(bool(record.fingerprint))
        self.set_actions_enabled(True)
        self.open_folder_button.setText("Open Folder" if record.exists else "Locate File")
        self.open_folder_button.setEnabled(True)
    
    @staticmethod
    def protection_text(record) -> str:
        if record.role == "public":
            return "Not applicable (public key)"
        return "Encrypted" if record.encrypted else "Unencrypted"
    
    def set_actions_enabled(self, enabled: bool) -> None:
        for button in (
            self.verify_button,
            self.edit_name_button,
            self.open_folder_button,
            self.remove_button,
        ):
            button.setEnabled(enabled)

    def copy_fingerprint(self) -> None:
        record = self.current_record()
        if record and record.fingerprint:
            QApplication.clipboard().setText(record.fingerprint)
            
    def open_import_dialog(self):
        ImportKeyDialog(self.registry, self).exec()
            
    def open_generate_dialog(self):
        GenerateKeyDialog(self.registry, self).exec()
        
    def verify_pair(self) -> None:
        record = self.current_record()
        if not record or not record.exists:
            QMessageBox.warning(self, "Verify RSA Pair", "The selected key file is missing.")
            return
        record_fingerprint = record.fingerprint
        if not record_fingerprint:
            info = inspect_key_with_password_prompt(self, record.path)
            if not info or info.role != record.role:
                return
            record_fingerprint = info.fingerprint
        if not record_fingerprint:
            QMessageBox.warning(self, "Verify RSA Pair", "The selected key fingerprint is unavailable.")
            return
        other_role = "private" if record.role == "public" else "public"
        picker = KeyPickerDialog(self.registry, other_role, verify_form=True, parent=self)
        if not picker.exec() or not picker.fingerprint:
            return

        fingerprints = [record_fingerprint, picker.fingerprint]
        if all(fingerprints):
            matches = fingerprints[0] == fingerprints[1]
            title = "Keys Match" if matches else "Keys Do Not Match"
            text = "The selected public and private keys are a valid pair." if matches else "The selected keys are not a pair."
            QMessageBox.information(self, title, text)
            return

        QMessageBox.information(
            self,
            "Password Required",
            "Import the encrypted private key with its password once to calculate its fingerprint, then verify again. The password will not be saved.",
        )
        
    def edit_display_name(self) -> None:
        record = self.current_record()
        if not record:
            return

        label, accepted = QInputDialog.getText(
            self,
            "Edit Display Name",
            "Display name",
            text=record.label,
        )
        if not accepted:
            return
        try:
            self.registry.rename(record.id, label)
        except (KeyError, ValueError) as error:
            QMessageBox.warning(self, "Edit Display Name", str(error))
            
    def open_locate_file(self) -> None:
        record = self.current_record()

        if record and record.exists:
            file_path = Path(record.path)
            
            # เรียก subprocess open แบบ process และ select file ด้วย
            subprocess.Popen(["explorer.exe", "/select,", str(file_path)])
            return
        
        # ถ้า Key file ถูกย้าย/ลบ จะเปิด file dialog ให้ locate ใหม่ และบันทึก
        if not record:
            return
        
        path, _ = QFileDialog.getOpenFileName(self, "Locate RSA Key", "", KEY_FILTER)

        if not path:
            return

        info = inspect_key_with_password_prompt(self, path)
        if not info:
            return
        if info.role != record.role:
            QMessageBox.warning(self, "Locate RSA Key", f"Choose an RSA {record.role} key file.")
            return
        self.registry.update_path(record.id, info)
            
    def remove_selected(self) -> None:
        record = self.current_record()
        if not record:
            return
        answer = QMessageBox.question(
            self,
            "Remove Key Reference",
            "Remove this key from Key Management? The key file will not be deleted.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.registry.remove(record.id)
