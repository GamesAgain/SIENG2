from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QTabWidget, QVBoxLayout, QWidget)

from PyQt6.QtCore import QSize, Qt

from src.core.stego.lsb_pp import HEADER_BYTES, LSBPP, estimate_overhead_bytes, get_max_message_bytes
from src.gui.components.files_drop import FileDropWidget
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, create_icon_state, format_file_size
from src.gui.components.key_source import KeySourceWidget
from src.gui.components.key_validation import KeyValidationLabel, inspect_public_key
from src.gui.components.password_visibility import add_password_visibility_toggle
from src.gui.components.toggle_switch import ToggleSwitch
from src.gui.components.visibility_stack import VisibilityStack
from src.gui.components.worker import FunctionWorker
from src.gui.services.key_registry import KeyRegistry
from config_prototype.gui.paths import ICON_DIR

ICON_SIZE = 14
COLOR_CHECKED_SYM = "#a78bfa"
COLOR_CHECKED_ASYM = "#34D399"
CAPACITY_WARNING_RATIO = 0.90  # ใช้ไป > 90% ของ max capacity แล้ว ให้เตือนสีเหลือง


@dataclass
class LSBInputsDraft:
    "LSB++ inputs draft for saving/loading state of the form."
    cover_path: str | None = None
    payload_text: str = ""
    encryption_enabled: bool = True
    encryption_mode: str = "password"
    password: str = field(default="", repr=False)
    public_key_path: str | None = None


