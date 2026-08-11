from pathlib import Path
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout

from src.core.stego.lsb_pp import LSBPP
from src.gui.components.files_drop import FileDropWidget
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, create_icon_state
from src.gui.components.key_validation import KeyValidationLabel, inspect_private_key
from src.gui.components.key_source import KeySourceWidget
from src.gui.components.password_visibility import add_password_visibility_toggle
from src.gui.components.result_viewers import PayloadResultViewer
from src.gui.components.toggle_switch import ToggleSwitch
from src.gui.components.visibility_stack import VisibilityStack
from src.gui.components.worker import FunctionWorker
from src.gui.services.key_registry import KeyRegistry

ICON_DIR = Path(__file__).parent.parent.parent / "assets" / "svg"

ICON_SIZE = 14
COLOR_CHECKED_SYM = "#a78bfa"
COLOR_CHECKED_ASYM = "#34D399"

class LSBExtractTab(QFrame):
    def __init__(self, key_registry: KeyRegistry | None = None):
        super().__init__()
        self.key_registry = key_registry
        
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
        left_layout.addWidget(stego_file_card, 1)
        
        # --- Right side - Decryption ---
        right_layout = QVBoxLayout()
        
        # Decryption card
        decryption_card = self.build_decryption_card()
        left_layout.addWidget(decryption_card, 0)
        
        # Add layouts to sub_layout
        sub_layout.addLayout(left_layout, 1)
        sub_layout.addLayout(right_layout, 1)
        
        # Add sub_layout to main_layout
        main_layout.addLayout(sub_layout)
        
        # TODO: LSB Options card (channel select, alpha embed, gradient/entropy/shuffle
        # toggles, etc.) -- shelved, see .claude/notes/lsb-options-plan.md before resuming
        # lsb_options_card = self.build_lsb_options_card()
        # main_layout.addWidget(lsb_options_card)

        # Extraction Result
        self.result_viewer = PayloadResultViewer()
        right_layout.addWidget(self.result_viewer)
        
        # --- Final layout for loading status bar and execute button ---
        final_layout = QHBoxLayout()
        final_layout.setContentsMargins(0, 0, 0, 0)
        
        # Loading & Status Bar
        loading_status_bar = self.build_loading_status_bar()
        final_layout.addWidget(loading_status_bar)
        
        # Execute Extract Data
        self.execute_extract_btn = QPushButton("Extract Data")
        self.execute_extract_btn.setFixedHeight(50)
        self.execute_extract_btn.setObjectName("PrimaryActionBtn")
        final_layout.addWidget(self.execute_extract_btn)
        self.execute_extract_btn.clicked.connect(self.execute_extraction)
        
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
        # Toggle Switch &  Decryption Mode Stack 
        self.decrypt_toggle_switch = ToggleSwitch()
        self.decrypt_stack = VisibilityStack()
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
        
        
        # Add decryption modes to stack
        self.decrypt_stack.addWidget(self.build_symmetric_mode())
        self.decrypt_stack.addWidget(self.build_asymmetric_mode())
        
        
        # Connect toggle switch to stack
        self.decrypt_group.idClicked.connect(self.decrypt_stack.setCurrentIndex)
        self.decrypt_toggle_switch.toggled.connect(self.decrypt_stack.setVisible)
        
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
        self.btn_symmetric.setObjectName("encryptOptionBtn")
        self.btn_symmetric.setProperty("accentColor", "purple")
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
        self.btn_asymmetric.setObjectName("encryptOptionBtn")
        self.btn_asymmetric.setProperty("accentColor", "green")
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
        
        # Password Input
        password_label = QLabel("Password")
        password_label.setObjectName("formLabel")
        
        self.password_input = QLineEdit()
        self.password_input.setObjectName("formInput")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        add_password_visibility_toggle(self.password_input)
        self.password_input.setPlaceholderText("Enter passphrase...")
        
        symmetric_layout.addWidget(password_label)
        symmetric_layout.addWidget(self.password_input)
        
        return symmetric_mode
    
    def build_asymmetric_mode(self):
        asymmetric_mode = QFrame()
        asymmetric_mode.setObjectName("asymmetricMode")
        
        asymmetric_layout = QVBoxLayout(asymmetric_mode)
        asymmetric_layout.setContentsMargins(0, 0, 0, 8)
        self.private_key_source = KeySourceWidget("private", self.key_registry)
        self.private_key_drop_zone = self.private_key_source.drop_zone
        self.private_key_source.key_selected.connect(self.on_private_key_selected)
        asymmetric_layout.addWidget(self.private_key_source)

        # Password Input
        key_password_label = QLabel("Private Key Password (Optional)")
        key_password_label.setObjectName("formLabel")

        self.key_password_input = QLineEdit()
        self.key_password_input.setObjectName("formInput")
        self.key_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        add_password_visibility_toggle(self.key_password_input)
        self.key_password_input.setPlaceholderText("Enter key password...")
        self.key_password_input.editingFinished.connect(self.validate_selected_private_key)

        asymmetric_layout.addWidget(key_password_label)
        asymmetric_layout.addWidget(self.key_password_input)

        self.private_key_status = KeyValidationLabel()
        asymmetric_layout.addWidget(self.private_key_status)
        
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
    
    
    def execute_extraction(self):
        input_data = self.get_input_data()
        
        if not input_data:
            return
        
        stego_file_path, private_key_path, password = input_data
        lsbpp = LSBPP()
        self.extract_worker = FunctionWorker(
            lsbpp.extract,
            stego_file_path, 
            private_key_path, 
            password,
            report_progress=True,
        )
        self.extract_worker.progress.connect(self.on_update_progess)
        self.extract_worker.done.connect(self.on_extract_done)
        self.execute_extract_btn.setEnabled(False)
        self.extract_worker.start()
    
    def get_input_data(self) -> tuple[str, str, str] | bool:
        # 1. เช็คความถูกต้องทั้งหมดก่อน
        if not self.validate_input():
            return False
        
        # 2. เคลียร์ค่ากุญแจให้ว่างเปล่าไว้ก่อน
        password = None
        private_key = None
        
        if not self.decrypt_toggle_switch.isChecked():
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
        if not self.decrypt_toggle_switch.isChecked():
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

            result = self.validate_selected_private_key()
            if not result.valid:
                title = "Private Key Password Required" if result.state == "pending" else "Invalid Private Key"
                QMessageBox.warning(self, title, result.message)
                return False

        return True
    
    # --- Event Handler ---
    def on_stego_file_selected(self, file_path: str):
        if not file_path:
            self.stego_file_path = None
            return
        self.stego_file_path = file_path
        
    def on_private_key_selected(self, file_path: str):
        if not file_path:
            self.private_key_path = None
            self.private_key_status.clear_result()
            return
        self.private_key_path = file_path

        self.validate_selected_private_key()

    def validate_selected_private_key(self):
        if not self.private_key_path:
            self.private_key_status.clear_result()
            return None

        password = self.key_password_input.text() or None
        result = inspect_private_key(self.private_key_path, password)
        self.private_key_status.set_result(result)
        return result
            
    def on_update_progess(self, percent: int, message: str):
        self.status_label.setText(f'Status: {message}')
        self.loading_bar.setValue(percent)
    
    def on_extract_done(self, result):
        self.execute_extract_btn.setEnabled(True) 
        if isinstance(result, dict) and "error" in result:
            QMessageBox.critical(self, "Error", f"Failed to Extract: {result['error']}")
            self.on_update_progess(0, "Ready")
            return
        self.result_viewer.show_text(result)
