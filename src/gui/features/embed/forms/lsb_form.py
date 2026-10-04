from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, 
    QLineEdit, QMessageBox, QPlainTextEdit, 
    QScrollArea, QStackedWidget, QTabWidget, QVBoxLayout)

from src.core.configurable.step_output import FileSource, StepOutput
from src.core.crypto.sym_encrypt import AES_NONCE_LENGTH, AES_SALT_LENGTH, AES_TAG_LENGTH
from src.core.stego.lsb_pp import HEADER_BYTES, LSBPP, estimate_overhead_bytes, get_max_message_bytes
from src.gui.components.gui_utils import (
    add_password_visibility_toggle, 
    add_shadow_effect, 
    create_icon_pixmap, 
    format_file_size)

from src.gui.components.widgets.files_drop import FileDropWidget
from src.gui.components.widgets.key_source import KeySourceWidget
from src.gui.components.widgets.key_validation import KeyValidationLabel, inspect_public_key
from src.gui.components.widgets.selection_toggle import SelectionToggle
from src.gui.components.widgets.toggle_switch import ToggleSwitch
from src.gui.components.widgets.visibility_stack import VisibilityStack
from src.gui.services.key_registry import KeyRegistry
from src.gui.services.worker import FunctionWorker
from src.path import svg_path

# Declare allowed image file format
ALLOWED_EXTS = [
    # 1. กลุ่มที่คนใช้งานเยอะที่สุด (ภาพพื้นใส / ภาพถ่าย / ภาพบนเว็บ)
    ".png", 
    ".jpg", ".jpeg", ".webp",
    
    # 2. กลุ่มนามสกุลย่อยของ JPEG (เจอบ่อยเวลาเซฟรูปจากอินเทอร์เน็ต / Twitter / Facebook)
    ".jpe", ".jfif", 
    
    # 3. กลุ่มภาพมาตรฐานระบบ Windows และงานสแกนเอกสาร/งานพิมพ์
    ".bmp", 
    ".tiff", ".tif", 
    
    # 4. กลุ่มไอคอนมาตรฐาน
    ".ico"
]

ICON_SIZE = 16
COLOR_CHECKED_SYM = "#a78bfa"
COLOR_CHECKED_ASYM = "#34D399"
CAPACITY_WARNING_RATIO = 0.90

@dataclass
class LSBInputsDraft:
    "LSB++ inputs draft for saving/loading state of the form."
    cover: FileSource | None = None
    payload_text: str = ""
    encryption_enabled: bool = True
    encryption_mode: str = "password"
    password: str = field(default="", repr=False)
    public_key_path: str | None = None
    