class LSBEmbedInputs(QFrame):
    """Host LSB++ inputs without depending on a page or shell variant."""

    def __init__(
        self,
        *,
        key_registry: KeyRegistry | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.key_registry = key_registry
        
        # Cover & Payload
        self.cover_file_path: str | None = None
        self.payload_file_path: str | None = None
        self.capacity_bits: int | None = None  # ผล analyze ภาพ (Sobel+entropy) แคชไว้เพราะหนัก ไม่คำนวณซ้ำทุกครั้งที่พิมพ์/สลับโหมด
        self.isCalculating = False
        
        # Encryption
        self.public_key_path: str | None = None
        
        self.build_ui()
        
    
    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

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
        right_scroll.setObjectName("pageScrollArea")
        right_scroll.setWidgetResizable(True)
        right_scroll.setWidget(right_widget)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)

        sub_layout.addLayout(left_layout, 1)
        sub_layout.addWidget(right_scroll, 1)

        main_layout.addLayout(sub_layout)

        # TODO: LSB Options card (channel select, alpha embed, gradient/entropy/shuffle
        # toggles, etc.) -- shelved, see .claude/notes/lsb-options-plan.md before resuming
        # main_layout.addWidget(self.build_lsb_options_card())

        self.update_capacity_label()  # เซ็ตข้อความเริ่มต้นให้ตรง state จริง (ยังไม่มี cover)
    
    
    def build_cover_file_card(self):
        cover_file_card = QFrame()
        cover_file_card.setObjectName("card")
        add_shadow_effect(cover_file_card)

        cover_file_layout = QVBoxLayout(cover_file_card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)

        # Icon
        title_icon = QLabel()
        photo_icon = create_icon_pixmap(ICON_DIR / "photo.svg", size=16)
        title_icon.setPixmap(photo_icon)

        # Text: Cover File (PNG)
        title_label = QLabel("Cover File (PNG)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        # Declare allowed image file format
        allowed_exts = [
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
        
        drop_zone = FileDropWidget(
            "Drop PNG file here or click to browse", "PNG format only", 
            str(ICON_DIR / "photo.svg"), 
            allowed_extensions=allowed_exts
            )
        
        self.cover_drop_zone = drop_zone
        drop_zone.file_selected.connect(self.on_cover_file_selected)

        cover_file_layout.addWidget(title_container, 0)  # top
        cover_file_layout.addWidget(drop_zone, 1)

        return cover_file_card
    
    
    def build_payload_card(self):
        payload_card = QFrame()
        payload_card.setObjectName("card")
        add_shadow_effect(payload_card)

        payload_layout = QVBoxLayout(payload_card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)

        # Icon
        title_icon = QLabel()
        photo_icon = create_icon_pixmap(ICON_DIR / "message.svg", size=16)
        title_icon.setPixmap(photo_icon)

        # Text: Payload (Secret Message)
        title_label = QLabel("Payload (Secret Message)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.payload_tabs = QTabWidget()

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

        drop_zone = FileDropWidget("Drop text file here or click to browse", "Supported: .txt", icon_path=str(ICON_DIR / "file-text.svg"), allowed_extensions=["txt"])
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
        self.encrypt_toggle_switch.toggled.connect(self.encrypt_stack.setVisible)

        # โหมดเข้ารหัสมีผลต่อ overhead ของ payload -> capacity ที่โชว์ต้องอัปเดตตามด้วย
        self.encrypt_group.idClicked.connect(self.update_capacity_label)
        self.encrypt_toggle_switch.toggled.connect(self.update_capacity_label)

        title_layout.addWidget(encrypt_selection)
        encryption_layout.addWidget(title_container)
        encryption_layout.addWidget(self.encrypt_stack)

        return encryption_card
    
    
    def build_encrypt_selection(self):
    
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
    
    
    def build_symmetric_mode(self):
        symmetric_mode = QFrame()
        symmetric_mode.setObjectName("symmetricMode")

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
    def load_draft(self, draft: LSBInputsDraft) -> None:
        self.cover_file_path = None
        self.public_key_path = None
        self.capacity_bits = None
        self.isCalculating = False

        # Payload
        self.payload_text_area.setPlainText(draft.payload_text)

        # Encryption
        self.encrypt_toggle_switch.setChecked(draft.encryption_enabled)

        if draft.encryption_mode == "public_key":
            self.btn_asymmetric.setChecked(True)
            self.encrypt_stack.setCurrentIndex(1)
        else:
            self.btn_symmetric.setChecked(True)
            self.encrypt_stack.setCurrentIndex(0)

        self.password_input.setText(draft.password)
        self.confirm_input.setText(draft.password)

        # Public Key
        public_key_path = draft.public_key_path

        if public_key_path and Path(public_key_path).is_file():
            self.public_key_drop_zone.add_files([public_key_path])
        else:
            self.public_key_drop_zone.clear_all()

        # Cover
        cover_path = draft.cover_path

        if cover_path and Path(cover_path).is_file():
            self.cover_drop_zone.add_files([cover_path])
        else:
            self.cover_drop_zone.clear_all()

        # ถ้ามี Cover และ worker กำลังทำงาน จะขึ้น Calculating...
        # ถ้าไม่มี Cover จะแสดงเฉพาะขนาด Payload
        self.update_capacity_label()

    def validate_draft(self) -> bool:
        cover_path = self.cover_file_path
        if not cover_path or not Path(cover_path).is_file():
            return self.show_validation_warning(
                "Please select an available cover image file."
            )

        if not self.payload_text_area.toPlainText().strip():
            return self.show_validation_warning(
                "Please enter a secret message or drop a text file."
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
            if not self.public_key_path:
                return self.show_validation_warning(
                    "Please select a public key for encryption."
                )

            result = inspect_public_key(self.public_key_path)
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

    def export_draft(self) -> LSBInputsDraft:
        encryption_enabled = self.encrypt_toggle_switch.isChecked()
        encryption_mode = (
            "public_key" if self.btn_asymmetric.isChecked() else "password"
        )
        return LSBInputsDraft(
            cover_path=self.cover_file_path,
            payload_text=self.payload_text_area.toPlainText(),
            encryption_enabled=encryption_enabled,
            encryption_mode=encryption_mode,
            password=(
                self.password_input.text() if encryption_enabled and encryption_mode == "password"
                else ""
            ),
            public_key_path=(
                self.public_key_path
                if encryption_enabled and encryption_mode == "public_key"
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
    
    
    # --- Event Handler ---
    def on_cover_file_selected(self, file_path: str):
        if not file_path:
            self.cover_file_path = None
            return
        self.cover_file_path = file_path

        self.isCalculating = True
        self.update_capacity_label()
        
        self.cap_worker = FunctionWorker(
            LSBPP().get_total_capacity_bits,
            file_path
        )
        self.cap_worker.done.connect(self.on_cal_capacity_done)
        self.cap_worker.start()
    
    def on_payload_text_changed(self):
            self.update_capacity_label()
        
    def update_capacity_label(self):
        """อัปเดต label + tooltip อธิบาย overhead ตามข้อความที่พิมพ์ (สีปกติไม่เปลี่ยน มีแค่
        เตือนเหลือง/แดงตอนใกล้เต็ม/เต็ม capacity ดู set_capacity_state)
        + โหมดเข้ารหัสที่เลือกอยู่ตอนนี้ โชว์แค่ Size เฉยๆ จนกว่าจะรู้ max capacity จริง
        (ต้องมี cover image แล้ว และถ้าเป็น asymmetric ต้องมี public key ด้วย เพราะ overhead
        ขึ้นกับขนาด RSA key ที่ใช้)"""
        if self.isCalculating:
            self.capacity_label.setText("Calculating...")
            return
        
        text_size_bytes = len(self.payload_text_area.toPlainText().encode('utf-8'))
        text_size = format_file_size(text_size_bytes)

        no_key_yet = self.encrypt_toggle_switch.isChecked() and self.btn_asymmetric.isChecked() and not self.public_key_path
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
            if self.btn_symmetric.isChecked():
                password = self.password_input.text()
                overhead_detail = "password mode: salt 16B + nonce 12B + tag 16B"
            elif self.btn_asymmetric.isChecked():
                public_key_path = self.public_key_path
                overhead_detail = "public key mode: RSA-encrypted session key + nonce 12B + tag 16B"

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
        """state: 'normal' | 'warning' | 'danger' ผูกกับ QSS ผ่าน property (ดู default.qss)"""
        self.capacity_label.setProperty("capacityState", state)
        self.capacity_label.style().unpolish(self.capacity_label)
        self.capacity_label.style().polish(self.capacity_label)
        
    def on_cal_capacity_done(self, result):
        self.isCalculating = False
        
        if not isinstance(result, tuple) or len(result) != 2:
            # กรณีที่ Worker โยน Error กลับมาเป็น Dict หรือ String
            self.capacity_bits = None
            self.update_capacity_label()
            print("Failed to calculate capacity.")
            return
        
        calculated_bits, return_file_path = result
        
        # ตรวจสอบ Task ID (ป้องกัน Race Condition ตอนผู้ใช้สลับรูปไวๆ)
        if return_file_path != self.cover_file_path:
            # ถ้า Path ที่คำนวณเสร็จ ไม่ตรงกับ Path ของรูปที่เปิดอยู่ปัจจุบัน ให้ทิ้งผลลัพธ์ไปเลย
            print(f"Discarded stale result for: {return_file_path}")
            return
        
        self.capacity_bits = calculated_bits
        self.update_capacity_label()
    
    def on_payload_file_selected(self, file_path: str):
        if not file_path:
            self.payload_file_path = None
            return
        self.payload_file_path = file_path

        encodings_to_try = ['utf-8-sig', 'utf-8', 'utf-16', 'cp874']
        payload_text = ""
        read_success = False
        last_error = None

        for encoding in encodings_to_try:
            try:
                with open(file_path, 'r', encoding=encoding) as file:
                    payload_text = file.read()
                read_success = True
                break
            except UnicodeDecodeError as error:
                last_error = error
                continue
            except Exception as error:
                last_error = error
                break

        if read_success:
            self.payload_text_area.setPlainText(payload_text)
            self.payload_tabs.setCurrentIndex(0)
        else:
            self.payload_text_area.clear()
            self.payload_tabs.setCurrentIndex(1)
    
    def on_public_key_selected(self, file_path: str):
        if not file_path:
            self.public_key_path = None
            self.public_key_status.clear_result()
            self.update_capacity_label()
            return

        result = inspect_public_key(file_path)
        self.public_key_status.set_result(result)
        self.public_key_path = file_path
        self.update_capacity_label()  # ขนาด RSA key มีผลต่อ overhead ของโหมด asymmetric
