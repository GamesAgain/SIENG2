from pathlib import Path

from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QScrollArea,
    QStackedWidget, QTabWidget, QVBoxLayout)
from PyQt6.QtCore import pyqtSignal

from src.core.stego.locomotive import PNG_SIGNATURE
from src.core.configurable.drafts import LocomotiveInputsDraft
from src.core.configurable.link import is_linked
from src.core.configurable.step_output import StepOutputInfo
from src.gui.components.gui_utils import add_password_visibility_toggle, add_shadow_effect, create_icon_pixmap, format_file_size
from src.gui.components.widgets.files_drop import MultiFileDropWidget
from src.gui.components.widgets.key_source import KeySourceWidget
from src.gui.components.widgets.key_validation import KeyValidationLabel, inspect_public_key
from src.gui.components.widgets.selection_toggle import SelectionToggle
from src.gui.components.widgets.toggle_switch import ToggleSwitch
from src.gui.components.widgets.visibility_stack import VisibilityStack
from src.gui.features.embed.configurable.widgets.step_output_picker import StepOutputPicker
from src.gui.services.key_registry import KeyRegistry
from src.path import svg_path

ICON_SIZE = 16
COLOR_CHECKED_SYM = "#a78bfa"
COLOR_CHECKED_ASYM = "#34D399"