class LSBInputForm(QFrame):
    
    def __init__(self, key_registry: KeyRegistry = None, is_config: bool = False, parent = None):
        super().__init__(parent)
        
        self.key_registry = key_registry
        self.is_config = is_config
        
        # Cover & Payload
        self.cover_source: FileSource = None
        self.payload_file_path: str = None
        self.capacity_bits: int = None  # ผล analyze ภาพ (Sobel+entropy) แคชไว้เพราะหนัก ไม่คำนวณซ้ำทุกครั้งที่พิมพ์/สลับโหมด
        self.isCalculating = False
        self.capacity_request = 0
        self.capacity_workers = {}
        
        # Encryption
        self.public_key_path: str | None = None
        
        self.setup_ui()
        
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 11, 0, 0)

        sub_layout = QHBoxLayout()

        # --- Left side - Cover file ---
        left_layout = QVBoxLayout()
        left_layout.addWidget(self.build_cover_file_card())

        # --- Right side - Payload and Encryption ---
        right_widget = QFrame()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.build_payload_card(), 1)
        right_layout.addWidget(self.build_encryption_card(), 0)

        right_scroll = QScrollArea()
        right_scroll.setObjectName("transparentScroll")
        right_scroll.setWidgetResizable(True)
        right_scroll.setWidget(right_widget)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)

        sub_layout.addLayout(left_layout, 1)
        sub_layout.addWidget(right_scroll, 1)

        main_layout.addLayout(sub_layout)

        self.update_capacity_label()  # เซ็ตข้อความเริ่มต้นให้ตรง state จริง (ยังไม่มี cover)
        
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
                    "value": "Manual",
                    "variant": "source",
                    "color_checked": "#38BDF8",
                },
                {
                    "text": "Previous Output",
                    "value": "linked",
                    "variant": "source",
                    "color_checked": "#38BDF8",
                },
            ])
        
        self.cover_mode_toggle.setVisible(self.is_config)
        
        # self.cover_mode_toggle.mode_changed.connect(self.on_cover_mode_changed) TODO
        
        drop_zone = FileDropWidget(
            text="Drop cover image here or click to browse",
            sub_text="Supports PNG, JPEG, WebP and other image formats",
            icon_path=str(svg_path("photo.svg")),
            allowed_extensions=ALLOWED_EXTS,
        )
        
        self.cover_drop_zone = drop_zone
        drop_zone.file_selected.connect(self.on_cover_file_selected)

        self.cover_source_stack = QStackedWidget()
        self.cover_source_stack.addWidget(drop_zone)

        cover_file_layout.addWidget(title_container, 0)  # top
        cover_file_layout.addWidget(self.cover_mode_toggle, 0)
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
        photo_icon = create_icon_pixmap(svg_path("message.svg"), size=ICON_SIZE)
        title_icon.setPixmap(photo_icon)

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

        drop_zone = FileDropWidget(
            "Drop text file here or click to browse", "Supported: .txt", 
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
        photo_icon = create_icon_pixmap(svg_path("shield-lock.svg"), "#a78bfa", ICON_SIZE)
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
        self.encrypt_mode_toggle.mode_changed.connect(self.on_encrypt_mode_changed)
        self.encrypt_toggle_switch.toggled.connect(self.encrypt_stack.setVisible)

        self.encrypt_toggle_switch.toggled.connect(self.update_capacity_label)
        self.password_input.textChanged.connect(self.update_capacity_label)

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
                "color_checked": "#a78bfa",
                "icon_path": svg_path("key.svg"),
                "icon_size": 14,
            },
            {
                "text": "Public Key",
                "value": "public_key",
                "variant": "public_key",
                "color_checked": "#34D399",
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

        return symmetric_mode
    
    
    def build_asymmetric_mode(self):
        asymmetric_mode = QFrame()
        asymmetric_layout = QVBoxLayout(asymmetric_mode)
        asymmetric_layout.setContentsMargins(0, 0, 0, 8)

        self.public_key_source = KeySourceWidget("public", self.key_registry)
        self.public_key_drop_zone = self.public_key_source.drop_zone
        asymmetric_layout.addWidget(self.public_key_source)

        self.public_key_status = KeyValidationLabel()
        asymmetric_layout.addWidget(self.public_key_status)
        self.public_key_source.key_selected.connect(self.on_public_key_selected)
        return asymmetric_mode
    
    def get_inputs(self) -> LSBInputsDraft:
        """Return a fresh draft, including values in inactive encryption modes."""
        return LSBInputsDraft(
            cover=self.cover_source,
            payload_text=self.payload_text_area.toPlainText(),
            encryption_enabled=self.encrypt_toggle_switch.isChecked(),
            encryption_mode=self.encrypt_mode_toggle.mode(),
            password=self.password_input.text(),
            public_key_path=self.public_key_path,
        )

    def passwords_match(self) -> bool:
        return self.password_input.text() == self.confirm_input.text()

    # --- Event handler ---
    def on_encrypt_mode_changed(self, mode: str):
        self.encrypt_stack.setCurrentIndex(0 if mode == "password" else 1)
        self.update_capacity_label()

    @property
    def cover_file_path(self) -> str | None:
        return self.cover_source if isinstance(self.cover_source, str) else None

    @cover_file_path.setter
    def cover_file_path(self, file_path: str | None):
        self.cover_source = file_path
    
    def on_cover_file_selected(self, file_path: str):
        if self.cover_mode_toggle.mode() == "linked":
            return
        
        self.capacity_request += 1
        request = self.capacity_request
        self.cover_file_path = file_path or None
        self.capacity_bits = None
        self.isCalculating = bool(file_path)
        self.update_capacity_label()
        if not file_path:
            return

        worker = FunctionWorker(LSBPP().get_total_capacity_bits, file_path)
        self.capacity_workers[request] = worker
        worker.done.connect(lambda result: self.on_cal_capacity_done(result, request))
        worker.finished.connect(lambda: self.release_capacity_worker(request))
        worker.start()

    def release_capacity_worker(self, request: int):
        worker = self.capacity_workers.pop(request, None)
        if worker is not None:
            worker.deleteLater()

    def on_cal_capacity_done(self, result, request: int):
        if request != self.capacity_request:
            return
        self.isCalculating = False
        if isinstance(result, tuple) and len(result) == 2 and result[1] == self.cover_file_path:
            self.capacity_bits = result[0]
            self.update_capacity_label()
        else:
            self.capacity_bits = None
            self.update_capacity_label()
            error = result.get("error", "Invalid capacity result") if isinstance(result, dict) else "Invalid capacity result"
            self.capacity_label.setToolTip(f"Could not calculate cover capacity: {error}")
            self.set_capacity_state("warning")

    def on_payload_text_changed(self):
        self.update_capacity_label()

    def on_payload_file_selected(self, file_path: str):
        self.payload_file_path = file_path or None
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
        
    def update_capacity_label(self):
        """อัปเดต label + tooltip อธิบาย overhead ตามข้อความที่พิมพ์ (สีปกติไม่เปลี่ยน มีแค่
        เตือนเหลือง/แดงตอนใกล้เต็ม/เต็ม capacity ดู set_capacity_state)
        + โหมดเข้ารหัสที่เลือกอยู่ตอนนี้ โชว์แค่ Size เฉยๆ จนกว่าจะรู้ max capacity จริง
        (ต้องมี cover image แล้ว และถ้าเป็น asymmetric ต้องมี public key ด้วย เพราะ overhead
        ขึ้นกับขนาด RSA key ที่ใช้)"""
        
        if self.isCalculating:
            self.capacity_label.setText("Calculating...")
            self.capacity_label.setToolTip("Calculating cover capacity...")
            self.set_capacity_state("normal")
            return
        
        text_size_bytes = len(self.payload_text_area.toPlainText().encode('utf-8'))
        text_size = format_file_size(text_size_bytes)

        if isinstance(self.cover_source, StepOutput):
            self.capacity_label.setText(f"Size: {text_size}")
            self.capacity_label.setToolTip(
                "Linked cover capacity will be checked when the pipeline runs."
            )
            self.set_capacity_state("normal")
            return

        mode = self.encrypt_mode_toggle.mode()
        no_key_yet = self.encrypt_toggle_switch.isChecked() and mode == "public_key" and not self.public_key_path
        if self.capacity_bits is None or no_key_yet:
            self.capacity_label.setText(f"Size: {text_size}")
            self.capacity_label.setToolTip(
                "Select a public key to see max capacity" if no_key_yet else "Select a cover image to see max capacity"
            )
            self.set_capacity_state("normal")
            return

        # โหมดไหนถูกเลือกอยู่ ใช้ตัดสิน overhead + ข้อความอธิบายใน tooltip
        password = None
        public_key_path = None
        overhead_detail = "no encryption (header only)"
        if self.encrypt_toggle_switch.isChecked():
            if mode == "password":
                password = self.password_input.text()
                overhead_detail = f"password mode: salt {AES_SALT_LENGTH}B + nonce {AES_NONCE_LENGTH}B + tag {AES_TAG_LENGTH}B"
            elif mode == "public_key":
                public_key_path = self.public_key_path
                overhead_detail = f"public key mode: RSA-encrypted session key + nonce {AES_NONCE_LENGTH}B + tag {AES_TAG_LENGTH}B"

        try:
            overhead_bytes = estimate_overhead_bytes(password, public_key_path)
            max_bytes = get_max_message_bytes(self.capacity_bits, password, public_key_path)
        except Exception:
            # เช่น public key ไฟล์เสีย/อ่านไม่ได้ จะโชว์แค่ขนาดข้อความ ไม่ให้ label พังเงียบๆ
            self.capacity_label.setText(f"Size: {text_size} / Invalid Key")
            self.capacity_label.setToolTip("Could not read the public key to estimate capacity.")
            self.set_capacity_state("warning")
            return

        self.capacity_label.setText(f"Size: {text_size} / {format_file_size(max_bytes)}")

        # เกิน max = แดง, ใช้ไปแล้ว > 90% = เหลือง, นอกนั้นปกติ
        usage_ratio = (text_size_bytes / max_bytes) if max_bytes > 0 else 1.0
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
        
    def set_capacity_state(self, state: str):
        """state: 'normal' | 'warning' | 'danger' ผูกกับ QSS ผ่าน property"""
        self.capacity_label.setProperty("capacityState", state)
        self.capacity_label.style().unpolish(self.capacity_label)
        self.capacity_label.style().polish(self.capacity_label)
