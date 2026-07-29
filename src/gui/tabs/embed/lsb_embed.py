from pathlib import Path
from PIL import Image
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QStackedWidget, QTabWidget, QVBoxLayout

from src.core.stego.lsb_pp import HEADER_BYTES, LSBPP, estimate_overhead_bytes, get_max_message_bytes
from src.gui.components.file_drop import FileDropWidget
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, create_icon_state, format_file_size
from src.gui.components.linked_step_toggle import LinkedStepToggle
from src.gui.components.step_output_picker import StepOutputPicker
from src.gui.components.toggle_switch import ToggleSwitch
from src.gui.components.visibility_stack import VisibilityStack
from src.gui.components.worker import FunctionWorker

ICON_DIR = Path(__file__).parent.parent.parent / "assets" / "svg"

ICON_SIZE = 14
COLOR_CHECKED_SYM = "#a78bfa"
COLOR_CHECKED_ASYM = "#34D399"
CAPACITY_WARNING_RATIO = 0.90  # ใช้ไป > 90% ของ max capacity แล้ว ให้เตือนสีเหลือง


class LSBEmbedInputs(QFrame):
    """ส่วน 'input' ของ LSB embed (cover + payload + encryption + options)
    แยกออกจาก execute bar เพื่อ reuse ได้ทั้งหน้า Standalone (LSBEmbedTab ห่อ + ปุ่ม Embed) และ Configurable Pipeline (เอาไปใส่ popup/inline ของ step config)

    เก็บ widget/state ทั้งหมดไว้บน self แล้วเปิด API `get_input_data()` /
    `validate_input()` ให้ผู้เรียก (tab หรือ pipeline) ดึงค่าไปใช้ต่อ"""

    def __init__(self, pipeline_mode: bool = False):
        super().__init__()

        # Cover & Payload
        self.cover_file_path = None
        self.payload_text = ""
        self.payload_file_path = None
        self.linked_cover_index: list[int] = []  # non-empty = cover มาจาก output ของ step ก่อนหน้า (pipeline_mode)
        self.capacity_bits = None  # ผล analyze ภาพ (Sobel+entropy) — แคชไว้เพราะหนัก ไม่คำนวณซ้ำทุกครั้งที่พิมพ์/สลับโหมด
        self.isCalculating = False
        
        # Encryption
        self.password = ""
        self.public_key_path = None

        # True เมื่อฝังใน Configurable Pipeline step → โชว์ toggle Manual Upload / Linked from Step
        self.pipeline_mode = pipeline_mode

        self.build_ui()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        sub_layout = QHBoxLayout()

        # --- Left side - Cover file ---
        left_layout = QVBoxLayout()
        left_layout.addWidget(self.build_cover_file_card())

        # --- Right side - Payload and Encryption ---
        right_layout = QVBoxLayout()
        right_layout.addWidget(self.build_payload_card())
        right_layout.addWidget(self.build_encryption_card())

        sub_layout.addLayout(left_layout, 1)
        sub_layout.addLayout(right_layout, 1)

        main_layout.addLayout(sub_layout)

        # TODO: LSB Options card (channel select, alpha embed, gradient/entropy/shuffle
        # toggles, etc.) -- shelved, see .claude/notes/lsb-options-plan.md before resuming
        # main_layout.addWidget(self.build_lsb_options_card())

        self.update_capacity_label()  # เซ็ตข้อความเริ่มต้นให้ตรง state จริง (ยังไม่มี cover)

    def build_lsb_options_card(self):
        lsb_options_card = QFrame()
        lsb_options_card.setObjectName("card")
        add_shadow_effect(lsb_options_card)

        lsb_options_layout = QVBoxLayout(lsb_options_card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)

        # Icon
        title_icon = QLabel()
        photo_icon = create_icon_pixmap(ICON_DIR / "adjustments.svg", size=16)
        title_icon.setPixmap(photo_icon)

        # Text: LSB Options
        title_label = QLabel("LSB Options")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        lsb_options_layout.addWidget(title_container)

        return lsb_options_card

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
        self.encrypt_stack = QStackedWidget()

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

    def build_symmetric_mode(self):
        symmetric_mode = QFrame()
        symmetric_mode.setObjectName("symmetricMode")

        symmetric_layout = QVBoxLayout(symmetric_mode)

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
        self.confirm_input.setPlaceholderText("Confirm your passphrase...")

        symmetric_layout.addWidget(confirm_label)
        symmetric_layout.addWidget(self.confirm_input)

        return symmetric_mode

    def build_asymmetric_mode(self):
        asymmetric_mode = QFrame()
        asymmetric_mode.setObjectName("asymmetricMode")

        asymmetric_layout = QVBoxLayout(asymmetric_mode)
        asymmetric_layout.setContentsMargins(0, 0, 0, 8)
        key_drop_zone = FileDropWidget("Drop public key here or click to browse", "Public key file (.pem, .der, .ssh)", icon_path=str(ICON_DIR / "file-text-shield.svg"), allowed_extensions=["pem", "der", "ssh"])
        key_drop_zone.file_selected.connect(self.on_public_key_selected)
        asymmetric_layout.addWidget(key_drop_zone)

        return asymmetric_mode

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

    def build_payload_card(self):
        payload_card = QFrame()
        payload_card.setObjectName("card")
        payload_card.setMinimumHeight(200)
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
        drop_zone.file_selected.connect(self.on_payload_file_selected)
        drop_zone.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        text_file_layout.addWidget(drop_zone)

        self.payload_tabs.addTab(text_input_tab, "Text Input")
        self.payload_tabs.addTab(text_file_tab, "Text File")

        payload_layout.addWidget(title_container)
        payload_layout.addWidget(self.payload_tabs)

        return payload_card

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
        allowed_exts = ["png", "jpg", "jpeg", "gif", "webp", "avif", "bmp", "tiff", "tif"]
        
        drop_zone = FileDropWidget("Drop PNG file here or click to browse", "PNG format only", str(ICON_DIR / "photo.svg"), allowed_extensions=allowed_exts)
        drop_zone.file_selected.connect(self.on_cover_file_selected)

        cover_file_layout.addWidget(title_container, 0)  # top

        if self.pipeline_mode:
            self.linked_toggle = LinkedStepToggle()
            title_layout.addWidget(self.linked_toggle)

            # สลับระหว่าง drop zone (Manual Upload) กับ StepOutputPicker (Linked from Step)
            self.cover_source_stack = VisibilityStack()
            self.cover_source_stack.addWidget(drop_zone)
            self.cover_picker = StepOutputPicker(max_selection=1)
            self.cover_picker.selectionChanged.connect(self.on_cover_link_changed)
            self.cover_source_stack.addWidget(self.cover_picker)
            self.linked_toggle.modeChanged.connect(self.on_cover_link_mode_changed)

            cover_file_layout.addWidget(self.cover_source_stack, 1)
        else:
            cover_file_layout.addWidget(drop_zone, 1)  # Stretch factor

        return cover_file_card

    # --- Linked-from-Step (Configurable Pipeline เท่านั้น) ---
    def set_cover_link_candidates(self, candidates: list[dict]):
        """เรียกจาก EmbedConfigurablePage ก่อนเปิด step config ทุกครั้ง — ป้อน list ของ
        step ก่อนหน้าที่ยังว่าง+type ตรงเงื่อนไข ให้ picker แสดง"""
        self.cover_picker.set_candidates(candidates)

    def on_cover_link_mode_changed(self, is_linked: bool):
        self.cover_source_stack.setCurrentIndex(1 if is_linked else 0)
        if not is_linked:
            self.linked_cover_index = []
            self.cover_picker.clear_selection()

    def on_cover_link_changed(self, index: list[int]):
        self.linked_cover_index = index

    def get_linked_cover_index(self) -> list[int]:
        return self.linked_cover_index

    def clear_links(self):
        """เคลียร์ cover link กลับเป็น Manual Upload — page เรียกเวลาลบ step ที่ถูก link ไว้"""
        self.linked_cover_index = []
        if self.pipeline_mode:
            self.linked_toggle.set_linked(False)
            self.cover_source_stack.setCurrentIndex(0)
            self.cover_picker.clear_selection()

    # --- Input API (ให้ tab / pipeline เรียกใช้) ---
    def get_input_data(self) -> tuple[str, str, str, str] | bool:
        # 1. เช็คความถูกต้องทั้งหมดก่อน
        if not self.validate_input():
            return False

        # 2. ดึงข้อมูลพื้นฐานที่ต้องใช้แน่ๆ
        payload_text = self.payload_text_area.toPlainText().strip()

        # 3. เคลียร์ค่ากุญแจให้ว่างเปล่าไว้ก่อน (ป้องกันการส่งค่าขยะข้ามโหมด)
        password = None
        public_key = None

        if not self.encrypt_toggle_switch.isChecked():
            return self.cover_file_path, payload_text, password, public_key

        # 4. ดึงค่าเฉพาะโหมดเข้ารหัสที่กำลังเปิดใช้งานอยู่
        if self.btn_symmetric.isChecked():
            password = self.password_input.text()
        elif self.btn_asymmetric.isChecked():
            public_key = self.public_key_path

        return self.cover_file_path, payload_text, password, public_key

    def validate_input(self):
        # 1. เช็ค Cover File (อัปโหลดเอง หรือ linked จาก step ก่อนหน้า อย่างใดอย่างหนึ่ง)
        if not self.cover_file_path and not self.linked_cover_index:
            QMessageBox.warning(self, "Validation Error", "Please select a cover PNG file.")
            return False

        # 2. เช็ค Payload
        if not self.payload_text_area.toPlainText().strip():
            QMessageBox.warning(self, "Validation Error", "Please enter a secret message or drop a text file.")
            return False

        # 3. เช็คว่าได้เปิดการเข้ารหัสไหม
        if not self.encrypt_toggle_switch.isChecked():
            return True

        # 4. เช็คโหมด Symmetric (Password)
        if self.btn_symmetric.isChecked():
            password = self.password_input.text()
            confirm = self.confirm_input.text()

            if not password:
                QMessageBox.warning(self, "Validation Error", "Please enter a password for encryption.")
                self.password_input.setFocus()  # เด้งไปรอให้พิมพ์
                return False

            if password != confirm:
                QMessageBox.warning(self, "Validation Error", "Passwords do not match! Please confirm your passphrase.")
                self.confirm_input.clear()
                self.confirm_input.setFocus()
                return False

        # 5. เช็คโหมด Asymmetric (Public Key)
        elif self.btn_asymmetric.isChecked():
            # เช็คว่าตัวแปรถูกสร้างไว้และมีค่า Path ของไฟล์ (.pem, .der) หรือไม่
            if not hasattr(self, 'public_key_path') or not self.public_key_path:
                QMessageBox.warning(self, "Validation Error", "Please drop a Public Key file for asymmetric encryption.")
                return False

        return True

    # --- Event Handler ---
    def on_cover_file_selected(self, file_path: str):
        self.cover_file_path = file_path

        self.isCalculating = True
        self.update_capacity_label()
        
        self.cap_worker = FunctionWorker(
            LSBPP().get_total_capacity_bits,
            file_path
        )
        self.cap_worker.done.connect(self.on_cal_capacity_done)
        self.cap_worker.start()
        
    def on_cal_capacity_done(self, result):
        # 1. อัปเดตสถานะว่าคำนวณเสร็จแล้ว
        self.isCalculating = False
        
        # 2. เช็คว่าเกิด Error หรือรับค่ามาผิดประเภทหรือไม่ (Backend ส่งกลับมาเป็น Tuple 2 ตัว)
        if not isinstance(result, tuple) or len(result) != 2:
            # กรณีที่ Worker โยน Error กลับมาเป็น Dict หรือ String
            self.capacity_bits = None
            self.update_capacity_label()
            print("Failed to calculate capacity.")
            return
        
        # 3. แตกค่าที่ได้จาก Tuple
        calculated_bits, return_file_path = result
        
        # 4. ตรวจสอบ Task ID (ป้องกัน Race Condition ตอนผู้ใช้สลับรูปไวๆ)
        if return_file_path != self.cover_file_path:
            # ถ้า Path ที่คำนวณเสร็จ ไม่ตรงกับ Path ของรูปที่เปิดอยู่ปัจจุบัน ให้ทิ้งผลลัพธ์ไปเลย
            print(f"Discarded stale result for: {return_file_path}")
            return
        
        # 5. ถ้าข้อมูลถูกต้อง ค่อยอัปเดตตัวแปรและหน้าจอ
        self.capacity_bits = calculated_bits
        self.update_capacity_label()
        
    def on_public_key_selected(self, file_path: str):
        self.public_key_path = file_path
        self.update_capacity_label()  # ขนาด RSA key มีผลต่อ overhead ของโหมด asymmetric

    def on_payload_file_selected(self, file_path: str):
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
            print(f"Error reading text file: {last_error}")
            self.payload_text_area.clear()
            self.payload_tabs.setCurrentIndex(1)

    def on_payload_text_changed(self):
        self.update_capacity_label()

    def update_capacity_label(self):
        """อัปเดต label + tooltip อธิบาย overhead ตามข้อความที่พิมพ์ (สีปกติไม่เปลี่ยน มีแค่
        เตือนเหลือง/แดงตอนใกล้เต็ม/เต็ม capacity — ดู set_capacity_state)
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
            # เช่น public key ไฟล์เสีย/อ่านไม่ได้ — โชว์แค่ขนาดข้อความ ไม่ให้ label พังเงียบๆ
            self.capacity_label.setText(f"Size: {text_size}")
            self.capacity_label.setToolTip("Could not read the public key to estimate capacity.")
            self.set_capacity_state("normal")
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
        """state: 'normal' | 'warning' | 'danger' — ผูกกับ QSS ผ่าน property (ดู default.qss)"""
        self.capacity_label.setProperty("capacityState", state)
        self.capacity_label.style().unpolish(self.capacity_label)
        self.capacity_label.style().polish(self.capacity_label)


class LSBEmbedTab(QFrame):
    """หน้า Standalone ของ LSB — ห่อ LSBEmbedInputs แล้วต่อ execute bar
    (status + progress + ปุ่ม Embed Data) ที่รัน engine + เซฟไฟล์เองในโหมดนี้"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 11, 4, 4)

        # ส่วน input (reuse ร่วมกับ Configurable Pipeline)
        self.inputs = LSBEmbedInputs()
        main_layout.addWidget(self.inputs)

        main_layout.addStretch()

        # --- Final layout for loading status bar and execute button ---
        final_layout = QHBoxLayout()
        final_layout.setContentsMargins(0, 0, 0, 0)

        # Loading & Status Bar
        loading_status_bar = self.build_loading_status_bar()
        final_layout.addWidget(loading_status_bar)

        # Execute Embed Data
        self.execute_embed_btn = QPushButton("Embed Data")
        self.execute_embed_btn.setFixedHeight(50)
        self.execute_embed_btn.setObjectName("PrimaryActionBtn")
        self.execute_embed_btn.clicked.connect(self.execute_embedding)
        final_layout.addWidget(self.execute_embed_btn)

        main_layout.addLayout(final_layout)

    def build_loading_status_bar(self):
        loading_status_bar = QFrame()
        loading_status_bar.setObjectName("card")
        loading_status_bar_layout = QVBoxLayout(loading_status_bar)

        self.status_label = QLabel("Status: Ready")
        self.status_label.setObjectName("statusLabel")
        loading_status_bar_layout.addWidget(self.status_label)

        self.loading_bar = QProgressBar()
        self.loading_bar.setObjectName("loadingIndicator")
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setFixedHeight(10)
        self.loading_bar.setRange(0, 100)
        self.loading_bar.setValue(0)
        loading_status_bar_layout.addWidget(self.loading_bar)

        return loading_status_bar

    def execute_embedding(self):
        # ดึง input จากส่วน reuse (validate ในตัว)
        data = self.inputs.get_input_data()
        if not data:
            return

        cover_file_path, payload_text, password, public_key_path = data
        
        lsbpp = LSBPP()
        self.embed_worker = FunctionWorker(
            lsbpp.embed,
            cover_file_path,
            payload_text,
            public_key_path,
            password,
            report_progress=True,
            )
        self.embed_worker.progress.connect(self.on_update_progess)
        self.embed_worker.done.connect(self.on_embed_done)
        self.execute_embed_btn.setEnabled(False)
        self.embed_worker.start()

    def save_stego_image(self, stego_image_bytes: bytes, default_name: str) -> bool:
        try:

            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Stego Image",     # ชื่อหน้าต่าง
                default_name,           # ชื่อไฟล์ตั้งต้นที่ดึงมาจาก LSB++
                "PNG Images (*.png)"    # ล็อกนามสกุลไฟล์เพื่อไม่ให้พิกเซลเสียหาย
            )

            if save_path:
                Path(save_path).write_bytes(stego_image_bytes)

                QMessageBox.information(self, "Success", f"Data embedded successfully!\nSaved to:\n{save_path}")
                print(f"Saved successfully at: {save_path}")
                return True
            else:
                print("User cancelled saving.")
                return False

        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"can't save file:\n{e}")
            print(f"Save Error: {e}")
            return False
    
    # --- Event Handler ---    
    def on_update_progess(self, percent: int, message: str):
        self.status_label.setText(f'Status: {message}')
        self.loading_bar.setValue(percent)
        
    def on_embed_done(self, result):
        if isinstance(result, dict) and "error" in result:
            QMessageBox.critical(self, "Error", f"Failed to embed: {result['error']}")
            self.on_update_progess(0, "Ready")
            self.execute_embed_btn.setEnabled(True)
            return
        stego_image_bytes, stego_name = result
        self.save_stego_image(stego_image_bytes, stego_name)
        self.on_update_progess(0, "Ready")
        self.execute_embed_btn.setEnabled(True)