from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QTabWidget,
    QVBoxLayout, QWidget,
)

from config_prototype.gui.paths import ICON_DIR
from src.gui.components.files_drop import MultiFileDropWidget
from src.gui.components.gui_utils import (
    add_shadow_effect,
    create_icon_pixmap,
    create_icon_state,
    format_file_size,
)
from src.gui.components.key_source import KeySourceWidget
from src.gui.components.key_validation import KeyValidationLabel, inspect_public_key
from src.gui.components.password_visibility import add_password_visibility_toggle
from src.gui.components.toggle_switch import ToggleSwitch
from src.gui.components.visibility_stack import VisibilityStack
from src.gui.services.key_registry import KeyRegistry

ICON_SIZE = 14
COLOR_CHECKED_SYM = "#a78bfa"
COLOR_CHECKED_ASYM = "#34D399"
PAYLOAD_MODE_FILES = "files"
PAYLOAD_MODE_TEXT = "text"
ENCRYPTION_MODE_PASSWORD = "password"
ENCRYPTION_MODE_PUBLIC_KEY = "public_key"
PAYLOAD_TAB_FILES = 0
PAYLOAD_TAB_TEXT = 1

@dataclass
class LocomotiveInputsDraft:
    """Locomotive inputs draft for saving/loading state of the form."""

    cover_paths: list[str] = field(default_factory=list)

    payload_mode: str = PAYLOAD_MODE_FILES
    payload_paths: list[str] = field(default_factory=list)
    payload_text: str = ""

    encryption_enabled: bool = True
    encryption_mode: str = ENCRYPTION_MODE_PASSWORD
    password: str = field(default="", repr=False)
    public_key_path: str | None = None


