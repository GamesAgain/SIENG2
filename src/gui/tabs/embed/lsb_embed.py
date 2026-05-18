from pathlib import Path
from PIL import Image
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QStackedWidget, QTabWidget, QVBoxLayout

from src.core.stego.lsb_pp import LSBPP
from src.gui.components.file_drop import FileDropWidget
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, create_icon_state, format_file_size
from src.gui.components.toggle_switch import ToggleSwitch

ICON_DIR = Path(__file__).parent.parent.parent / "assets" / "svg"

ICON_SIZE = 14
COLOR_CHECKED_SYM = "#a78bfa"
COLOR_CHECKED_ASYM = "#34D399"

class LSBEmbedTab(QFrame):
    def __init__(self):
        super().__init__()
        
        # Cover & Payload
        self.cover_file_path = None
        self.payload_text = ""
        self.payload_file_path = None
        
        # Encryption
        self.password = ""
        self.public_key_path = None
        
        self.init_ui()
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 11, 4, 4)
        
        sub_layout = QHBoxLayout()
        
        # --- Left side - Cover file ---
        left_layout = QVBoxLayout()
        
        # Cover file card
        cover_file_card = self.build_cover_file_card()
        left_layout.addWidget(cover_file_card)
        
        # --- Right side - Payload and Encryption ---
        right_layout = QVBoxLayout()
        
        # Payload card
        payload_card = self.build_payload_card()
        right_layout.addWidget(payload_card)
        
        # Encryption card
        encryption_card = self.build_encryption_card()
        right_layout.addWidget(encryption_card)

        # --- Add layouts to sub_layout ---
        sub_layout.addLayout(left_layout, 1)
        sub_layout.addLayout(right_layout, 1)
        
        main_layout.addLayout(sub_layout) 
        
        # LSB Options card
        lsb_options_card = self.build_lsb_options_card()
        main_layout.addWidget(lsb_options_card)  
        
        main_layout.addStretch()
        
        # --- Final layout for loading status bar and execute button ---
        final_layout = QHBoxLayout()
        final_layout.setContentsMargins(0, 0, 0, 0)
        
        # Loading & Status Bar
        loading_status_bar = self.build_loading_status_bar()
        final_layout.addWidget(loading_status_bar)
        
        # Execute Embed Data
        execute_embed_btn = QPushButton("Embed Data")
        execute_embed_btn.setFixedHeight(50)
        execute_embed_btn.setObjectName("EmbedBtn")
        
        execute_embed_btn.clicked.connect(self.execute_embedding)
        final_layout.addWidget(execute_embed_btn)
        
        main_layout.addLayout(final_layout)
        
        
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
        key_drop_zone = FileDropWidget("Drop public key here or click to browse", "Public key file (.pem, .der, .ssh)", icon_path= str(ICON_DIR / "file-text-shield.svg"), allowed_extensions=["pem", "der", "ssh"])
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
        self.btn_symmetric.setObjectName("passwordBtn")
        self.btn_symmetric.setCheckable(True)
        self.btn_symmetric.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # ADD ICON
        symmetric_icon_path = ICON_DIR / "key.svg"
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
        asymmetric_icon_path = ICON_DIR / "lock.svg"
        if asymmetric_icon_path.exists():
            configurable_icon = create_icon_state(str(asymmetric_icon_path), ICON_SIZE, color_checked=COLOR_CHECKED_ASYM)
            self.btn_asymmetric.setIcon(configurable_icon)
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
        
        drop_zone = FileDropWidget("Drop PNG file here or click to browse", "PNG format only", str(ICON_DIR / "photo.svg"), allowed_extensions=["png"])
        drop_zone.file_selected.connect(self.on_cover_file_selected)
        
        cover_file_layout.addWidget(title_container, 0) # top 
        cover_file_layout.addWidget(drop_zone, 1) # Stretch factor
        
        return cover_file_card
    
    def execute_embedding(self):
        # Get input data
        
        if not self.get_input_data():
            return
        
        cover_file_path, payload_text, password, public_key_path = self.get_input_data()
        
        try:
            lsbpp = LSBPP()
            stego_img, stego_name = lsbpp.embed(cover_file_path, payload_text, public_key_path, password)
            
            is_saved = self.save_stego_image(stego_img, stego_name)
            if not is_saved:
                return
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to embed: {str(e)}")
        
    
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
        # 1. เช็ค Cover File
        if not hasattr(self, 'cover_file_path') or not self.cover_file_path:
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
                self.password_input.setFocus() # เด้งไปรอให้พิมพ์
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
    
    def save_stego_image(self, stego_img: Image.Image, default_name: str) -> bool:
        try:
            
            save_path, _ = QFileDialog.getSaveFileName(
                self, 
                "Save Stego Image",     # ชื่อหน้าต่าง
                default_name,           # ชื่อไฟล์ตั้งต้นที่ดึงมาจาก LSB++
                "PNG Images (*.png)"    # ล็อกนามสกุลไฟล์เพื่อไม่ให้พิกเซลเสียหาย
            )
            
            if save_path:
                stego_img.save(save_path)
                
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
    def on_cover_file_selected(self, file_path: str):
        self.cover_file_path = file_path
        
    def on_public_key_selected(self, file_path: str):
        self.public_key_path = file_path
        
    def on_payload_file_selected(self, file_path: str):
        self.payload_file_path = file_path 
        
        encodings_to_try = ['utf-8-sig', 'utf-8', 'utf-16', 'cp874']
        payload_text = ""
        read_success = False
        last_error = None
        
        for encoding in encodings_to_try:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    payload_text = f.read()
                read_success = True
                break
            except UnicodeDecodeError as e:
                last_error = e
                continue
            except Exception as e:
                last_error = e
                break
                
        if read_success:
            self.payload_text_area.setPlainText(payload_text)
            self.payload_tabs.setCurrentIndex(0) 
        else:
            print(f"Error reading text file: {last_error}")
            self.payload_text_area.clear() 
            self.payload_tabs.setCurrentIndex(1)
            
        
    def on_payload_text_changed(self):
        text = self.payload_text_area.toPlainText()
        text_size_bytes = len(text.encode('utf-8'))
        text_size = format_file_size(text_size_bytes)
        self.capacity_label.setText(f"Capacity: {text_size} / MAX KB")