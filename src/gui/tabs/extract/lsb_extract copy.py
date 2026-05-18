from pathlib import Path
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout

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
        main_layout.addWidget(lsb_options_card)  
        
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
        
        execute_extract_btn.clicked.connect(self.execute_extraction)
        final_layout.addWidget(execute_extract_btn)
        
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
        
        # Connect toggle switch to stack
        self.decrypt_group.idClicked.connect(self.encrypt_stack.setCurrentIndex)
        self.encrypt_toggle_switch.toggled.connect(self.encrypt_stack.setVisible)
        
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
        symmetric_layout.setContentsMargins(0, 12, 0, 0)
        
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
        password_label = QLabel("Private Key Password (Optional)")
        password_label.setObjectName("formLabel")
        
        self.password_input = QLineEdit()
        self.password_input.setObjectName("formInput")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter key password...")
        
        asymmetric_layout.addWidget(password_label)
        asymmetric_layout.addWidget(self.password_input)
        
        return asymmetric_mode
    
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
    
    # --- Event Handler ---
    def on_stego_file_selected(self, file_path: str):
        self.stego_file_path = file_path
        
    def on_private_key_selected(self, file_path: str):
        self.private_key_path = file_path