class LocomotiveEmbedInputs(QFrame):
    """Host Locomotive inputs without depending on a page or shell variant."""

    def __init__(
        self,
        *,
        key_registry: KeyRegistry | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.key_registry = key_registry

        # Multi-file selections use empty lists when no files are selected.
        self.locomotive_file_paths: list[str] = []
        self.payload_file_paths: list[str] = []
        self.public_key_path: str | None = None

        self.build_ui()

    def build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        sub_layout = QHBoxLayout()

        # --- Left side - Locomotive file ---
        left_layout = QVBoxLayout()
        left_layout.addWidget(self.build_locomotive_file_card())

        # --- Right side - Payload and Encryption ---
        right_widget = QFrame()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.build_payload_card(), 1)
        right_layout.addWidget(self.build_encryption_card(), 0)

        right_scroll = QScrollArea()
        right_scroll.setObjectName("pageScrollArea")
        right_scroll.setWidgetResizable(True)
        right_scroll.setWidget(right_widget)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)

        sub_layout.addLayout(left_layout, 1)
        sub_layout.addWidget(right_scroll, 1)

        main_layout.addLayout(sub_layout)
        self.update_cover_summary()
        self.update_payload_file_summary()
        self.update_payload_text_summary()
        self.update_encryption_state(self.encrypt_toggle_switch.isChecked())


    def build_locomotive_file_card(self) -> QFrame:
        locomotive_file_card = QFrame()
        locomotive_file_card.setObjectName("card")
        add_shadow_effect(locomotive_file_card)

        locomotive_file_layout = QVBoxLayout(locomotive_file_card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)

        # Icon
        title_icon = QLabel()
        photo_icon = create_icon_pixmap(ICON_DIR / "photo.svg", size=16)
        title_icon.setPixmap(photo_icon)

        # Text: Locomotive File (PNG)
        title_label = QLabel("Locomotive File (PNGs)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        drop_zone = MultiFileDropWidget(
            "Drop PNG files here or click to browse",
            "PNG format only (Single file OR Multiple files)",
            str(ICON_DIR / "photo.svg"),
            allowed_extensions=[".png"]
            )

        self.cover_drop_zone = drop_zone
        drop_zone.files_changed.connect(self.on_locomotive_file_selected)

        self.cover_summary_label = QLabel()
        self.cover_summary_label.setObjectName("capacityLabel")

        locomotive_file_layout.addWidget(title_container, 0)  # top
        locomotive_file_layout.addWidget(drop_zone, 1)  # bottom
        locomotive_file_layout.addWidget(self.cover_summary_label)

        return locomotive_file_card


    def build_payload_card(self) -> QFrame:
        payload_card = QFrame()
        payload_card.setObjectName("card")
        add_shadow_effect(payload_card)

        payload_layout = QVBoxLayout(payload_card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)

        # Icon
        title_icon = QLabel()
        photo_icon = create_icon_pixmap(ICON_DIR / "file.svg", size=16)
        title_icon.setPixmap(photo_icon)

        # Text: Payload File
        title_label = QLabel("Payload File (Secret File)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.payload_tabs = QTabWidget()

        # --- File Tab ---
        file_tab = QFrame()
        file_tab_layout = QVBoxLayout(file_tab)
        file_tab_layout.setContentsMargins(0, 12, 0, 0)

        drop_zone = MultiFileDropWidget(
            "Drop any files or type text",
            "Any file format (PDF, ZIP, EXE, TXT, ...)",
            icon_path=str(ICON_DIR / "file-plus.svg"))

        self.payload_file_drop_zone = drop_zone
        drop_zone.files_changed.connect(self.on_payload_file_selected)
        file_tab_layout.addWidget(drop_zone)

        self.payload_file_summary_label = QLabel()
        self.payload_file_summary_label.setObjectName("capacityLabel")
        file_tab_layout.addWidget(self.payload_file_summary_label)

        # --- Text Tab ---
        text_input_tab = QFrame()
        text_edit_layout = QVBoxLayout(text_input_tab)
        text_edit_layout.setContentsMargins(0, 12, 0, 0)

        self.payload_text_area = QPlainTextEdit()
        self.payload_text_area.setObjectName("payloadTextArea")
        self.payload_text_area.setPlaceholderText("Enter secret message here...")
        self.payload_text_area.textChanged.connect(
            self.update_payload_text_summary
        )
        text_edit_layout.addWidget(self.payload_text_area)

        # Locomotive appends its payload after PNG data, so this is a size
        # summary rather than a cover-capacity calculation.
        self.capacity_label = QLabel("Size: 0.0 B")
        self.capacity_label.setObjectName("capacityLabel")

        text_edit_layout.addWidget(self.capacity_label)

        self.payload_tabs.addTab(file_tab, "File Input")
        self.payload_tabs.addTab(text_input_tab, "Text Input")

        payload_layout.addWidget(title_container)
        payload_layout.addWidget(self.payload_tabs)

        return payload_card


    def build_encryption_card(self) -> QFrame:
        encryption_card = QFrame()
        encryption_card.setObjectName("card")
        add_shadow_effect(encryption_card)

        encryption_layout = QVBoxLayout(encryption_card)
        encryption_layout.setContentsMargins(11, 11, 11, 2)
        encryption_layout.setSpacing(6)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)

        # Toggle Switch
        self.encrypt_toggle_switch = ToggleSwitch()
        self.encrypt_toggle_switch.setChecked(True)
        title_layout.addWidget(self.encrypt_toggle_switch)

        # Icon
        title_icon = QLabel()
        photo_icon = create_icon_pixmap(ICON_DIR / "shield-lock.svg", "#a78bfa", size=16)
        title_icon.setPixmap(photo_icon)

        # Text: Encryption Options
        title_label = QLabel("Encryption Options")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        encrypt_selection = self.build_encrypt_selection()

        # Encryption Mode Stack
        self.encrypt_stack = VisibilityStack()

        # Add encryption modes to stack
        self.encrypt_stack.addWidget(self.build_symmetric_mode())
        self.encrypt_stack.addWidget(self.build_asymmetric_mode())

        # Connect toggle switch to stack
        self.encrypt_group.idClicked.connect(self.encrypt_stack.setCurrentIndex)
        self.encrypt_toggle_switch.toggled.connect(self.update_encryption_state)

        title_layout.addWidget(encrypt_selection)
        encryption_layout.addWidget(title_container)
        encryption_layout.addWidget(self.encrypt_stack)

        return encryption_card


    def build_encrypt_selection(self) -> QFrame:
        encrypt_selection = QFrame()
        encrypt_selection.setObjectName("encryptSelectionContainer")

        encrypt_layout = QHBoxLayout(encrypt_selection)
        encrypt_layout.setContentsMargins(3, 3, 3, 3)
        encrypt_layout.setSpacing(3)

        # --- SYMMETRIC MODE BUTTON ---
        self.btn_symmetric = QPushButton("Password")
        self.btn_symmetric.setObjectName("encryptOptionBtn")
        self.btn_symmetric.setProperty("accentColor", "purple")
        self.btn_symmetric.setCheckable(True)
        self.btn_symmetric.setCursor(Qt.CursorShape.PointingHandCursor)

        # ADD ICON
        symmetric_icon_path = ICON_DIR / "key.svg"
        if symmetric_icon_path.exists():
            symmetric_icon = create_icon_state(str(symmetric_icon_path), ICON_SIZE, color_checked=COLOR_CHECKED_SYM)
            self.btn_symmetric.setIcon(symmetric_icon)
            self.btn_symmetric.setIconSize(QSize(ICON_SIZE, ICON_SIZE))

        # --- ASYMMETRIC MODE BUTTON ---
        self.btn_asymmetric = QPushButton("Public Key")
        self.btn_asymmetric.setObjectName("encryptOptionBtn")
        self.btn_asymmetric.setProperty("accentColor", "green")
        self.btn_asymmetric.setCheckable(True)
        self.btn_asymmetric.setCursor(Qt.CursorShape.PointingHandCursor)

        # ADD ICON
        asymmetric_icon_path = ICON_DIR / "lock.svg"
        if asymmetric_icon_path.exists():
            asymmetric_icon = create_icon_state(str(asymmetric_icon_path), ICON_SIZE, color_checked=COLOR_CHECKED_ASYM)
            self.btn_asymmetric.setIcon(asymmetric_icon)
            self.btn_asymmetric.setIconSize(QSize(ICON_SIZE, ICON_SIZE))

        encrypt_layout.addWidget(self.btn_symmetric)
        encrypt_layout.addWidget(self.btn_asymmetric)

        # --- BUTTON GROUP ---
        self.encrypt_group = QButtonGroup()
        self.encrypt_group.setExclusive(True)
        self.encrypt_group.addButton(self.btn_symmetric, 0)
        self.encrypt_group.addButton(self.btn_asymmetric, 1)

        # Set default selection
        self.btn_symmetric.setChecked(True)

        return encrypt_selection


    def build_symmetric_mode(self) -> QFrame:
        symmetric_mode = QFrame()
        symmetric_mode.setObjectName("symmetricMode")

        symmetric_layout = QVBoxLayout(symmetric_mode)
        symmetric_layout.setContentsMargins(0, 0, 0, 8)

        # --- Password Input ---
        password_label = QLabel("Password")
        password_label.setContentsMargins(0, 0, 0, 0)
        password_label.setObjectName("formLabel")

        self.password_input = QLineEdit()
        self.password_input.setObjectName("formInput")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter passphrase...")

        symmetric_layout.addWidget(password_label)
        symmetric_layout.addWidget(self.password_input)

        # --- Confirm Password Input ---
        confirm_label = QLabel("Confirm Password")
        confirm_label.setContentsMargins(0, 0, 0, 0)
        confirm_label.setObjectName("formLabel")

        self.confirm_input = QLineEdit()
        self.confirm_input.setObjectName("formInput")
        self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        add_password_visibility_toggle(self.password_input, self.confirm_input)
        self.confirm_input.setPlaceholderText("Confirm your passphrase...")

        symmetric_layout.addWidget(confirm_label)
        symmetric_layout.addWidget(self.confirm_input)

        return symmetric_mode

    def build_asymmetric_mode(self) -> QFrame:
        asymmetric_mode = QFrame()
        asymmetric_mode.setObjectName("asymmetricMode")

        asymmetric_layout = QVBoxLayout(asymmetric_mode)
        asymmetric_layout.setContentsMargins(0, 0, 0, 8)
        self.public_key_source = KeySourceWidget("public", self.key_registry)
        self.public_key_drop_zone = self.public_key_source.drop_zone
        self.public_key_source.key_selected.connect(self.on_public_key_selected)
        asymmetric_layout.addWidget(self.public_key_source)

        self.public_key_status = KeyValidationLabel()
        asymmetric_layout.addWidget(self.public_key_status)

        return asymmetric_mode

    # --- Draft API ---
    def load_draft(self, draft: LocomotiveInputsDraft) -> None:
        """Replace the visible form state with values from ``draft``."""
        cover_paths = [
            path
            for path in draft.cover_paths
            if self._is_available_png(path)
        ]
        self.cover_drop_zone.clear_all()
        if cover_paths:
            self.cover_drop_zone.add_files(cover_paths)

        if draft.payload_mode == PAYLOAD_MODE_TEXT:
            self.payload_tabs.setCurrentIndex(PAYLOAD_TAB_TEXT)
            self.payload_file_drop_zone.clear_all()
            self.payload_text_area.setPlainText(draft.payload_text)
        else:
            payload_paths = [
                path
                for path in draft.payload_paths
                if Path(path).is_file()
            ]
            self.payload_tabs.setCurrentIndex(PAYLOAD_TAB_FILES)
            self.payload_text_area.clear()
            self.payload_file_drop_zone.clear_all()
            if payload_paths:
                self.payload_file_drop_zone.add_files(payload_paths)

        self.encrypt_toggle_switch.setChecked(draft.encryption_enabled)

        if draft.encryption_mode == ENCRYPTION_MODE_PUBLIC_KEY:
            self.btn_asymmetric.setChecked(True)
            self.encrypt_stack.setCurrentIndex(1)
        else:
            self.btn_symmetric.setChecked(True)
            self.encrypt_stack.setCurrentIndex(0)

        password = (
            draft.password
            if draft.encryption_enabled
            and draft.encryption_mode == ENCRYPTION_MODE_PASSWORD
            else ""
        )
        self.password_input.setText(password)
        self.confirm_input.setText(password)

        self.public_key_drop_zone.clear_all()
        public_key_path = draft.public_key_path
        if (
            draft.encryption_enabled
            and draft.encryption_mode == ENCRYPTION_MODE_PUBLIC_KEY
            and public_key_path
            and Path(public_key_path).is_file()
        ):
            self.public_key_drop_zone.add_files([public_key_path])

    def validate_draft(self) -> bool:
        """Validate the current manual Locomotive inputs before saving."""
        if not self.locomotive_file_paths:
            return self.show_validation_warning(
                "Please select at least one PNG cover image."
            )

        if not all(
            self._is_available_png(path)
            for path in self.locomotive_file_paths
        ):
            return self.show_validation_warning(
                "One or more PNG cover images are no longer available."
            )

        if self.payload_tabs.currentIndex() == PAYLOAD_TAB_FILES:
            if not self.payload_file_paths:
                return self.show_validation_warning(
                    "Please select at least one payload file."
                )
            if not all(Path(path).is_file() for path in self.payload_file_paths):
                return self.show_validation_warning(
                    "One or more payload files are no longer available."
                )
        elif not self.payload_text_area.toPlainText().strip():
            self.payload_text_area.setFocus()
            return self.show_validation_warning(
                "Please enter a secret message."
            )

        if not self.encrypt_toggle_switch.isChecked():
            return True

        if self.btn_symmetric.isChecked():
            password = self.password_input.text()
            if not password:
                self.password_input.setFocus()
                return self.show_validation_warning(
                    "Please enter a password for encryption."
                )
            if password != self.confirm_input.text():
                self.confirm_input.setFocus()
                return self.show_validation_warning(
                    "Passwords do not match. Please confirm your passphrase."
                )
            return True

        if self.btn_asymmetric.isChecked():
            public_key_path = self.public_key_path
            if not public_key_path or not Path(public_key_path).is_file():
                return self.show_validation_warning(
                    "Please select an available public key for encryption."
                )

            result = inspect_public_key(public_key_path)
            self.public_key_status.set_result(result)
            if not result.valid:
                return self.show_validation_warning(
                    result.message,
                    title="Invalid Public Key",
                )
            return True

        return self.show_validation_warning(
            "Please select an encryption mode."
        )

    def export_draft(self) -> LocomotiveInputsDraft:
        """Return a canonical draft containing only the active input modes."""
        payload_mode = (
            PAYLOAD_MODE_TEXT
            if self.payload_tabs.currentIndex() == PAYLOAD_TAB_TEXT
            else PAYLOAD_MODE_FILES
        )
        encryption_enabled = self.encrypt_toggle_switch.isChecked()
        encryption_mode = (
            ENCRYPTION_MODE_PUBLIC_KEY
            if self.btn_asymmetric.isChecked()
            else ENCRYPTION_MODE_PASSWORD
        )

        return LocomotiveInputsDraft(
            cover_paths=list(self.locomotive_file_paths),
            payload_mode=payload_mode,
            payload_paths=(
                list(self.payload_file_paths)
                if payload_mode == PAYLOAD_MODE_FILES
                else []
            ),
            payload_text=(
                self.payload_text_area.toPlainText()
                if payload_mode == PAYLOAD_MODE_TEXT
                else ""
            ),
            encryption_enabled=encryption_enabled,
            encryption_mode=encryption_mode,
            password=(
                self.password_input.text()
                if encryption_enabled
                and encryption_mode == ENCRYPTION_MODE_PASSWORD
                else ""
            ),
            public_key_path=(
                self.public_key_path
                if encryption_enabled
                and encryption_mode == ENCRYPTION_MODE_PUBLIC_KEY
                else None
            ),
        )

    def show_validation_warning(
        self,
        message: str,
        *,
        title: str = "Validation Error",
    ) -> bool:
        QMessageBox.warning(self, title, message)
        return False

    @staticmethod
    def _is_available_png(file_path: str) -> bool:
        path = Path(file_path)
        return path.is_file() and path.suffix.lower() == ".png"

    def update_cover_summary(self) -> None:
        count = len(self.locomotive_file_paths)
        noun = "PNG" if count == 1 else "PNGs"
        self.cover_summary_label.setText(f"Selected: {count} {noun}")

    def update_payload_file_summary(self) -> None:
        count = len(self.payload_file_paths)
        total_bytes = 0
        available_count = 0

        for file_path in self.payload_file_paths:
            try:
                total_bytes += Path(file_path).stat().st_size
                available_count += 1
            except OSError:
                continue

        summary = f"Files: {count} · Total: {format_file_size(total_bytes)}"
        if available_count != count:
            summary += f" · Available: {available_count}"
        self.payload_file_summary_label.setText(summary)

    def update_payload_text_summary(self) -> None:
        text_size = len(self.payload_text_area.toPlainText().encode("utf-8"))
        self.capacity_label.setText(f"Size: {format_file_size(text_size)}")

    def update_encryption_state(self, enabled: bool) -> None:
        """Keep the chosen mode while making the disabled state unambiguous."""
        self.encrypt_stack.setVisible(enabled)
        for button in (self.btn_symmetric, self.btn_asymmetric):
            button.setEnabled(enabled)
            button.setProperty("encryptionActive", enabled)
            button.style().unpolish(button)
            button.style().polish(button)


    # --- Event Handlers ---
    def on_locomotive_file_selected(self, file_paths: list[str]) -> None:
        """Handle locomotive file selection"""
        self.locomotive_file_paths = list(file_paths)
        self.update_cover_summary()

    def on_payload_file_selected(self, file_paths: list[str]) -> None:
        """Handle payload file selection"""
        self.payload_file_paths = list(file_paths)
        self.update_payload_file_summary()

    def on_public_key_selected(self, file_path: str) -> None:
        """Handle public key selection"""
        if not file_path:
            self.public_key_path = None
            self.public_key_status.clear_result()
            return

        result = inspect_public_key(file_path)
        self.public_key_status.set_result(result)
        self.public_key_path = file_path
