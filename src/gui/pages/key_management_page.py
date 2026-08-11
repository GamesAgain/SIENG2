"""Key Management page for generated and imported RSA key references."""
from pathlib import Path

from PyQt6.QtCore import QSize, QUrl, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QInputDialog,
    QPushButton,
    QVBoxLayout,
)

from src.core.crypto.key_management import inspect_private_key_file, inspect_public_key_file
from src.gui.components.gui_utils import add_shadow_effect
from src.gui.dialogs.key_dialogs import KEY_FILTER, GenerateKeyDialog, ImportKeyDialog, KeyPickerDialog
from src.gui.services.key_registry import KeyRegistry


class KeyListItemWidget(QFrame):
    def __init__(self, display_name: str, detail: str):
        super().__init__()
        self.setObjectName("keyListItemContent")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 3, 2, 3)
        layout.setSpacing(3)

        self.name_label = QLabel(display_name)
        self.name_label.setObjectName("keyListDisplayName")
        self.detail_label = QLabel(detail)
        self.detail_label.setObjectName("keyListSummary")
        self.name_label.setProperty("selected", False)
        self.detail_label.setProperty("selected", False)

        layout.addWidget(self.name_label)
        layout.addWidget(self.detail_label)

    def set_selected(self, selected: bool) -> None:
        for label in (self.name_label, self.detail_label):
            label.setProperty("selected", selected)
            label.style().unpolish(label)
            label.style().polish(label)


class KeyManagementPage(QFrame):
    def __init__(self, registry: KeyRegistry):
        super().__init__()
        self.registry = registry
        self.setObjectName("keyManagementPage")
        self.build_ui()
        self.registry.changed.connect(self.refresh)
        self.refresh()

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

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

        content = QHBoxLayout()
        content.setSpacing(14)

        list_card = QFrame()
        list_card.setObjectName("card")
        add_shadow_effect(list_card)
        list_layout = QVBoxLayout(list_card)
        list_title = QLabel("Saved Keys")
        list_title.setObjectName("cardTitle")
        list_layout.addWidget(list_title)
        self.key_list = QListWidget()
        self.key_list.setObjectName("keyManagementList")
        self.key_list.currentItemChanged.connect(self.on_key_selection_changed)
        list_layout.addWidget(self.key_list, 1)
        content.addWidget(list_card, 5)

        detail_card = QFrame()
        detail_card.setObjectName("card")
        add_shadow_effect(detail_card)
        detail_layout = QVBoxLayout(detail_card)
        detail_title = QLabel("Key Details")
        detail_title.setObjectName("cardTitle")
        detail_layout.addWidget(detail_title)

        self.detail_grid = QGridLayout()
        self.detail_grid.setColumnStretch(1, 1)
        self.detail_values = {}
        fields = ["Name", "Role", "Algorithm", "Format", "Protection", "Fingerprint", "File"]
        for row, field in enumerate(fields):
            label = QLabel(field)
            label.setObjectName("formLabel")
            value = QLabel("—")
            value.setObjectName("keyDetailValue")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.detail_grid.addWidget(label, row, 0, Qt.AlignmentFlag.AlignTop)
            self.detail_grid.addWidget(value, row, 1)
            self.detail_values[field] = value
        detail_layout.addLayout(self.detail_grid)
        detail_layout.addStretch()

        action_row = QHBoxLayout()
        self.verify_button = QPushButton("Verify Pair")
        self.verify_button.setObjectName("SecondaryBtn")
        self.verify_button.clicked.connect(self.verify_pair)
        action_row.addWidget(self.verify_button)
        self.edit_name_button = QPushButton("Edit Display Name")
        self.edit_name_button.setObjectName("SecondaryBtn")
        self.edit_name_button.clicked.connect(self.edit_display_name)
        action_row.addWidget(self.edit_name_button)
        detail_layout.addLayout(action_row)

        file_row = QHBoxLayout()
        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.setObjectName("SecondaryBtn")
        self.open_folder_button.clicked.connect(self.open_or_locate_file)
        file_row.addWidget(self.open_folder_button)
        self.remove_button = QPushButton("Remove from List")
        self.remove_button.setObjectName("DangerBtn")
        self.remove_button.clicked.connect(self.remove_selected)
        file_row.addWidget(self.remove_button)
        detail_layout.addLayout(file_row)

        content.addWidget(detail_card, 6)
        layout.addLayout(content, 1)
        self.set_actions_enabled(False)

    def current_record(self):
        item = self.key_list.currentItem()
        if not item:
            return None
        return self.registry.get(item.data(Qt.ItemDataRole.UserRole))

    def refresh(self) -> None:
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
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            empty_item.setSizeHint(QSize(0, 52))
            self.key_list.addItem(empty_item)
            self.show_details()
        elif selected_item:
            self.key_list.setCurrentItem(selected_item)
        else:
            self.key_list.setCurrentRow(0)

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

    def open_generate_dialog(self) -> None:
        GenerateKeyDialog(self.registry, self).exec()

    def open_import_dialog(self) -> None:
        ImportKeyDialog(self.registry, self).exec()

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

    def open_or_locate_file(self) -> None:
        record = self.current_record()
        if record and record.exists:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(record.path).parent)))
            return
        if not record:
            return

        path, _ = QFileDialog.getOpenFileName(self, "Locate RSA Key", "", KEY_FILTER)
        if not path:
            return
        try:
            info = (
                inspect_public_key_file(path)
                if record.role == "public"
                else inspect_private_key_file(path)
            )
            self.registry.update_path(record.id, info)
        except (OSError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "Locate RSA Key", str(error))

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

    def verify_pair(self) -> None:
        record = self.current_record()
        if not record or not record.exists:
            QMessageBox.warning(self, "Verify RSA Pair", "The selected key file is missing.")
            return
        other_role = "private" if record.role == "public" else "public"
        picker = KeyPickerDialog(self.registry, other_role, self)
        if not picker.exec() or not picker.selected_path:
            return

        other = next(
            (item for item in self.registry.records(other_role) if item.path == picker.selected_path),
            None,
        )
        fingerprints = [record.fingerprint, other.fingerprint if other else None]
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