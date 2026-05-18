from pathlib import Path
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout

from src.core.stego.lsb_pp import LSBPP
from src.gui.components.file_drop import FileDropWidget
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, create_icon_state
from src.gui.components.toggle_switch import ToggleSwitch

ICON_DIR = Path(__file__).parent.parent.parent / "assets" / "svg"

ICON_SIZE = 14
COLOR_CHECKED_SYM = "#a78bfa"
COLOR_CHECKED_ASYM = "#34D399"

class LSBExtractTab(QFrame):
    def __init__(self):
        super().__init__()
        
        # Stego file
        self.stego_file_path = None
        
        # Decryption
        self.password = ""
        self.private_key_path = None
        
        self.init_ui()
        
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 11, 4, 4)
        
        sub_layout = QHBoxLayout()
        
        # --- Left side - Stego file ---
        left_layout = QVBoxLayout()
        
        # Stego file card
        stego_file_card = self.build_stego_file_card()
        left_layout.addWidget(stego_file_card)
        
        # --- Right side - Decryption ---
        right_layout = QVBoxLayout()
        
        # Decryption card
        decryption_card = self.build_decryption_card()
        right_layout.addWidget(decryption_card)
        
        # Add layouts to sub_layout
        sub_layout.addLayout(left_layout)
        sub_layout.addLayout(right_layout)
        
        # Add sub_layout to main_layout
        main_layout.addLayout(sub_layout)
        
        # LSB Options card
        lsb_options_card = self.build_lsb_options_card()
        # main_layout.addWidget(lsb_options_card)  
        
                
        # Extraction Result
        extraction_result = self.build_extraction_result()
        main_layout.addWidget(extraction_result)
        
        # Add spacer
        main_layout.addStretch()
        
        # --- Final layout for loading status bar and execute button ---
        final_layout = QHBoxLayout()
        final_layout.setContentsMargins(0, 0, 0, 0)
        
        # Loading & Status Bar
        loading_status_bar = self.build_loading_status_bar()
        final_layout.addWidget(loading_status_bar)
        
        # Execute Extract Data
        execute_extract_btn = QPushButton("Extract Data")
        execute_extract_btn.setFixedHeight(50)
        execute_extract_btn.setObjectName("ExtractBtn")
        final_layout.addWidget(execute_extract_btn)
        execute_extract_btn.clicked.connect(self.execute_extraction)
        
        main_layout.addLayout(final_layout)
        
        
    def build_stego_file_card(self):
        stego_file_card = QFrame()
        stego_file_card.setObjectName("card")
        add_shadow_effect(stego_file_card)
        
        stego_file_layout = QVBoxLayout(stego_file_card)
        
        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        
        # Icon
        title_icon = QLabel()
        photo_icon = create_icon_pixmap(ICON_DIR / "photo.svg", size=16)
        title_icon.setPixmap(photo_icon)
        
        # Text: Stego File (PNG)
        title_label = QLabel("Stego File (PNG)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        drop_zone = FileDropWidget("Drop PNG file here or click to browse", "PNG format only", str(ICON_DIR / "photo.svg"), allowed_extensions=["png"])
        drop_zone.file_selected.connect(self.on_stego_file_selected)
        
        stego_file_layout.addWidget(title_container, 0) # top 
        stego_file_layout.addWidget(drop_zone, 1) # Stretch factor
        
        return stego_file_card
    
    def build_decryption_card(self):
        decryption_card = QFrame()
        decryption_card.setObjectName("card")
        add_shadow_effect(decryption_card)
        
        decryption_layout = QVBoxLayout(decryption_card)
        decryption_layout.setContentsMargins(11, 11, 11, 2)
        decryption_layout.setSpacing(6)
        
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
        title_label = QLabel("Decryption Options")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        encrypt_selection = self.build_decrypt_selection()
        
        # Encryption Mode Stack 
        self.encrypt_stack = QStackedWidget()
        
        
        # Add encryption modes to stack
        self.encrypt_stack.addWidget(self.build_symmetric_mode())
        self.encrypt_stack.addWidget(self.build_asymmetric_mode())
        self.encrypt_stack.addWidget(self.build_disabled_mode())
        
        
        # Connect toggle switch to stack
        self.encrypt_toggle_switch.toggled.connect(self.on_decryption_toggled)
        self.decrypt_group.idClicked.connect(self.encrypt_stack.setCurrentIndex)
        
        title_layout.addWidget(encrypt_selection)
        decryption_layout.addWidget(title_container)
        decryption_layout.addWidget(self.encrypt_stack)
        
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
        self.btn_asymmetric = QPushButton("Private Key")
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
        quide_layout = QVBoxLayout(guide_box)
        quide_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        quide_layout.setContentsMargins(10, 10, 10, 10)
        quide_layout.setSpacing(4)
        
        
        # Icon label
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setMinimumSize(1, 1)
        icon_label.setPixmap(create_icon_pixmap(str(ICON_DIR / "arrow-big-down-lines.svg"), size=42))
        quide_layout.addWidget(icon_label)
        
        # Text labels
        main_label = QLabel("Enter password to extract hidden data")
        main_label.setObjectName("mainLabel")
        main_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        quide_layout.addWidget(main_label)
        
        symmetric_layout.addWidget(guide_box)
        
        quide_layout.setSpacing(20)
        

        
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
        disabled_layout.setContentsMargins(0, 0, 0, 12)
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
    
    def build_loading_status_bar(self):
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
    
    
    def execute_extraction(self):
        input_data = self.get_input_data()
        
        if not input_data:
            return
        
        stego_file_path, private_key_path, password = input_data
        try:
            lsbpp = LSBPP()
            message = lsbpp.extract(stego_file_path, private_key_path, password)
            self.payload_text_area.setPlainText(message)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to Extract: {str(e)}")
    
    def get_input_data(self) -> tuple[str, str, str] | bool:
        # 1. เช็คความถูกต้องทั้งหมดก่อน
        if not self.validate_input():
            return False
        
        # 2. เคลียร์ค่ากุญแจให้ว่างเปล่าไว้ก่อน
        password = None
        private_key = None
        
        if not self.encrypt_toggle_switch.isChecked():
            return self.stego_file_path, private_key, password
        
        # 3. แก้ไข: ดึงค่าให้ถูกช่องกับโหมดที่เปิดใช้งานอยู่
        if self.btn_symmetric.isChecked():
            password = self.password_input.text() # ดึงช่องของ Symmetric
            
        elif self.btn_asymmetric.isChecked():
            private_key = self.private_key_path
            password = self.key_password_input.text() # ดึงช่องของ Asymmetric (ถ้ามี)
            
            # แปลง string ว่างให้เป็น None ถ้าผู้ใช้ไม่ได้กรอกรหัสผ่านสำหรับ Private Key
            if not password:
                password = None 
            
        return self.stego_file_path, private_key, password
    
    def validate_input(self):
        # 1. เช็ค Stego File
        if not hasattr(self, 'stego_file_path') or not self.stego_file_path:
            QMessageBox.warning(self, "Validation Error", "Please select a Stego PNG file.")
            return False
                      
        # 2. เช็คว่าได้เปิดการถอดรหัสไหม
        if not self.encrypt_toggle_switch.isChecked():
            return True

        # 3. เช็คโหมด Symmetric (Password)
        if self.btn_symmetric.isChecked():
            password = self.password_input.text()
            
            if not password:
                QMessageBox.warning(self, "Validation Error", "Please enter a password for decryption.")
                self.password_input.setFocus() 
                return False

        # 4. เช็คโหมด Asymmetric (Public Key)
        elif self.btn_asymmetric.isChecked():
            if not hasattr(self, 'private_key_path') or not self.private_key_path:
                QMessageBox.warning(self, "Validation Error", "Please drop a Private Key file for asymmetric decryption.")
                return False

        return True
    
    # --- Event Handler ---
    def on_stego_file_selected(self, file_path: str):
        self.stego_file_path = file_path
        
    def on_private_key_selected(self, file_path: str):
        self.private_key_path = file_path
        
    def on_decryption_toggled(self, checked: bool):
        # 1. จัดการปุ่ม Password และ Private Key (โชว์/ซ่อน/ทำให้เป็นสีเทา)
        self.btn_symmetric.setEnabled(checked)
        self.btn_asymmetric.setEnabled(checked)
        
        # 2. จัดการหน้า Stack ที่จะแสดง
        if checked:
            # ถ้าเปิด Toggle: ให้กลับไปโชว์หน้าที่ถูกเลือกไว้ล่าสุดใน ButtonGroup (0 หรือ 1)
            current_checked_id = self.decrypt_group.checkedId()
            if current_checked_id != -1:
                self.encrypt_stack.setCurrentIndex(current_checked_id)
        else:
            self.encrypt_stack.setCurrentIndex(2)
