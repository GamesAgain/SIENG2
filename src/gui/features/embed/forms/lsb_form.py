from pathlib import Path

from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, 
    QLineEdit, QMessageBox, QPlainTextEdit, QScrollArea, 
    QStackedWidget, QTabWidget, QVBoxLayout)
from PyQt6.QtCore import pyqtSignal

from src.core.configurable.drafts import LSBInputsDraft
from src.core.crypto.sym_encrypt import AES_NONCE_LENGTH, AES_SALT_LENGTH, AES_TAG_LENGTH
from src.core.stego.lsb_pp import ALLOWED_IMAGE_EXTENSIONS, HEADER_BYTES, LSBPP, estimate_overhead_bytes, get_max_message_bytes
from src.gui.components.gui_utils import add_password_visibility_toggle, add_shadow_effect, create_icon_pixmap, format_file_size
from src.gui.components.widgets.files_drop import FileDropWidget
from src.gui.components.widgets.key_source import KeySourceWidget
from src.gui.components.widgets.key_validation import KeyValidationLabel, inspect_public_key
from src.gui.components.widgets.selection_toggle import SelectionToggle
from src.gui.components.widgets.toggle_switch import ToggleSwitch
from src.gui.components.widgets.visibility_stack import VisibilityStack
from src.gui.services.key_registry import KeyRegistry
from src.gui.services.worker import FunctionWorker
from src.path import svg_path

ICON_SIZE = 16
COLOR_CHECKED_SYM = "#a78bfa"
COLOR_CHECKED_ASYM = "#34D399"
CAPACITY_WARNING_RATIO = 0.90

