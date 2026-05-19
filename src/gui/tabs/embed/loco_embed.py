from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QButtonGroup, QFrame, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QStackedWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel
from pathlib import Path

from src.gui.components.file_drop import FileDropWidget
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, create_icon_state
from src.gui.components.multi_file_drop import MultiFileDropWidget
from src.gui.components.toggle_switch import ToggleSwitch

ICON_DIR = Path(__file__).parent.parent.parent / "assets" / "svg"
ICON_SIZE = 14
COLOR_CHECKED_SYM = "#a78bfa"
COLOR_CHECKED_ASYM = "#34D399"

class LocomotiveEmbedTab(QFrame):
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 11, 4, 4)
        
        sub_layout = QHBoxLayout()
        
        # --- Left side - Locomotive file ---
        left_layout = QVBoxLayout()
        
        # Locomotive file card
        locomotive_file_card = self.build_locomotive_file_card()
        left_layout.addWidget(locomotive_file_card)
        
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
        
        # main_layout.addStretch()
        
        # --- Final layout for loading status bar and execute button ---
        execution_box = self.build_execution_box()
        
        main_layout.addLayout(execution_box, 1)
        
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
        # drop_zone.files_changed.connect(self.on_locomotive_file_selected)
        
        locomotive_file_layout.addWidget(title_container, 0) # top 
        locomotive_file_layout.addWidget(drop_zone, 1) # Stretch factor
        
        return locomotive_file_card
    
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
        photo_icon = create_icon_pixmap(ICON_DIR / "file.svg", size=16)
        title_icon.setPixmap(photo_icon)
        
        # Text: Payload File
        title_label = QLabel("Payload File (Secret Files)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        
        self.payload_tabs = QTabWidget()
        
        # --- File Tab ---
        file_tab = QFrame()
        file_tab_layout = QVBoxLayout(file_tab)
        file_tab_layout.setContentsMargins(0, 12, 0, 0)

        drop_zone = MultiFileDropWidget("Drop any files or type text", "Any file format (PDF, ZIP, EXE, TXT, ...)", icon_path=str(ICON_DIR / "file-plus.svg"))
        # drop_zone.file_selected.connect(self.on_payload_file_selected)
        drop_zone.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        file_tab_layout.addWidget(drop_zone)
        
        # --- Text Tab ---
        text_input_tab = QFrame()
        text_edit_layout = QVBoxLayout(text_input_tab)
        text_edit_layout.setContentsMargins(0, 12, 0, 0)
        
        self.payload_text_area = QPlainTextEdit()
        # self.payload_text_area.textChanged.connect(self.on_payload_text_changed)
        
        self.payload_text_area.setObjectName("payloadTextArea")
        self.payload_text_area.setPlaceholderText("Enter secret message here...")
        text_edit_layout.addWidget(self.payload_text_area)
        
        # Capacity indicator
        self.capacity_label = QLabel("Size: 0.0 B")
        self.capacity_label.setObjectName("capacityLabel")
        
        text_edit_layout.addWidget(self.capacity_label)
        
        self.payload_tabs.addTab(file_tab, "File Input")
        self.payload_tabs.addTab(text_input_tab, "Text Input")
          
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
    
    def build_symmetric_mode(self):
        symmetric_mode = QFrame()
        symmetric_mode.setObjectName("symmetricMode")
        
        symmetric_layout = QVBoxLayout(symmetric_mode)
        
        # --- Password Input ---
        password_label = QLabel("Password")
        password_label.setObjectName("formLabel")
        
        self.password_input = QLineEdit()
        self.password_input.setObjectName("formInput")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter passphrase...")
        
        symmetric_layout.addWidget(password_label)
        symmetric_layout.addWidget(self.password_input)
        
        # --- Confirm Password Input ---
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
        # key_drop_zone.file_selected.connect(self.on_public_key_selected)
        asymmetric_layout.addWidget(key_drop_zone)
        
        return asymmetric_mode
    
    def build_execution_box(self):
        execution_box = QHBoxLayout()
        execution_box.setContentsMargins(0, 0, 0, 0)
        
        # Loading & Status Bar
        loading_status_bar = self.create_loading_status_bar()
        execution_box.addWidget(loading_status_bar)
        
        # Execute Embed Data
        execute_embed_btn = QPushButton("Embed Data")
        execute_embed_btn.setFixedHeight(50)
        execute_embed_btn.setObjectName("EmbedBtn")
        
        # execute_embed_btn.clicked.connect(self.execute_embedding)
        execution_box.addWidget(execute_embed_btn)
        
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