class LocomotiveInputForm(QFrame):

    draft_status = pyqtSignal(bool)

    def __init__(self, key_registry: KeyRegistry = None, is_config: bool = False, parent = None):
        super().__init__(parent)

        self.key_registry = key_registry
        self.is_config = is_config

        # setup inputs (covers / payload files live in the drop zones)
        self.public_key_path = None
        self.cover_links: list = []  # the picked Previous Outputs (StepOutput); only used while that mode is open
        self.payload_links: list = []  # the same for the payload files
        self.output_infos: dict = {}  # StepOutput -> StepOutputInfo (the outputs the page offers)

        self.setup_ui()

    # --- UI construction ---
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 11, 0, 0)

        sub_layout = QHBoxLayout()

        # --- Left side - Locomotive (cover) file Card ---
        left_layout = QVBoxLayout()
        left_layout.addWidget(self.build_locomotive_file_card())

        # --- Right side - Payload and Encryption Cards ---
        right_widget = QFrame()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.build_payload_card(), 1)
        right_layout.addWidget(self.build_encryption_card())

        # Make right side scrollable
        right_scroll = QScrollArea()
        right_scroll.setObjectName("transparentScroll")
        right_scroll.setWidgetResizable(True)
        right_scroll.setWidget(right_widget)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)

        # Left:Right is 1:1 ratio
        sub_layout.addLayout(left_layout, 1)
        sub_layout.addWidget(right_scroll, 1)

        main_layout.addLayout(sub_layout)

    def build_locomotive_file_card(self) -> QFrame:
        locomotive_file_card = QFrame()
        locomotive_file_card.setObjectName("card")
        add_shadow_effect(locomotive_file_card)

        locomotive_file_layout = QVBoxLayout(locomotive_file_card)
        locomotive_file_layout.setContentsMargins(10, 10, 10, 10)

        title_container = QFrame()
        title_layout = QHBoxLayout(title_container)

        # Icon
        title_icon = QLabel()
        photo_icon = create_icon_pixmap(svg_path("photo.svg"), size=ICON_SIZE)
        title_icon.setPixmap(photo_icon)

        # Text: Locomotive File (PNGs)
        title_label = QLabel("Locomotive File (PNGs)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.cover_mode_toggle = SelectionToggle(
            [
                {
                    "text": "Manual File",
                    "value": "manual",
                    "variant": "source",
                },
                {
                    "text": "Previous Output",
                    "value": "previous",
                    "variant": "source",
                },
            ])

        self.cover_mode_toggle.mode_changed.connect(self.on_cover_mode_changed)

        drop_zone = MultiFileDropWidget(
            text="Drop PNG files here or click to browse",
            sub_text="Supports one or multiple PNG files",
            icon_path=str(svg_path("photo.svg")),
            allowed_extensions=[".png"],
        )

        self.cover_drop_zone = drop_zone
        drop_zone.files_changed.connect(self.on_covers_changed)

        self.cover_source_stack = QStackedWidget()
        self.cover_source_stack.addWidget(drop_zone)
        self.output_picker = StepOutputPicker(multi_select=True)
        self.output_picker.selections_changed.connect(self.on_cover_outputs_selected)
        self.cover_source_stack.addWidget(self.output_picker)

        self.cover_summary_label = QLabel("Selected: 0 PNGs")
        self.cover_summary_label.setObjectName("capacityLabel")

        locomotive_file_layout.addWidget(title_container)
        locomotive_file_layout.addWidget(self.cover_mode_toggle)
        self.cover_mode_toggle.setVisible(self.is_config) # Standalone: hidden, Configurable: shown
        locomotive_file_layout.addWidget(self.cover_source_stack, 1)
        locomotive_file_layout.addWidget(self.cover_summary_label)

        return locomotive_file_card

    def build_payload_card(self) -> QFrame:
        payload_card = QFrame()
        payload_card.setObjectName("card")
        add_shadow_effect(payload_card)

        payload_layout = QVBoxLayout(payload_card)

        title_container = QFrame()
        title_layout = QHBoxLayout(title_container)

        # Icon
        title_icon = QLabel()
        file_icon = create_icon_pixmap(svg_path("file.svg"), size=ICON_SIZE)
        title_icon.setPixmap(file_icon)

        # Text: Payload File (Secret File)
        title_label = QLabel("Payload File (Secret File)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.payload_tabs = QTabWidget()
        self.payload_tabs.setObjectName("siengTabs")

        # --- File Input (default tab) ---
        file_tab = QFrame()
        file_layout = QVBoxLayout(file_tab)
        file_layout.setContentsMargins(0, 12, 0, 0)

        self.payload_mode_toggle = SelectionToggle(
            [
                {
                    "text": "Manual File",
                    "value": "manual",
                    "variant": "source",
                },
                {
                    "text": "Previous Output",
                    "value": "previous",
                    "variant": "source",
                },
            ])

        self.payload_mode_toggle.mode_changed.connect(self.on_payload_source_mode_changed)

        self.payload_file_drop_zone = MultiFileDropWidget(
            text="Drop files here or click to browse",
            sub_text="Any file format (PDF, ZIP, TXT, ...)",
            icon_path=str(svg_path("file-plus.svg")),
            allowed_extensions="*",
        )
        # Keep the preview readable; the file list adds its own height below it.
        self.payload_file_drop_zone.drop_zone.setMinimumHeight(115)
        self.payload_file_drop_zone.files_changed.connect(self.on_payload_files_changed)

        self.payload_source_stack = QStackedWidget()
        self.payload_source_stack.addWidget(self.payload_file_drop_zone)
        self.payload_output_picker = StepOutputPicker(multi_select=True)
        self.payload_output_picker.selections_changed.connect(self.on_payload_outputs_selected)
        self.payload_source_stack.addWidget(self.payload_output_picker)

        self.payload_file_summary_label = QLabel("Files: 0 · Total: 0 B")
        self.payload_file_summary_label.setObjectName("capacityLabel")

        file_layout.addWidget(self.payload_mode_toggle)
        self.payload_mode_toggle.setVisible(self.is_config) # Standalone: hidden, Configurable: shown
        file_layout.addWidget(self.payload_source_stack, 1)
        file_layout.addWidget(self.payload_file_summary_label)

        # --- Text Input ---
        text_tab = QFrame()
        text_layout = QVBoxLayout(text_tab)
        text_layout.setContentsMargins(0, 12, 0, 0)

        self.payload_text_area = QPlainTextEdit()
        self.payload_text_area.setObjectName("payloadTextArea")
        self.payload_text_area.setPlaceholderText("Enter secret message here...")
        self.payload_text_area.textChanged.connect(self.on_payload_text_changed)

        self.text_size_label = QLabel("Size: 0 B")
        self.text_size_label.setObjectName("capacityLabel")

        text_layout.addWidget(self.payload_text_area, 1)
        text_layout.addWidget(self.text_size_label)

        self.payload_tabs.addTab(file_tab, "File Input")
        self.payload_tabs.addTab(text_tab, "Text Input")
        # Connect after addTab: the first addTab emits currentChanged while the form is still being built.
        self.payload_tabs.currentChanged.connect(self.on_payload_mode_changed)

        payload_layout.addWidget(title_container)
        payload_layout.addWidget(self.payload_tabs, 1)

        return payload_card

    def build_encryption_card(self) -> QFrame:
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
        shield_icon = create_icon_pixmap(svg_path("shield-lock.svg"), COLOR_CHECKED_SYM, ICON_SIZE)
        title_icon.setPixmap(shield_icon)

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
        self.encrypt_toggle_switch.toggled.connect(self.update_draft_status)

        title_layout.addWidget(encrypt_selection)
        encryption_layout.addWidget(title_container)
        encryption_layout.addWidget(self.encrypt_stack)

        return encryption_card

    def build_encrypt_selection(self) -> SelectionToggle:
        self.encrypt_mode_toggle = SelectionToggle([
            {
                "text": "Password",
                "value": "password",
                "variant": "password",
                "color_checked": COLOR_CHECKED_SYM,
                "icon_path": svg_path("key.svg"),
                "icon_size": 14,
            },
            {
                "text": "Public Key",
                "value": "public_key",
                "variant": "public_key",
                "color_checked": COLOR_CHECKED_ASYM,
                "icon_path": svg_path("lock.svg"),
                "icon_size": 14,
            },
        ])
        self.encrypt_mode_toggle.setProperty("variant", "encryption")
        return self.encrypt_mode_toggle

    def build_symmetric_mode(self) -> QFrame:
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

        self.password_input.textChanged.connect(self.update_draft_status)
        self.confirm_input.textChanged.connect(self.update_draft_status)

        return symmetric_mode

    def build_asymmetric_mode(self) -> QFrame:
        asymmetric_mode = QFrame()
        asymmetric_layout = QVBoxLayout(asymmetric_mode)
        asymmetric_layout.setContentsMargins(0, 0, 0, 8)

        self.public_key_source = KeySourceWidget("public", self.key_registry)
        asymmetric_layout.addWidget(self.public_key_source)

        self.public_key_status = KeyValidationLabel()
        asymmetric_layout.addWidget(self.public_key_status)
        self.public_key_source.key_selected.connect(self.on_public_key_selected)
        return asymmetric_mode

    # --- Input validation and draft status ---
    def link_file_name(self, link) -> str:
        """File name of a Previous Output (a.png, or song.mp3 from a Metadata MP3 step)."""
        info = self.output_infos.get(link)
        return info.display_name if info and info.display_name else f"{link.output_key}.png"

    @staticmethod
    def check_unique_names(paths: list[str], label: str):
        """Raise ValueError if two files share a name (case-insensitive, like Windows)."""
        seen = set()
        for path in paths:
            name = Path(path).name
            if name.casefold() in seen:
                raise ValueError(f"{label} filenames must be unique: '{name}' is selected more than once.")
            seen.add(name.casefold())

    def validate_inputs(self, draft: LocomotiveInputsDraft):
        # Covers (no capacity check: Locomotive appends data after the PNG end marker)
        if not draft.covers:
            raise ValueError("Please select at least one PNG cover image.")

        for cover in draft.covers:
            if is_linked(cover):
                continue  # a Previous Output has no file before the run (it is a PNG: LSB++ and Locomotive make PNGs)
            path = Path(cover)
            try:
                with path.open("rb") as file:
                    header = file.read(len(PNG_SIGNATURE))
            except OSError:
                raise ValueError(f"Cover file is unavailable: {path.name}")
            if header != PNG_SIGNATURE:
                raise ValueError(f"Not a valid PNG file: {path.name}")

        # Output names are "<stem>_loco.png", so cover names must not collide (a Previous Output is named by its key).
        self.check_unique_names([f"{cover.output_key}.png" if is_linked(cover) else cover for cover in draft.covers], "Cover")

        # Payload: only the active tab is checked
        if draft.payload_mode == "files":
            if not draft.payload_files:
                raise ValueError("Please select at least one payload file.")

            for payload in draft.payload_files:
                if is_linked(payload):
                    continue  # a Previous Output has no file before the run
                if not Path(payload).is_file():
                    raise ValueError(f"Payload file is unavailable: {Path(payload).name}")

            # Several files are zipped by name, so duplicates would overwrite each other (a Previous Output is named by its key).
            self.check_unique_names([self.link_file_name(payload) if is_linked(payload) else payload for payload in draft.payload_files], "Payload")

            # One output can be used once: it cannot be a cover and a payload file of the same step
            if {file for file in draft.payload_files if is_linked(file)} & {cover for cover in draft.covers if is_linked(cover)}:
                raise ValueError("The same Previous Output cannot be both a cover and a payload file.")

        elif draft.payload_mode == "text":
            if not draft.payload_text.strip():
                raise ValueError("Please enter a payload message.")

        else:
            raise ValueError("Unsupported payload mode.")

        # Encryption
        if draft.encryption_enabled:
            if draft.encryption_mode == "password":
                if not draft.password:
                    raise ValueError("Please enter a password.")

                if not self.confirm_input.text():
                    raise ValueError("Please confirm your password.")

                if draft.password != self.confirm_input.text():
                    raise ValueError("Password and confirmation do not match.")

            elif draft.encryption_mode == "public_key":
                if not draft.public_key_path:
                    raise ValueError("Please select a valid public key.")
            else:
                raise ValueError("Unsupported encryption mode.")

    def get_inputs(self) -> LocomotiveInputsDraft:
        """Read the form state and raise ValueError if it cannot be embedded."""
        # Only the source that is open counts: the other one is ignored (not saved)
        covers = self.cover_links if self.cover_mode_toggle.mode() == "previous" else self.cover_drop_zone.get_selected_files()
        draft = LocomotiveInputsDraft(
            covers=list(covers),
            payload_mode="files" if self.payload_tabs.currentIndex() == 0 else "text",
            payload_files=list(self.payload_links if self.payload_mode_toggle.mode() == "previous"
                               else self.payload_file_drop_zone.get_selected_files()),
            payload_text=self.payload_text_area.toPlainText(),
            encryption_enabled=self.encrypt_toggle_switch.isChecked(),
            encryption_mode=self.encrypt_mode_toggle.mode(),
            password=self.password_input.text(),
            public_key_path=self.public_key_path,
        )
        self.validate_inputs(draft)
        return draft

    def load_draft(self, draft: LocomotiveInputsDraft) -> None:
        """Fill the form from a saved draft (the reverse of get_inputs)."""
        # 1. Clear the previous files (emits files_changed([]) -> summaries are reset)
        self.cover_mode_toggle.set_mode("manual")
        self.cover_source_stack.setCurrentIndex(0)
        self.payload_mode_toggle.set_mode("manual")
        self.payload_source_stack.setCurrentIndex(0)
        self.cover_drop_zone.clear_all()
        self.payload_file_drop_zone.clear_all()
        self.cover_links = []
        self.output_picker.set_selected_outputs([])
        self.payload_links = []
        self.payload_output_picker.set_selected_outputs([])

        # 2. Payload text and the active payload tab (0 = files, 1 = text)
        self.payload_text_area.setPlainText(draft.payload_text)
        self.payload_tabs.setCurrentIndex(0 if draft.payload_mode == "files" else 1)

        # 3. Encryption: values of the inactive mode are restored too
        self.encrypt_mode_toggle.set_mode(draft.encryption_mode)
        self.on_encrypt_mode_changed(draft.encryption_mode)  # set_mode does not emit mode_changed
        self.encrypt_toggle_switch.setChecked(draft.encryption_enabled)
        self.encrypt_stack.setVisible(draft.encryption_enabled)  # setChecked emits nothing when the value is unchanged
        self.password_input.setText(draft.password)
        self.confirm_input.setText(draft.password)  # the draft keeps one password (it matched when it was saved)

        # public key: select_path -> key_selected -> on_public_key_selected validates it and sets public_key_path
        self.public_key_source.drop_zone.clear_all()
        if draft.public_key_path and Path(draft.public_key_path).is_file():
            self.public_key_source.select_path(draft.public_key_path)

        # 4. Files last: add_files -> files_changed -> summary + draft status
        if any(is_linked(cover) for cover in draft.covers):
            # The page gives the list (set_output_choices) before this; an output that is no longer in it stays unpicked
            self.cover_mode_toggle.set_mode("previous")  # set_mode does not emit mode_changed
            self.cover_source_stack.setCurrentIndex(1)
            self.cover_links = [cover for cover in draft.covers if cover in self.output_infos]
            self.output_picker.set_selected_outputs(self.cover_links)
            self.update_cover_summary()
        else:
            self.cover_drop_zone.add_files(draft.covers)
        if any(is_linked(file) for file in draft.payload_files):
            self.payload_mode_toggle.set_mode("previous")  # set_mode does not emit mode_changed
            self.payload_source_stack.setCurrentIndex(1)
            self.payload_links = [file for file in draft.payload_files if file in self.output_infos]
            self.payload_output_picker.set_selected_outputs(self.payload_links)
            self.update_payload_summary()
        else:
            self.payload_file_drop_zone.add_files(draft.payload_files)

        # 5. A missing file is skipped by the drop zone (the draft is not changed); refresh the status once
        self.update_draft_status()

    def is_draft_ready(self) -> bool:
        try:
            self.get_inputs()
        except ValueError:
            return False
        return True

    def update_draft_status(self):
        self.draft_status.emit(self.is_draft_ready())

    # --- Event handlers ---
    def on_covers_changed(self, files: list[str]):
        self.update_cover_summary()

    def on_cover_outputs_selected(self, references: list):
        self.cover_links = list(references)
        self.update_cover_summary()

    def update_cover_summary(self):
        """Count the covers of the source that is open, then refresh the draft status."""
        if self.cover_mode_toggle.mode() == "previous":
            count = len(self.cover_links)
        else:
            count = len(self.cover_drop_zone.get_selected_files())
        noun = "PNG" if count == 1 else "PNGs"
        self.cover_summary_label.setText(f"Selected: {count} {noun}")
        self.update_draft_status()

    def on_payload_files_changed(self, files: list[str]):
        self.update_payload_summary()

    def on_payload_outputs_selected(self, references: list):
        self.payload_links = list(references)
        self.update_payload_summary()

    def update_payload_summary(self):
        """Count the payload files of the source that is open, then refresh the draft status."""
        if self.payload_mode_toggle.mode() == "previous":
            self.payload_file_summary_label.setText(f"Files: {len(self.payload_links)} · from Previous Output")
        else:
            total_bytes = 0
            files = self.payload_file_drop_zone.get_selected_files()
            for file in files:
                try:
                    total_bytes += Path(file).stat().st_size
                except OSError:
                    continue  # unavailable files are reported by validate_inputs
            self.payload_file_summary_label.setText(f"Files: {len(files)} · Total: {format_file_size(total_bytes)}")
        self.update_draft_status()

    def on_payload_text_changed(self):
        size = len(self.payload_text_area.toPlainText().encode("utf-8"))
        self.text_size_label.setText(f"Size: {format_file_size(size)}")
        self.update_draft_status()

    def on_payload_mode_changed(self, index: int):
        # Readiness depends on the active payload tab (0 = files, 1 = text)
        self.update_draft_status()

    def on_cover_mode_changed(self, mode: str):
        index = 0 if mode == "manual" else 1
        self.cover_source_stack.setCurrentIndex(index)
        self.update_cover_summary()  # the count follows the source that is open

    def set_output_choices(self, choices: list[StepOutputInfo]):
        """The page gives the outputs this step may pick; the form only passes them on."""
        self.output_infos = {info.reference: info for info in choices}
        self.output_picker.set_outputs([info for info in choices if info.media_type == "png"])  # cover = PNG only
        self.payload_output_picker.set_outputs(choices)  # payload: any file (MP3 from a Metadata step too)
        self.cover_links = []  # the lists were rebuilt: nothing is picked in them
        self.payload_links = []

    def on_payload_source_mode_changed(self, mode: str):
        index = 0 if mode == "manual" else 1
        self.payload_source_stack.setCurrentIndex(index)
        self.update_payload_summary()  # the count follows the source that is open

    def on_encrypt_mode_changed(self, mode: str):
        self.encrypt_stack.setCurrentIndex(0 if mode == "password" else 1)
        self.update_draft_status()

    def on_public_key_selected(self, file_path: str):
        self.public_key_path = None
        if file_path:
            result = inspect_public_key(file_path)
            self.public_key_status.set_result(result)
            if result.valid:
                self.public_key_path = file_path
        else:
            self.public_key_status.clear_result()

        self.update_draft_status()
