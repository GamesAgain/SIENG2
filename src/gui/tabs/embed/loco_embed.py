from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QButtonGroup, QFileDialog, QFrame, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel
from pathlib import Path

from src.core.stego.locomotive import Locomotive
from src.gui.components.files_drop import FileDropWidget, MultiFileDropWidget
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, create_icon_state
from src.gui.components.linked_step_toggle import LinkedStepToggle
from src.gui.components.step_output_picker import StepOutputPicker
from src.gui.components.toggle_switch import ToggleSwitch
from src.gui.components.visibility_stack import VisibilityStack

ICON_DIR = Path(__file__).parent.parent.parent / "assets" / "svg"
ICON_SIZE = 14
COLOR_CHECKED_SYM = "#a78bfa"
COLOR_CHECKED_ASYM = "#34D399"


class LocoEmbedInputs(QFrame):
    """ส่วน 'input' ของ Locomotive embed (locomotive file + payload + encryption)
    แยกออกจาก execute bar เพื่อ reuse ทั้งหน้า Standalone (LocomotiveEmbedTab) และ
    Configurable Pipeline (step config popup/inline) — เปิด API `get_input_data()`"""

    def __init__(self, pipeline_mode: bool = False):
        super().__init__()

        # Locomotive & Payload
        self.locomotive_file_paths: list[str] = None
        self.payload_file_paths: list[str] = None
        self.payload_text = ""
        self.linked_cover_index: list[int] = []  # non-empty = cover มาจาก output ของ step ก่อนหน้า (pipeline_mode) — เลือกได้หลายตัว
        self.linked_payload_index: list[int] = []  # non-empty = payload (file) มาจาก output ของ step ก่อนหน้า — ชนิดไฟล์อะไรก็ได้

        # Encryption
        self.password = ""
        self.public_key_path = None

        # True เมื่อฝังใน Configurable Pipeline step UI จะ โชว์ toggle Manual Upload / Linked from Step
        self.pipeline_mode = pipeline_mode

        self.build_ui()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        sub_layout = QHBoxLayout()

        # --- Left side - Locomotive file ---
        left_layout = QVBoxLayout()
        left_layout.addWidget(self.build_locomotive_file_card())

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

        drop_zone = MultiFileDropWidget("Drop PNG files here or click to browse", "PNG format only (Single file OR Multiple files)", str(ICON_DIR / "photo.svg"), allowed_extensions=[".png"])
        drop_zone.files_changed.connect(self.on_locomotive_file_selected)

        locomotive_file_layout.addWidget(title_container, 0)  # top

        if self.pipeline_mode:
            self.linked_toggle = LinkedStepToggle()
            title_layout.addWidget(self.linked_toggle)

            # สลับระหว่าง drop zone (Manual Upload) กับ StepOutputPicker (Linked from Step)
            # max_selection=None เพราะ Locomotive รับ cover ได้หลายภาพพร้อมกัน
            self.cover_source_stack = VisibilityStack()
            self.cover_source_stack.addWidget(drop_zone)
            self.cover_picker = StepOutputPicker(max_selection=None)
            self.cover_picker.selectionChanged.connect(self.on_cover_link_changed)
            self.cover_source_stack.addWidget(self.cover_picker)
            self.linked_toggle.modeChanged.connect(self.on_cover_link_mode_changed)

            locomotive_file_layout.addWidget(self.cover_source_stack, 1)
        else:
            locomotive_file_layout.addWidget(drop_zone, 1)  # Stretch factor

        return locomotive_file_card

    # --- Linked-from-Step: cover (Configurable Pipeline เท่านั้น) ---
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
        photo_icon = create_icon_pixmap(ICON_DIR / "file.svg", size=16)
        title_icon.setPixmap(photo_icon)

        # Text: Payload File
        title_label = QLabel("Payload File (Secret File)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        if self.pipeline_mode:
            self.payload_linked_toggle = LinkedStepToggle()
            title_layout.addWidget(self.payload_linked_toggle)

        self.payload_tabs = QTabWidget()

        # --- File Tab ---
        file_tab = QFrame()
        file_tab_layout = QVBoxLayout(file_tab)
        file_tab_layout.setContentsMargins(0, 12, 0, 0)

        drop_zone = MultiFileDropWidget("Drop any files or type text", "Any file format (PDF, ZIP, EXE, TXT, ...)", icon_path=str(ICON_DIR / "file-plus.svg"))
        drop_zone.files_changed.connect(self.on_payload_file_selected)
        file_tab_layout.addWidget(drop_zone)

        # --- Text Tab ---
        text_input_tab = QFrame()
        text_edit_layout = QVBoxLayout(text_input_tab)
        text_edit_layout.setContentsMargins(0, 12, 0, 0)

        self.payload_text_area = QPlainTextEdit()
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

        if self.pipeline_mode:
            # สลับระหว่าง payload_tabs (Manual Upload/Text) กับ StepOutputPicker (Linked from Step)
            # max_selection=None เพราะ file_payload รับได้หลายไฟล์ — ไม่จำกัด type (Locomotive ฝังไฟล์อะไรก็ได้)
            self.payload_source_stack = VisibilityStack()
            self.payload_source_stack.addWidget(self.payload_tabs)
            self.payload_picker = StepOutputPicker(max_selection=None)
            self.payload_picker.selectionChanged.connect(self._on_payload_link_changed)
            self.payload_source_stack.addWidget(self.payload_picker)
            self.payload_linked_toggle.modeChanged.connect(self._on_payload_link_mode_changed)

            payload_layout.addWidget(self.payload_source_stack)
        else:
            payload_layout.addWidget(self.payload_tabs)

        return payload_card

    # --- Linked-from-Step: payload (Configurable Pipeline เท่านั้น) ---
    def set_payload_link_candidates(self, candidates: list[dict]):
        self.payload_picker.set_candidates(candidates)

    def _on_payload_link_mode_changed(self, is_linked: bool):
        self.payload_source_stack.setCurrentIndex(1 if is_linked else 0)
        if not is_linked:
            self.linked_payload_index = []
            self.payload_picker.clear_selection()

    def _on_payload_link_changed(self, index: list[int]):
        self.linked_payload_index = index

    def get_linked_payload_index(self) -> list[int]:
        return self.linked_payload_index

    def clear_links(self):
        """เคลียร์ cover + payload link กลับเป็น Manual — page เรียกเวลาลบ step ที่ถูก link ไว้"""
        self.linked_cover_index = []
        self.linked_payload_index = []
        if self.pipeline_mode:
            self.linked_toggle.set_linked(False)
            self.cover_source_stack.setCurrentIndex(0)
            self.cover_picker.clear_selection()
            self.payload_linked_toggle.set_linked(False)
            self.payload_source_stack.setCurrentIndex(0)
            self.payload_picker.clear_selection()

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

        # --- Password Input ---
        password_label = QLabel("Password")
        password_label.setContentsMargins(0, 0, 0, 0)
        password_label.setObjectName("formLabel")

        self.password_input = QLineEdit()
        self.password_input.setObjectName("formInput")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter passphrase...")

        symmetric_layout.addWidget(password_label)
        symmetric_layout.addWidget(self.password_input)

        # --- Confirm Password Input ---
        confirm_label = QLabel("Confirm Password")
        confirm_label.setContentsMargins(0, 0, 0, 0)
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

    # --- Input API ---
    def validate_inputs(self):
        """Validate all inputs before embedding"""

        # 1. เช็ค Locomotive File (อัปโหลดเอง หรือ linked จาก step ก่อนหน้า อย่างใดอย่างหนึ่ง)
        if not self.locomotive_file_paths and not self.linked_cover_index:
            QMessageBox.warning(self, "Validation Error", "Please select a locomotive file")
            return False

        # 2. เช็ค Payload — linked จาก step ก่อนหน้า หรือเช็คตาม Tab ที่เปิดอยู่ (manual)
        if not self.linked_payload_index:
            active_tab = self.payload_tabs.currentIndex()  # 0 = File Tab, 1 = Text Tab
            if active_tab == 0:
                if not self.payload_file_paths:
                    QMessageBox.warning(self, "Validation Error", "Please select a payload file")
                    return False
            elif active_tab == 1:
                if not self.payload_text_area.toPlainText().strip():  # ถ้าพิมพ์แต่ช่องว่าง หรือไม่พิมพ์อะไรเลย
                    QMessageBox.warning(self, "Validation Error", "Please enter some text to hide")
                    self.payload_text_area.setFocus()
                    return False

        # 3. เช็คว่าได้เปิดการเข้ารหัสไหม
        if not self.encrypt_toggle_switch.isChecked():
            return True

        # 4. เช็คโหมด Symmetric (Password)
        if self.btn_symmetric.isChecked():
            password = self.password_input.text()
            if not password:
                QMessageBox.warning(self, "Validation Error", "Please enter a password for encryption.")
                self.password_input.setFocus()
                return False

        # 5. เช็คโหมด Asymmetric (Public Key)
        elif self.btn_asymmetric.isChecked():
            if not hasattr(self, 'public_key_path') or not self.public_key_path:
                QMessageBox.warning(self, "Validation Error", "Please drop a Public Key file for asymmetric encryption.")
                return False

        return True

    def get_input_data(self):
        if not self.validate_inputs():
            return False

        # ดึงข้อมูล Payload ตาม Tab
        active_tab = self.payload_tabs.currentIndex()

        file_index = 0
        raw_text_index = 1

        payload_files = self.payload_file_paths if active_tab == file_index else None
        raw_text = self.payload_text_area.toPlainText() if active_tab == raw_text_index else None

        password = None
        public_key_path = None

        if self.encrypt_toggle_switch.isChecked():
            if self.btn_symmetric.isChecked():
                password = self.password_input.text()
            elif self.btn_asymmetric.isChecked():
                public_key_path = self.public_key_path

        return self.locomotive_file_paths, payload_files, raw_text, public_key_path, password

    # --- Event Handlers ---
    def on_locomotive_file_selected(self, file_paths):
        """Handle locomotive file selection"""
        if file_paths:
            self.locomotive_file_paths = file_paths
        else:
            self.locomotive_file_paths = None

    def on_payload_file_selected(self, file_paths):
        """Handle payload file selection"""
        if file_paths:
            self.payload_file_paths = file_paths
        else:
            self.payload_file_paths = None

    def on_public_key_selected(self, file_paths):
        """Handle public key selection"""
        if file_paths:
            self.public_key_path = file_paths
        else:
            self.public_key_path = None


class LocomotiveEmbedTab(QFrame):
    """หน้า Standalone ของ Locomotive — ห่อ LocoEmbedInputs + execute bar
    (status + ปุ่ม Embed Data) ที่รัน engine + เซฟไฟล์เองในโหมดนี้"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 11, 4, 4)

        # ส่วน input (reuse ร่วมกับ Configurable Pipeline)
        self.inputs = LocoEmbedInputs()
        main_layout.addWidget(self.inputs)

        # --- Final layout for loading status bar and execute button ---
        execution_box = self.build_execution_box()
        main_layout.addLayout(execution_box, 1)

    def build_execution_box(self):
        execution_box = QHBoxLayout()
        execution_box.setContentsMargins(0, 0, 0, 0)

        # Loading & Status Bar
        loading_status_bar = self.create_loading_status_bar()
        execution_box.addWidget(loading_status_bar)

        # Execute Embed Data
        execute_embed_btn = QPushButton("Embed Data")
        execute_embed_btn.setFixedHeight(50)
        execute_embed_btn.setObjectName("PrimaryActionBtn")

        execute_embed_btn.clicked.connect(self.execute_embedding)
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

    def execute_embedding(self):
        """Execute the embedding process"""
        inputs = self.inputs.get_input_data()
        if not inputs:
            return

        locomotive_file_paths, payload_file_paths, raw_text, public_key_path, password = inputs

        try:
            locomotive = Locomotive()

            stego_files = locomotive.embed(
                cover_image_paths=locomotive_file_paths,
                file_paths=payload_file_paths,
                raw_text=raw_text,
                public_key_path=public_key_path,
                password=password
            )

            is_saved = self.save_stego_images(stego_files)
            if not is_saved:
                return

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to embed: {str(e)}")

    def save_stego_images(self, output_files: list[tuple[str, bytes]]):

        if not output_files:
            return

        # ไฟล์เดียว
        if len(output_files) == 1:

            filename, data = output_files[0]

            save_path, _ = QFileDialog.getSaveFileName(self, "Save File", filename, "PNG Files (*.png)")

            if not save_path:
                return

            try:
                with open(save_path, 'wb') as f:
                    f.write(data)

                # แจ้งเตือนเมื่อเขียนไฟล์เสร็จแล้ว
                QMessageBox.information(self, "Success", f"Data embedded successfully!\nSaved to:\n{save_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file: {str(e)}")

            return

        # หลายไฟล์
        save_dir = QFileDialog.getExistingDirectory(self, "Select Save Folder")

        # 1. เช็คก่อนว่าผู้ใช้กดยกเลิกไหม ถ้ากดให้จบการทำงาน
        if not save_dir:
            return

        save_dir = Path(save_dir)

        try:
            # 2. วนลูปเซฟไฟล์ให้เสร็จทุกไฟล์ก่อน
            for filename, data in output_files:
                output_path = save_dir / filename

                with open(output_path, 'wb') as f:
                    f.write(data)

            # 3. แจ้งเตือนเมื่อทุกอย่างเซฟเสร็จสมบูรณ์
            QMessageBox.information(self, "Success", f"Data embedded successfully!\nSaved {len(output_files)} files to:\n{save_dir}")
            print(f"Saved successfully at: {save_dir}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save files: {str(e)}")