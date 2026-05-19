from pathlib import Path
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QLabel

from src.core.stego.locomotive import Locomotive
from src.gui.components.file_drop import FileDropWidget
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, create_icon_state
from src.gui.components.multi_file_drop import MultiFileDropWidget
from src.gui.components.toggle_switch import ToggleSwitch

ICON_DIR = Path(__file__).parent.parent.parent / "assets" / "svg"
ICON_SIZE = 14
COLOR_CHECKED_SYM = "#a78bfa"
COLOR_CHECKED_ASYM = "#34D399"

class LocomotiveExtractTab(QFrame):
    def __init__(self):
        super().__init__()
        
        # State variables
        self.stego_file_paths: list[str] = None
        self.private_key_path: str = None
        
        self.init_ui()
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 11, 4, 4)
        
        sub_layout = QHBoxLayout()
        
        # --- Left side - Stego file ---
        left_layout = QVBoxLayout()
        
        # Locomotive file card
        cover_file_card = self.build_locomotive_file_card()
        left_layout.addWidget(cover_file_card)
        
        # --- Right side - Payload and Encryption ---
        right_layout = QVBoxLayout()
        
        # Decryption card
        decryption_card = self.build_decryption_card()
        right_layout.addWidget(decryption_card)
        
        # --- Add layouts to sub_layout ---
        sub_layout.addLayout(left_layout, 1)
        sub_layout.addLayout(right_layout, 1)
        
        main_layout.addLayout(sub_layout)
        
        # Extraction Result
        extraction_result = self.build_extraction_result()
        main_layout.addWidget(extraction_result)
        
        # Execute button
        execute_box = self.build_execution_box()
        main_layout.addLayout(execute_box, 1)
        
    def build_locomotive_file_card(self):
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
        
        drop_zone = MultiFileDropWidget("Drop PNG files here or click to browse", "PNG format only (Single file OR Multiple files)", str(ICON_DIR / "photo.svg"))
        drop_zone.files_changed.connect(self.on_locomotive_file_selected)
        
        locomotive_file_layout.addWidget(title_container, 0) # top 
        locomotive_file_layout.addWidget(drop_zone, 1) # Stretch factor
        
        return locomotive_file_card
    
    def build_decryption_card(self):
        decryption_card = QFrame()
        decryption_card.setObjectName("card")
        add_shadow_effect(decryption_card)
        
        decryption_layout = QVBoxLayout(decryption_card)
        decryption_layout.setContentsMargins(11, 11, 11, 11)
        decryption_layout.setSpacing(6)
        
        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)
        # Toggle Switch
        self.decrypt_toggle_switch = ToggleSwitch()
        self.decrypt_toggle_switch.setChecked(True)
        title_layout.addWidget(self.decrypt_toggle_switch)
        
        # Icon
        title_icon = QLabel()
        photo_icon = create_icon_pixmap(ICON_DIR / "shield-lock.svg", "#a78bfa", size=16)
        title_icon.setPixmap(photo_icon)
        
        # Text: Decryption Options
        title_label = QLabel("Decryption Options")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        decrypt_selection = self.build_decrypt_selection()
        
        # Encryption Mode Stack 
        self.decrypt_stack = QStackedWidget()
        
        
        # Add encryption modes to stack
        self.decrypt_stack.addWidget(self.build_symmetric_mode())
        self.decrypt_stack.addWidget(self.build_asymmetric_mode())
        self.decrypt_stack.addWidget(self.build_disabled_mode())
        
        
        # Connect toggle switch to stack
        self.decrypt_toggle_switch.toggled.connect(self.on_decryption_toggled)
        self.decrypt_group.idClicked.connect(self.decrypt_stack.setCurrentIndex)
        
        title_layout.addWidget(decrypt_selection)
        decryption_layout.addWidget(title_container)
        decryption_layout.addWidget(self.decrypt_stack)
        
        return decryption_card
    
    def build_decrypt_selection(self):
        
        decrypt_selection = QFrame()
        decrypt_selection.setObjectName("encryptSelectionContainer")
        
        decrypt_layout = QHBoxLayout(decrypt_selection)
        decrypt_layout.setContentsMargins(3, 3, 3, 3) 
        decrypt_layout.setSpacing(3)
        
        # --- SYMMETRIC MODE BUTTON ---
        self.btn_symmetric = QPushButton("Password") 
        self.btn_symmetric.setObjectName("passwordBtn")
        self.btn_symmetric.setCheckable(True)
        self.btn_symmetric.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # ADD ICON
        symmetric_icon_path = ICON_DIR / "lock-open.svg"
        if symmetric_icon_path.exists():
            standalone_icon = create_icon_state(str(symmetric_icon_path), ICON_SIZE, color_checked=COLOR_CHECKED_SYM)
            self.btn_symmetric.setIcon(standalone_icon)
            self.btn_symmetric.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        
        # --- ASYMMETRIC MODE BUTTON ---
        self.btn_asymmetric = QPushButton("Public Key")
        self.btn_asymmetric.setObjectName("publicKeyBtn")
        self.btn_asymmetric.setCheckable(True)
        self.btn_asymmetric.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # ADD ICON
        asymmetric_icon_path = ICON_DIR / "key.svg"
        if asymmetric_icon_path.exists():
            configurable_icon = create_icon_state(str(asymmetric_icon_path), ICON_SIZE, color_checked=COLOR_CHECKED_ASYM)
            self.btn_asymmetric.setIcon(configurable_icon)
            self.btn_asymmetric.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        
        decrypt_layout.addWidget(self.btn_symmetric)
        decrypt_layout.addWidget(self.btn_asymmetric)
        
        # --- BUTTON GROUP ---
        self.decrypt_group = QButtonGroup()
        self.decrypt_group.setExclusive(True)
        self.decrypt_group.addButton(self.btn_symmetric, 0)
        self.decrypt_group.addButton(self.btn_asymmetric, 1)
        
        # Set default selection
        self.btn_symmetric.setChecked(True)
        
        return decrypt_selection
        
    def build_symmetric_mode(self):
        symmetric_mode = QFrame()
        symmetric_mode.setObjectName("symmetricMode")
        
        symmetric_layout = QVBoxLayout(symmetric_mode)
        symmetric_layout.setContentsMargins(0, 0, 0, 8)
        
        # Guide Box
        guide_box = QFrame()
        guide_box.setObjectName("GuideBox")
        guide_box.setMinimumHeight(200)
        guide_layout = QVBoxLayout(guide_box)
        guide_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        guide_layout.setContentsMargins(10, 10, 10, 10)
        guide_layout.setSpacing(4)
        
        
        # Icon label
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setMinimumSize(1, 1)
        icon_label.setPixmap(create_icon_pixmap(str(ICON_DIR / "arrow-big-down-lines.svg"), size=42))
        guide_layout.addWidget(icon_label)
        
        # Text labels
        main_label = QLabel("Enter password to extract hidden data")
        main_label.setObjectName("mainLabel")
        main_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        guide_layout.addWidget(main_label)
        
        symmetric_layout.addWidget(guide_box)
        
        guide_layout.setSpacing(20)
        
        # Password Input
        password_label = QLabel("Password")
        password_label.setObjectName("formLabel")
        
        self.password_input = QLineEdit()
        self.password_input.setObjectName("formInput")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter passphrase...")
        
        symmetric_layout.addWidget(password_label)
        symmetric_layout.addWidget(self.password_input)
        
        symmetric_layout.addStretch()
        
        return symmetric_mode
    
    def build_asymmetric_mode(self):
        asymmetric_mode = QFrame()
        asymmetric_mode.setObjectName("asymmetricMode")
        
        asymmetric_layout = QVBoxLayout(asymmetric_mode)
        asymmetric_layout.setContentsMargins(0, 0, 0, 8)
        key_drop_zone = FileDropWidget("Drop private key here or click to browse", "Private key file (.pem, .der, .ssh)", icon_path= str(ICON_DIR / "file-text-shield.svg"), allowed_extensions=["pem", "der", "ssh"])
        key_drop_zone.setMinimumHeight(200)
        key_drop_zone.file_selected.connect(self.on_private_key_selected)
        asymmetric_layout.addWidget(key_drop_zone)
        
        # Password Input
        key_password_label = QLabel("Private Key Password (Optional)")
        key_password_label.setObjectName("formLabel")
        
        self.key_password_input = QLineEdit()
        self.key_password_input.setObjectName("formInput")
        self.key_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_password_input.setPlaceholderText("Enter key password...")
        
        asymmetric_layout.addWidget(key_password_label)
        asymmetric_layout.addWidget(self.key_password_input)
        
        return asymmetric_mode
    
    def build_disabled_mode(self):
        disabled_mode = QFrame()
        disabled_mode.setObjectName("disabledMode")
        
        disabled_layout = QVBoxLayout(disabled_mode)
        disabled_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disabled_layout.setContentsMargins(0, 0, 0, 0)
        # Icon โล่กากบาท (แนะนำให้หาไอคอน shield-off.svg หรือคล้ายกันมาใส่ในโฟลเดอร์)
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # ใช้สีเทาหม่นๆ เพื่อให้ดูเหมือนถูก Disable ไว้
        icon_label.setPixmap(create_icon_pixmap(ICON_DIR / "shield-off.svg", size=48, color_hex="#52525b")) 
        
        # ข้อความ 
        text_label = QLabel("Decryption disabled")
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # ใช้ฟอนต์ monospace และสีเทาหม่นตาม Design ในภาพ
        text_label.setStyleSheet("color: #52525b; font-family: 'Courier New', monospace; font-size: 13px;")
        
        disabled_layout.addWidget(icon_label)
        disabled_layout.addSpacing(10)
        disabled_layout.addWidget(text_label)
        
        return disabled_mode
    
    
    # --- Event Handlers ---
    def on_decryption_toggled(self, checked: bool):
        # 1. จัดการปุ่ม Password และ Private Key (โชว์/ซ่อน/ทำให้เป็นสีเทา)
        self.btn_symmetric.setEnabled(checked)
        self.btn_asymmetric.setEnabled(checked)
        
        # 2. จัดการหน้า Stack ที่จะแสดง
        if checked:
            # ถ้าเปิด Toggle: ให้กลับไปโชว์หน้าที่ถูกเลือกไว้ล่าสุดใน ButtonGroup (0 หรือ 1)
            current_checked_id = self.decrypt_group.checkedId()
            if current_checked_id != -1:
                self.decrypt_stack.setCurrentIndex(current_checked_id)
        else:
            self.decrypt_stack.setCurrentIndex(2)
            
    def build_extraction_result(self):
        result_box = QFrame()
        result_box.setObjectName("card")
        add_shadow_effect(result_box)
        
        stego_file_layout = QVBoxLayout(result_box)
        
        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        
        # Icon
        title_icon = QLabel()
        photo_icon = create_icon_pixmap(ICON_DIR / "report-search.svg", size=16, color_hex="#cfcfcf")
        title_icon.setPixmap(photo_icon)
        
        # Text: Extraction Result
        title_label = QLabel("Extraction Result")
        title_label.setStyleSheet("font-weight: bold; color: #cfcfcf;")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        self.payload_text_area = QPlainTextEdit()
        self.payload_text_area.setReadOnly(True)
        self.payload_text_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.payload_text_area.setObjectName("payloadTextArea")
        self.payload_text_area.setPlaceholderText("Not text extraction available")
        
        stego_file_layout.addWidget(title_container)
        stego_file_layout.addWidget(self.payload_text_area)
        return result_box
    
    def build_execution_box(self):
        execution_box = QHBoxLayout()
        execution_box.setContentsMargins(0, 0, 0, 0)
        
        # Loading & Status Bar
        loading_status_bar = self.create_loading_status_bar()
        execution_box.addWidget(loading_status_bar)
        
        # Execute Extract Data
        execute_extract_btn = QPushButton("Extract Data")
        execute_extract_btn.setFixedHeight(50)
        execute_extract_btn.setObjectName("ExtractBtn")
        
        execute_extract_btn.clicked.connect(self.execute_extraction)
        execution_box.addWidget(execute_extract_btn)
        
        return execution_box
    
    def create_loading_status_bar(self):
        loading_status_bar = QFrame()
        loading_status_bar.setObjectName("card")
        loading_status_bar_layout = QVBoxLayout(loading_status_bar)
        
        status_label = QLabel("Status: Ready")
        status_label.setObjectName("statusLabel")
        loading_status_bar_layout.addWidget(status_label)
        
        loading_bar = QProgressBar()
        loading_bar.setObjectName("loadingIndicator")
        loading_bar.setTextVisible(False)
        loading_bar.setFixedHeight(10)
        loading_bar.setRange(0, 100)
        loading_bar.setValue(0)
        loading_status_bar_layout.addWidget(loading_bar)
        
        return loading_status_bar
    
    # --- Event Handlers ---
    def on_locomotive_file_selected(self, file_paths):
        if file_paths:
            self.stego_file_paths = file_paths
        else:
            self.stego_file_paths = None

    def on_private_key_selected(self, file_paths):
        if file_paths:
            self.private_key_path = file_paths
        else:
            self.private_key_path = None


    # --- Logic & Execution ---
    def validate_inputs(self) -> bool:
        # 1. เช็คว่าเลือกไฟล์ภาพมาหรือยัง
        if not self.stego_file_paths:
            QMessageBox.warning(self, "Validation Error", "Please select stego image(s) to extract.")
            return False
            
        # 2. เช็คว่าเปิดการถอดรหัสไว้ไหม
        if self.decrypt_toggle_switch.isChecked():
            # ถ้าเป็น Password โหมด
            if self.btn_symmetric.isChecked():
                if not self.password_input.text():
                    QMessageBox.warning(self, "Validation Error", "Please enter the password for decryption.")
                    self.password_input.setFocus()
                    return False
            # ถ้าเป็น Private Key โหมด
            elif self.btn_asymmetric.isChecked():
                if not self.private_key_path:
                    QMessageBox.warning(self, "Validation Error", "Please drop a Private Key file for decryption.")
                    return False
                    
        return True

    def get_input_data(self) -> tuple[list[str], str, str] | bool:
        if not self.validate_inputs():
            return False
            
        password = None
        private_key = None
        
        # ดึงข้อมูลถอดรหัสเฉพาะตอนที่ Toggle เปิดอยู่
        if self.decrypt_toggle_switch.isChecked():
            if self.btn_symmetric.isChecked():
                password = self.password_input.text()
            elif self.btn_asymmetric.isChecked():
                private_key = self.private_key_path
                # นำรหัสผ่านของ Private Key (ถ้ามี) ไปใส่ให้ด้วย
                key_password = self.key_password_input.text()
                password = key_password if key_password else None 
                
        return self.stego_file_paths, private_key, password

    def execute_extraction(self):
        inputs = self.get_input_data()
        if not inputs:
            return
            
        stego_file_paths, private_key_path, password = inputs
        
        try:
            # เรียกใช้คลาส Locomotive เพื่อดึงข้อมูลออกมา
            locomotive = Locomotive()
            output_name, extracted_data = locomotive.extract(stego_file_paths, private_key_path, password)
            
            # เมื่อได้ข้อมูลมาแล้ว ให้จัดการเซฟและแสดงผล
            self.handle_extracted_data(output_name, extracted_data)
            
        except Exception as e:
            # ดักจับ Error (เช่น รหัสผ่านผิด, ไฟล์เสีย, หา LOCO ไม่เจอ)
            QMessageBox.critical(self, "Extraction Failed", f"Failed to extract data:\n{str(e)}")

    def handle_extracted_data(self, default_name: str, data: bytes):
        is_text = False
        text_content = ""

        # 1. ลองพยายามถอดรหัสเป็นข้อความ (รองรับทั้ง Text Input และไฟล์นามสกุล .txt)
        try:
            text_content = data.decode('utf-8')
            is_text = True
        except UnicodeDecodeError:
            is_text = False # ถอดไม่ได้ แปลว่าเป็นไฟล์ Binary

        if is_text:
            # นำข้อความไปโชว์ในช่อง Result Area
            self.payload_text_area.setPlainText(text_content)

            # เช็คว่าไฟล์ที่ได้มา คือ "Text จากช่อง Input" ที่เราจำลองไว้หรือไม่
            if "secret_message" in default_name:
                QMessageBox.information(self, "Success", "Text extracted successfully!\nYou can read it in the Extraction Result box.")
                
                # ถามผู้ใช้ว่าต้องการเซฟข้อความนี้เป็นไฟล์ .txt เก็บไว้ด้วยไหม?
                reply = QMessageBox.question(
                    self, 
                    "Save Text", 
                    "Do you want to save this text as a .txt file?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.save_file_dialog(default_name, data)
            else:
                # กรณีแนบไฟล์ประเภท .txt เข้ามาตอน Embed
                QMessageBox.information(self, "Success", f"Text file '{default_name}' extracted!\nA preview is available in the result box.")
                self.save_file_dialog(default_name, data)

        else:
            # 2. กรณีเป็นไฟล์ประเภทอื่นๆ (Binary file เช่น ZIP, PDF, EXE)
            self.payload_text_area.setPlainText(
                f"[ Binary file extracted successfully ]\n"
                f"File Name: {default_name}\n"
                f"Size: {len(data):,} bytes\n"
            )
            QMessageBox.information(self, "Success", f"Binary file '{default_name}' extracted successfully!")
            self.save_file_dialog(default_name, data)

    def save_file_dialog(self, default_name: str, data: bytes):
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Extracted File",
            default_name,
            "All Files (*)"
        )
        
        if save_path:
            try:
                with open(save_path, 'wb') as f:
                    f.write(data)
                QMessageBox.information(self, "Success", "File saved successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file:\n{str(e)}")