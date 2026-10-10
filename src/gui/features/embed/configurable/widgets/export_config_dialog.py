"""Options for exporting a pipeline (secrets are excluded by default)."""
from PyQt6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout


class ExportConfigDialog(QDialog):
    def __init__(self, name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Config")
        self.setObjectName("exportConfigDialog")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        label = QLabel("Pipeline name (optional)")
        label.setObjectName("formLabel")
        layout.addWidget(label)
        self.name_edit = QLineEdit(name)
        self.name_edit.setObjectName("formInput")
        self.name_edit.setPlaceholderText("Name this pipeline")
        layout.addWidget(self.name_edit)

        self.include_secret = QCheckBox("Include secret text")
        self.include_passwords = QCheckBox("Include passwords")
        layout.addWidget(self.include_secret)
        layout.addWidget(self.include_passwords)
        self.warning_label = QLabel("This file will contain your secret in plain text.")
        self.warning_label.setObjectName("exportSecretWarning")
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        layout.addWidget(self.warning_label)
        self.include_secret.toggled.connect(self.update_warning)
        self.include_passwords.toggled.connect(self.update_warning)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("SecondaryBtn")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        self.export_button = QPushButton("Export")
        self.export_button.setObjectName("PrimaryActionBtn")
        self.export_button.setDefault(True)
        self.export_button.clicked.connect(self.accept)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.export_button)
        layout.addLayout(buttons)

    def update_warning(self):
        self.warning_label.setVisible(self.include_secret.isChecked() or self.include_passwords.isChecked())
