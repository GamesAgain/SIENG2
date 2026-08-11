from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QVBoxLayout

from src.gui.components.files_drop import FileDropWidget
from src.gui.components.gui_utils import create_icon_pixmap
from src.gui.dialogs.key_dialogs import KeyPickerDialog
from src.gui.services.key_registry import KeyRegistry


ICON_DIR = Path(__file__).parent.parent / "assets" / "svg"


class KeySourceWidget(QFrame):
    key_selected = pyqtSignal(str)

    def __init__(self, role: str, registry: KeyRegistry | None = None):
        super().__init__()
        if role not in {"public", "private"}:
            raise ValueError("Key role must be public or private.")

        self.role = role
        self.registry = registry
        self.setObjectName("keySourceWidget")
        self.build_ui()

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        action_row = QHBoxLayout()
        self.choose_button = QPushButton(" Choose Saved Key")
        self.choose_button.setObjectName("KeyLibraryBtn")
        self.choose_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.choose_button.setIcon(
            QIcon(create_icon_pixmap(ICON_DIR / "books.svg", "#38BDF8", size=14))
        )
        self.choose_button.setEnabled(self.registry is not None)
        self.choose_button.setToolTip(
            "Choose a saved key reference"
            if self.registry is not None
            else "Saved keys are available from Key Management in the main window"
        )
        self.choose_button.clicked.connect(self.choose_from_registry)
        action_row.addWidget(self.choose_button)
        layout.addLayout(action_row)

        is_public = self.role == "public"
        self.drop_zone = FileDropWidget(
            f"Drop {self.role} key here or click to browse",
            f"RSA {self.role} key ({'.pem, .der, .pub' if is_public else '.pem, .der, .key'})",
            icon_path=str(ICON_DIR / "file-text-shield.svg"),
            allowed_extensions=[".pem", ".der", ".pub" if is_public else ".key"],
        )
        self.drop_zone.setMinimumHeight(115)
        self.drop_zone.file_selected.connect(self.key_selected.emit)
        layout.addWidget(self.drop_zone)

    def choose_from_registry(self) -> None:
        dialog = KeyPickerDialog(self.registry, self.role, self)
        if dialog.exec() and dialog.selected_path:
            self.select_path(dialog.selected_path)

    def select_path(self, path: str) -> None:
        self.drop_zone.add_files([path])