class LSBInputForm(QFrame):
    
    draft_status = pyqtSignal(bool)
    
    def __init__(self, key_registry: KeyRegistry = None, is_config: bool = False, parent = None):
        super().__init__(parent)
        
        self.key_registry = key_registry
        self.is_config = is_config
        
        # setup inputs
        self.cover_file_path = None
        self.public_key_path = None
        
        # setup cal capacity 
        self.capacity_bits: int = None  # ผล analyze ภาพ (Sobel+entropy) แคชไว้เพราะหนัก ไม่คำนวณซ้ำทุกครั้งที่พิมพ์/สลับโหมด
        self.is_calculating = False
        self.capacity_request = 0 # กันไม่ให้ผลลัพธ์ capacity แสดงผลผิดภาพ
        self.capacity_workers = {}
    
        self.setup_ui()
        
    # --- UI construction ---
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 11, 0, 0)

        sub_layout = QHBoxLayout()

        # --- Left side - Cover file Card ---
        left_layout = QVBoxLayout()
        left_layout.addWidget(self.build_cover_file_card())

        # --- Right side - Payload and Encryption Cards ---
        right_widget = QFrame()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.build_payload_card(), 1)
        right_layout.addWidget(self.build_encryption_card())
        
        # Make right side scrollable
        right_scroll = QScrollArea()
        right_scroll.setObjectName("transparentScroll")
        right_scroll.setWidgetResizable(True)
        right_scroll.setWidget(right_widget)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        # Left:Right is 1:1 ratio
        sub_layout.addLayout(left_layout, 1)
        sub_layout.addWidget(right_scroll, 1)

        main_layout.addLayout(sub_layout)
    
    def build_cover_file_card(self):
        cover_file_card = QFrame()
        cover_file_card.setObjectName("card")
        add_shadow_effect(cover_file_card)

        cover_file_layout = QVBoxLayout(cover_file_card)
        cover_file_layout.setContentsMargins(10, 10, 10, 10)

        title_container = QFrame()
        title_layout = QHBoxLayout(title_container)

        # Icon
        title_icon = QLabel()
        photo_icon = create_icon_pixmap(svg_path("photo.svg"), size=ICON_SIZE)
        title_icon.setPixmap(photo_icon)

        # Text: Cover File (PNG)
        title_label = QLabel("Cover File (PNG)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.cover_mode_toggle = SelectionToggle(
            [
                { 
                    "text": "Manual File",
                    "value": "manual",
                    "variant": "source",
                },
                {
                    "text": "Previous Output",
                    "value": "previous",
                    "variant": "source",
                },
            ])
        
        self.cover_mode_toggle.mode_changed.connect(self.on_cover_mode_changed)
        
        drop_zone = FileDropWidget(
            text="Drop cover image here or click to browse",
            sub_text="Supports PNG, JPEG, WebP and other image formats",
            icon_path=str(svg_path("photo.svg")),
            allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
        )
        
        self.cover_drop_zone = drop_zone
        drop_zone.file_selected.connect(self.on_cover_file_selected)

        self.cover_source_stack = QStackedWidget()
        self.cover_source_stack.addWidget(drop_zone)
        self.output_picker = QLabel("Previous Output List") #TODO
        self.cover_source_stack.addWidget(self.output_picker)
        # self.output_picker.selection_changed.connect(self.on_cover_output_selected) #TODO

        cover_file_layout.addWidget(title_container)
        cover_file_layout.addWidget(self.cover_mode_toggle)
        self.cover_mode_toggle.setVisible(self.is_config) # Standalone: hidden, Configurable: shown
        cover_file_layout.addWidget(self.cover_source_stack, 1)

        return cover_file_card
        
    def build_payload_card(self):
        payload_card = QFrame()
        payload_card.setObjectName("card")
        add_shadow_effect(payload_card)

        payload_layout = QVBoxLayout(payload_card)

        title_container = QFrame()
        title_layout = QHBoxLayout(title_container)

        # Icon
        title_icon = QLabel()
        message_icon = create_icon_pixmap(svg_path("message.svg"), size=ICON_SIZE)
        title_icon.setPixmap(message_icon)

        # Text: Payload (Secret Message)
        title_label = QLabel("Payload (Secret Message)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.payload_tabs = QTabWidget()
        self.payload_tabs.setObjectName("siengTabs")

        text_input_tab = QFrame()
        text_edit_layout = QVBoxLayout(text_input_tab)
        text_edit_layout.setContentsMargins(0, 12, 0, 0)

        self.payload_text_area = QPlainTextEdit()
        self.payload_text_area.textChanged.connect(self.on_payload_text_changed)

        self.payload_text_area.setObjectName("payloadTextArea")
        self.payload_text_area.setPlaceholderText("Enter secret message here...")
        text_edit_layout.addWidget(self.payload_text_area)

        # Capacity indicator
        self.capacity_label = QLabel("Size: 0.0 B")
        self.capacity_label.setObjectName("capacityLabel")

        text_edit_layout.addWidget(self.capacity_label)

        text_file_tab = QFrame()
        text_file_layout = QVBoxLayout(text_file_tab)
        text_file_layout.setContentsMargins(0, 12, 0, 0)
        
        # File drop zone
        drop_zone = FileDropWidget(
            text="Drop text file here or click to browse", 
            sub_text="Supported: .txt", 
            icon_path=str(svg_path("file-text.svg")), 
            allowed_extensions=["txt"])
        
        self.payload_file_drop_zone = drop_zone
        drop_zone.file_selected.connect(self.on_payload_file_selected)
        drop_zone.setMinimumHeight(115)
        text_file_layout.addWidget(drop_zone)

        self.payload_tabs.addTab(text_input_tab, "Text Input")
        self.payload_tabs.addTab(text_file_tab, "Text File")

        payload_layout.addWidget(title_container)
        payload_layout.addWidget(self.payload_tabs)

        return payload_card
    
    def build_encryption_card(self):
        encryption_card = QFrame()
        encryption_card.setObjectName("card")
        add_shadow_effect(encryption_card)

        encryption_layout = QVBoxLayout(encryption_card)
        encryption_layout.setContentsMargins(11, 11, 11, 2)
        encryption_layout.setSpacing(6)

        title_container = QFrame()
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)
        
        # Toggle Switch
        self.encrypt_toggle_switch = ToggleSwitch()
        self.encrypt_toggle_switch.setChecked(True)
        title_layout.addWidget(self.encrypt_toggle_switch)

        # Icon
        title_icon = QLabel()
        shield_icon = create_icon_pixmap(svg_path("shield-lock.svg"), "#a78bfa", ICON_SIZE)
        title_icon.setPixmap(shield_icon)

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
        self.encrypt_mode_toggle.mode_changed.connect(self.on_encrypt_mode_changed)
        self.encrypt_toggle_switch.toggled.connect(self.encrypt_stack.setVisible)
        
        # update draft status and capacity label
        self.encrypt_toggle_switch.toggled.connect(self.update_draft_status)
        self.encrypt_toggle_switch.toggled.connect(self.update_capacity_label)

        title_layout.addWidget(encrypt_selection)
        encryption_layout.addWidget(title_container)
        encryption_layout.addWidget(self.encrypt_stack)

        return encryption_card
    
    def build_encrypt_selection(self):
        self.encrypt_mode_toggle = SelectionToggle([
            {
                "text": "Password",
                "value": "password",
                "variant": "password",
                "color_checked": COLOR_CHECKED_SYM,
                "icon_path": svg_path("key.svg"),
                "icon_size": 14,
            },
            {
                "text": "Public Key",
                "value": "public_key",
                "variant": "public_key",
                "color_checked": COLOR_CHECKED_ASYM,
                "icon_path": svg_path("lock.svg"),
                "icon_size": 14,
            },
        ])
        self.encrypt_mode_toggle.setProperty("variant", "encryption")
        return self.encrypt_mode_toggle
    
    def build_symmetric_mode(self):
        symmetric_mode = QFrame()

        symmetric_layout = QVBoxLayout(symmetric_mode)
        symmetric_layout.setContentsMargins(0, 0, 0, 8)

        # Password Input
        password_label = QLabel("Password")
        password_label.setObjectName("formLabel")

        self.password_input = QLineEdit()
        self.password_input.setObjectName("formInput")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter passphrase...")

        symmetric_layout.addWidget(password_label)
        symmetric_layout.addWidget(self.password_input)

        # Confirm Password Input
        confirm_label = QLabel("Confirm Password")
        confirm_label.setObjectName("formLabel")

        self.confirm_input = QLineEdit()
        self.confirm_input.setObjectName("formInput")
        self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        add_password_visibility_toggle(self.password_input, self.confirm_input)
        self.confirm_input.setPlaceholderText("Confirm your passphrase...")

        symmetric_layout.addWidget(confirm_label)
        symmetric_layout.addWidget(self.confirm_input)
        
        self.password_input.textChanged.connect(self.update_draft_status)
        self.password_input.textChanged.connect(self.update_capacity_label)

        self.confirm_input.textChanged.connect(self.update_draft_status)

        return symmetric_mode
    
    def build_asymmetric_mode(self):
        asymmetric_mode = QFrame()
        asymmetric_layout = QVBoxLayout(asymmetric_mode)
        asymmetric_layout.setContentsMargins(0, 0, 0, 8)

        self.public_key_source = KeySourceWidget("public", self.key_registry)
        asymmetric_layout.addWidget(self.public_key_source)

        self.public_key_status = KeyValidationLabel()
        asymmetric_layout.addWidget(self.public_key_status)
        self.public_key_source.key_selected.connect(self.on_public_key_selected)
        return asymmetric_mode
    
    # --- Input validation and draft status ---
    def validate_inputs(self, draft: LSBInputsDraft):
        if not draft.cover:
            raise ValueError("Please select a cover image.")

        if not draft.payload_text.strip():
            raise ValueError("Please enter a payload message or upload a text file.")

        if draft.encryption_enabled:
            if draft.encryption_mode == "password":
                if not draft.password:
                    raise ValueError("Please enter a password.")

                if not self.confirm_input.text():
                    raise ValueError("Please confirm your password.")

                if draft.password != self.confirm_input.text():
                    raise ValueError("Password and confirmation do not match.")

            elif draft.encryption_mode == "public_key":
                if not draft.public_key_path:
                    raise ValueError("Please select a valid public key.")
            else:
                raise ValueError("Unsupported encryption mode.")

        # Capacity
        if self.is_calculating:
            raise ValueError("Please wait for cover capacity calculation.")

        if self.capacity_bits is None:
            raise ValueError("Could not calculate cover capacity.")
        
    def get_inputs(self) -> LSBInputsDraft:
        """Read the form state and raise ValueError if it cannot be embedded."""
        draft = LSBInputsDraft(
            cover=self.cover_file_path,
            payload_text=self.payload_text_area.toPlainText(),
            encryption_enabled=self.encrypt_toggle_switch.isChecked(),
            encryption_mode=self.encrypt_mode_toggle.mode(),
            password=self.password_input.text(),
            public_key_path=self.public_key_path,
        )
        self.validate_inputs(draft)
        return draft

    def load_draft(self, draft: LSBInputsDraft) -> None:
        """Fill the form from a saved draft (the reverse of get_inputs)."""
        # 1. Clear the previous cover (emits file_selected("") -> capacity is reset)
        self.cover_mode_toggle.set_mode("manual")
        self.cover_source_stack.setCurrentIndex(0)
        self.cover_drop_zone.clear_all()

        # 2. Message
        self.payload_text_area.setPlainText(draft.payload_text)
        self.payload_tabs.setCurrentIndex(0)

        # 3. Encryption: values of the inactive mode are restored too
        self.encrypt_mode_toggle.set_mode(draft.encryption_mode)
        self.on_encrypt_mode_changed(draft.encryption_mode)  # set_mode does not emit mode_changed
        self.encrypt_toggle_switch.setChecked(draft.encryption_enabled)
        self.encrypt_stack.setVisible(draft.encryption_enabled)  # setChecked emits nothing when the value is unchanged
        self.password_input.setText(draft.password)
        self.confirm_input.setText(draft.password)  # the draft keeps one password (it matched when it was saved)

        # public key: select_path -> key_selected -> on_public_key_selected validates it and sets public_key_path
        self.public_key_source.drop_zone.clear_all()
        if draft.public_key_path and Path(draft.public_key_path).is_file():
            self.public_key_source.select_path(draft.public_key_path)

        # 4. Cover last: add_files -> file_selected -> capacity worker (needs the encryption values above)
        # TODO(configurable): draft.cover may be a previous step's output instead of a file path
        if draft.cover and Path(draft.cover).is_file():
            self.cover_drop_zone.add_files([draft.cover])

        # 5. A missing cover/key stays empty (the draft is not changed); refresh the status once
        self.update_capacity_label()
        self.update_draft_status()

    def is_draft_ready(self) -> bool:
        try:
            self.get_inputs()
        except ValueError:
            return False
        return True
    
    def update_draft_status(self):
        self.draft_status.emit(self.is_draft_ready())
    
    # --- Capacity estimation and display ---
    def set_capacity_state(self, state: str):
        """state: 'normal' | 'warning' | 'danger' ผูกกับ QSS ผ่าน property"""
        self.capacity_label.setProperty("capacityState", state)
        self.capacity_label.style().unpolish(self.capacity_label)
        self.capacity_label.style().polish(self.capacity_label)
        
    def calculate_capacity(self) -> tuple[int, int, str]:
        """Calculate overhead and maximum bytes without changing the label."""
        password = None
        public_key_path = None
        overhead_detail = "no encryption (header only)"

        if self.encrypt_toggle_switch.isChecked():
            mode = self.encrypt_mode_toggle.mode()
            if mode == "password":
                password = self.password_input.text()
                overhead_detail = (
                    f"password mode: salt {AES_SALT_LENGTH}B + "
                    f"nonce {AES_NONCE_LENGTH}B + tag {AES_TAG_LENGTH}B"
                )
            elif mode == "public_key":
                public_key_path = self.public_key_path
                overhead_detail = (
                    "public key mode: RSA-encrypted session key + "
                    f"nonce {AES_NONCE_LENGTH}B + tag {AES_TAG_LENGTH}B"
                )

        overhead_bytes = estimate_overhead_bytes(password, public_key_path)
        max_bytes = get_max_message_bytes(self.capacity_bits, password, public_key_path)
        return overhead_bytes, max_bytes, overhead_detail
    
    def update_capacity_label(self):
        """Show capacity status, usage colour and the explanatory tooltip."""

        text_size_bytes = len(self.payload_text_area.toPlainText().encode("utf-8"))
        text_size = format_file_size(text_size_bytes)

        if self.is_calculating:
            self.capacity_label.setText("Calculating...")
            self.capacity_label.setToolTip("Calculating cover capacity...")
            self.set_capacity_state("normal")
            return

        if self.capacity_bits is None:
            self.capacity_label.setText(f"Size: {text_size}")
            self.capacity_label.setToolTip("Select a cover image to calculate capacity.")
            self.set_capacity_state("normal")
            return

        # Public Key mode without a valid key: overhead is unknown, so max is not shown.
        no_key_yet = (
            self.encrypt_toggle_switch.isChecked()
            and self.encrypt_mode_toggle.mode() == "public_key"
            and not self.public_key_path
        )
        if no_key_yet:
            self.capacity_label.setText(f"Size: {text_size}")
            self.capacity_label.setToolTip("Select a public key to see max capacity.")
            self.set_capacity_state("normal")
            return

        try:
            overhead_bytes, max_bytes, overhead_detail = self.calculate_capacity()
        except Exception:
            self.capacity_label.setText(f"Size: {text_size} / Invalid Key")
            self.capacity_label.setToolTip("Could not read the public key to estimate capacity.")
            self.set_capacity_state("warning")
            return

        self.capacity_label.setText(f"Size: {text_size} / {format_file_size(max_bytes)}")

        usage_ratio = (text_size_bytes / max_bytes if max_bytes > 0 else 1.0)

        if text_size_bytes > max_bytes:
            self.set_capacity_state("danger")
        elif usage_ratio > CAPACITY_WARNING_RATIO:
            self.set_capacity_state("warning")
        else:
            self.set_capacity_state("normal")

        self.capacity_label.setToolTip(
            f"Cover raw capacity: {format_file_size(self.capacity_bits // 8)} ({self.capacity_bits} bits)\n"
            f"Overhead: {format_file_size(overhead_bytes)} (header {HEADER_BYTES}B + {overhead_detail})\n"
            f"Max message size: {format_file_size(max_bytes)}\n"
            f"Current usage: {text_size} ({usage_ratio:.0%})"
        )
        
    # --- Event handlers ---
    def on_cover_file_selected(self, file_path: str):
        # เปลี่ยนหรือล้างไฟล์ทุกครั้ง ต้องทำให้ผลของ worker เก่าเป็นโมฆะก่อน
        self.capacity_request += 1
        request = self.capacity_request

        self.cover_file_path = file_path or None
        self.capacity_bits = None
        self.is_calculating = bool(file_path)

        self.update_capacity_label()
        self.update_draft_status()

        if not file_path:
            return

        worker = FunctionWorker(LSBPP().get_total_capacity_bits, file_path)
        self.capacity_workers[request] = worker
        worker.done.connect(lambda result: self.on_cal_capacity_done(result, request))
        worker.finished.connect(lambda: self.release_capacity_worker(request))
        worker.start()
        
    def on_cover_mode_changed(self, mode: str):
        index = 0 if mode == "manual" else 1
        self.cover_source_stack.setCurrentIndex(index)
    
    def on_cal_capacity_done(self, result, request: int):
        if request != self.capacity_request:
            return

        self.is_calculating = False

        if isinstance(result, int):
            self.capacity_bits = result
            self.update_capacity_label()
        else:
            self.capacity_bits = None
            self.update_capacity_label()

            error = "Invalid capacity result"
            if isinstance(result, dict):
                error = result.get("error", error)

            self.capacity_label.setToolTip(
                f"Could not calculate cover capacity: {error}"
            )
            self.set_capacity_state("warning")

        self.update_draft_status()
                    
    def release_capacity_worker(self, request: int):
        worker = self.capacity_workers.pop(request, None)
        if worker is not None:
            worker.deleteLater()
        
        
    def on_payload_file_selected(self, file_path: str):
        if not file_path:
            return  # Clearing the selected file preserves the editable text.
        error = None
        for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp874"):
            try:
                text = Path(file_path).read_text(encoding=encoding)
            except UnicodeError as exc:
                error = exc
                continue
            except OSError as exc:
                error = exc
                break
            self.payload_text_area.setPlainText(text)
            self.payload_tabs.setCurrentIndex(0)
            return
        self.payload_text_area.clear()
        self.payload_tabs.setCurrentIndex(1)
        QMessageBox.warning(self, "Cannot read text file", str(error))
        
    def on_payload_text_changed(self):
        self.update_capacity_label()
        self.update_draft_status()
    
    def on_encrypt_mode_changed(self, mode: str):
        self.encrypt_stack.setCurrentIndex(0 if mode == "password" else 1)
        self.update_capacity_label()
        self.update_draft_status()
        
    def on_public_key_selected(self, file_path: str):
        self.public_key_path = None
        if file_path:
            result = inspect_public_key(file_path)
            self.public_key_status.set_result(result)
            if result.valid:
                self.public_key_path = file_path
        else:
            self.public_key_status.clear_result()
        
        self.update_capacity_label()    
        self.update_draft_status()