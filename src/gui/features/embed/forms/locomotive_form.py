from collections import defaultdict, deque
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from PIL import Image
from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QScrollArea, QStackedWidget, QTabWidget, QVBoxLayout

from src.core.configurable.step_output import FileSource, StepOutput, StepOutputInfo
from src.gui.components.gui_utils import add_password_visibility_toggle, add_shadow_effect, create_icon_pixmap, format_file_size
from src.gui.components.widgets.files_drop import MultiFileDropWidget
from src.gui.components.widgets.key_source import KeySourceWidget
from src.gui.components.widgets.key_validation import KeyValidationLabel, inspect_public_key
from src.gui.components.widgets.selection_toggle import SelectionToggle
from src.gui.components.widgets.step_output_picker import StepOutputPicker
from src.gui.components.widgets.toggle_switch import ToggleSwitch
from src.gui.components.widgets.visibility_stack import VisibilityStack
from src.gui.services.key_registry import KeyRegistry
from src.path import svg_path

ICON_SIZE = 16
OUTPUT_KEY_HEX_LENGTH = 8

def generate_output_key(
    used_output_keys: Collection[str] = (),
) -> str:
    """Create an internal Locomotive output identity not present in ``used``."""

    while True:
        suffix = uuid4().hex[:OUTPUT_KEY_HEX_LENGTH]
        output_key = f"output_{suffix}"
        if output_key not in used_output_keys:
            return output_key
        
@dataclass
class LocomotiveCoverDraft:
    """One Locomotive cover and the stable identity of its future output."""

    source: FileSource
    output_key: str = field(default_factory=generate_output_key)


def link_sources_to_covers(
    sources: Iterable[FileSource],
    existing_covers: Iterable[LocomotiveCoverDraft] = (),
) -> list[LocomotiveCoverDraft]:
    """Retain existing output identities and allocate unique keys for new sources."""
    available_by_source = defaultdict(deque)
    used_output_keys = set()
    for cover in existing_covers:
        available_by_source[cover.source].append(cover)
        used_output_keys.add(cover.output_key)

    covers = []
    for source in sources:
        matches = available_by_source[source]
        if matches:
            cover = matches.popleft()
        else:
            cover = LocomotiveCoverDraft(source, generate_output_key(used_output_keys))
            used_output_keys.add(cover.output_key)
        covers.append(cover)
    return covers


@dataclass
class LocomotiveInputsDraft:
    """Locomotive form state, including values in inactive payload/encryption modes."""
    covers: list[LocomotiveCoverDraft] = field(default_factory=list)
    payload_mode: str = "files"
    payload_files: list[FileSource] = field(default_factory=list)
    payload_text: str = ""
    encryption_enabled: bool = True
    encryption_mode: str = "password"
    password: str = field(default="", repr=False)
    public_key_path: str | None = None


class LocomotiveInputForm(QFrame):
    
    def __init__(self, key_registry: KeyRegistry = None, is_config: bool = False, parent = None):
        super().__init__(parent)
        
        self.key_registry = key_registry
        self.is_config = is_config
        
        self.locomotive_covers: list[LocomotiveCoverDraft] = []
        self.payload_files: list[FileSource] = []
        self.public_key_path: str | None = None
        
        self.setup_ui()
        
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 11, 0, 0)

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
        right_scroll.setObjectName("transparentScroll")
        right_scroll.setWidgetResizable(True)
        right_scroll.setWidget(right_widget)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)

        sub_layout.addLayout(left_layout, 1)
        sub_layout.addWidget(right_scroll, 1)

        main_layout.addLayout(sub_layout)
        self.update_cover_summary()
        self.update_payload_file_summary()
        self.update_payload_text_summary()
        self.update_encryption_state(self.encrypt_toggle_switch.isChecked())
        
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

        # Text: Locomotive File (PNG)
        title_label = QLabel("Locomotive File (PNGs)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.cover_mode_toggle = SelectionToggle(
            [
                { 
                    "text": "Manual File",
                    "value": "Manual",
                    "variant": "source",
                    "color_checked": "#38BDF8",
                },
                {
                    "text": "Previous Output",
                    "value": "linked",
                    "variant": "source",
                    "color_checked": "#38BDF8",
                },
            ])
        
        self.cover_mode_toggle.mode_changed.connect(self.on_cover_mode_changed)

        drop_zone = MultiFileDropWidget(
            text="Drop PNG files here or click to browse",
            sub_text="Supports one or multiple PNG files",
            icon_path=str(svg_path("photo.svg")),
            allowed_extensions=[".png"]
            )
        

        self.cover_drop_zone = drop_zone
        drop_zone.files_changed.connect(self.on_locomotive_file_selected)

        self.cover_source_stack = QStackedWidget()
        self.cover_source_stack.addWidget(drop_zone)
        self.cover_output_picker = StepOutputPicker(multi_select=True)
        self.cover_source_stack.addWidget(self.cover_output_picker)
        self.cover_output_picker.selections_changed.connect(self.on_cover_outputs_selected)

        self.cover_summary_label = QLabel("Selected: 0 PNGs")
        self.cover_summary_label.setObjectName("capacityLabel")

        locomotive_file_layout.addWidget(title_container, 0)  # top
        locomotive_file_layout.addWidget(self.cover_mode_toggle, 0)
        self.cover_mode_toggle.setVisible(self.is_config)
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
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(svg_path("file.svg"), size=ICON_SIZE))
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

        self.payload_mode_toggle = SelectionToggle([
            {
                "text": "Manual File",
                "value": "Manual",
                "variant": "source",
                "color_checked": "#38BDF8",
            },
            {
                "text": "Previous Output",
                "value": "linked",
                "variant": "source",
                "color_checked": "#38BDF8",
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
        self.payload_file_drop_zone.files_changed.connect(self.on_payload_file_selected)

        self.payload_source_stack = QStackedWidget()
        self.payload_source_stack.addWidget(self.payload_file_drop_zone)
        self.payload_output_picker = StepOutputPicker(multi_select=True)
        self.payload_source_stack.addWidget(self.payload_output_picker)
        self.payload_output_picker.selections_changed.connect(self.on_payload_outputs_selected)
        self.payload_file_summary_label = QLabel("Files: 0 · Total: 0 B")
        self.payload_file_summary_label.setObjectName("capacityLabel")

        file_layout.addWidget(self.payload_mode_toggle)
        self.payload_mode_toggle.setVisible(self.is_config)
        file_layout.addWidget(self.payload_source_stack, 1)
        file_layout.addWidget(self.payload_file_summary_label)

        # --- Text Input ---
        text_tab = QFrame()
        text_layout = QVBoxLayout(text_tab)
        text_layout.setContentsMargins(0, 12, 0, 0)

        self.payload_text_area = QPlainTextEdit()
        self.payload_text_area.setObjectName("payloadTextArea")
        self.payload_text_area.setPlaceholderText("Enter secret message here...")
        self.payload_text_area.textChanged.connect(self.update_payload_text_summary)
        self.capacity_label = QLabel("Size: 0 B")
        self.capacity_label.setObjectName("capacityLabel")
        text_layout.addWidget(self.payload_text_area, 1)
        text_layout.addWidget(self.capacity_label)

        self.payload_tabs.addTab(file_tab, "File Input")
        self.payload_tabs.addTab(text_tab, "Text Input")
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

        self.encrypt_toggle_switch = ToggleSwitch()
        self.encrypt_toggle_switch.setChecked(True)
        title_layout.addWidget(self.encrypt_toggle_switch)

        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(svg_path("shield-lock.svg"), "#a78bfa", ICON_SIZE))
        title_label = QLabel("Encryption Options")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.build_encrypt_selection())

        self.encrypt_stack = VisibilityStack()
        self.encrypt_stack.addWidget(self.build_symmetric_mode())
        self.encrypt_stack.addWidget(self.build_asymmetric_mode())
        self.encrypt_mode_toggle.mode_changed.connect(self.on_encrypt_mode_changed)
        self.encrypt_toggle_switch.toggled.connect(self.update_encryption_state)

        encryption_layout.addWidget(title_container)
        encryption_layout.addWidget(self.encrypt_stack)
        return encryption_card

    def build_encrypt_selection(self) -> SelectionToggle:
        self.encrypt_mode_toggle = SelectionToggle([
            {
                "text": "Password",
                "value": "password",
                "variant": "password",
                "color_checked": "#a78bfa",
                "icon_path": svg_path("key.svg"),
                "icon_size": 14,
            },
            {
                "text": "Public Key",
                "value": "public_key",
                "variant": "public_key",
                "color_checked": "#34D399",
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

        password_label = QLabel("Password")
        password_label.setObjectName("formLabel")
        self.password_input = QLineEdit()
        self.password_input.setObjectName("formInput")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter passphrase...")
        symmetric_layout.addWidget(password_label)
        symmetric_layout.addWidget(self.password_input)

        confirm_label = QLabel("Confirm Password")
        confirm_label.setObjectName("formLabel")
        self.confirm_input = QLineEdit()
        self.confirm_input.setObjectName("formInput")
        self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_input.setPlaceholderText("Confirm your passphrase...")
        add_password_visibility_toggle(self.password_input, self.confirm_input)
        symmetric_layout.addWidget(confirm_label)
        symmetric_layout.addWidget(self.confirm_input)
        return symmetric_mode

    def build_asymmetric_mode(self) -> QFrame:
        asymmetric_mode = QFrame()
        asymmetric_layout = QVBoxLayout(asymmetric_mode)
        asymmetric_layout.setContentsMargins(0, 0, 0, 8)

        self.public_key_source = KeySourceWidget("public", self.key_registry)
        self.public_key_drop_zone = self.public_key_source.drop_zone
        asymmetric_layout.addWidget(self.public_key_source)
        self.public_key_status = KeyValidationLabel()
        asymmetric_layout.addWidget(self.public_key_status)
        self.public_key_source.key_selected.connect(self.on_public_key_selected)
        return asymmetric_mode

    def get_inputs(self) -> LocomotiveInputsDraft:
        covers = []
        for cover in self.locomotive_covers:
            covers.append(LocomotiveCoverDraft(cover.source, cover.output_key))
        return LocomotiveInputsDraft(
            covers=covers,
            payload_mode="files" if self.payload_tabs.currentIndex() == 0 else "text",
            payload_files=list(self.payload_files),
            payload_text=self.payload_text_area.toPlainText(),
            encryption_enabled=self.encrypt_toggle_switch.isChecked(),
            encryption_mode=self.encrypt_mode_toggle.mode(),
            password=self.password_input.text(),
            public_key_path=self.public_key_path,
        )

    def load_draft(self, draft: LocomotiveInputsDraft) -> None:
        """Restore independent editor state without regenerating cover output keys."""
        self.cover_mode_toggle.set_mode("Manual")
        self.payload_mode_toggle.set_mode("Manual")
        manual_covers = []
        linked_covers = []
        self.locomotive_covers = []
        for cover in draft.covers:
            self.locomotive_covers.append(LocomotiveCoverDraft(cover.source, cover.output_key))
            if isinstance(cover.source, StepOutput):
                linked_covers.append(cover.source)
            elif isinstance(cover.source, str) and Path(cover.source).is_file():
                manual_covers.append(cover.source)

        manual_files = []
        linked_files = []
        for source in draft.payload_files:
            if isinstance(source, StepOutput):
                linked_files.append(source)
            elif isinstance(source, str) and Path(source).is_file():
                manual_files.append(source)
        # Drop-zone signals normally create cover identities. Restore the saved
        # identities ourselves, and retain missing paths so validation can report them.
        with QSignalBlocker(self.cover_drop_zone):
            self.cover_drop_zone.clear_all()
            self.cover_drop_zone.add_files(manual_covers)
        with QSignalBlocker(self.payload_file_drop_zone):
            self.payload_file_drop_zone.clear_all()
            self.payload_file_drop_zone.add_files(manual_files)
        self.payload_files = list(draft.payload_files)
        self.cover_output_picker.set_selected_outputs(linked_covers)
        self.payload_output_picker.set_selected_outputs(linked_files)
        if linked_covers:
            self.cover_mode_toggle.set_mode("linked")
        if linked_files:
            self.payload_mode_toggle.set_mode("linked")
        self.on_cover_mode_changed(self.cover_mode_toggle.mode())
        self.on_payload_source_mode_changed(self.payload_mode_toggle.mode())
        self.payload_text_area.setPlainText(draft.payload_text)
        self.payload_tabs.setCurrentIndex(0 if draft.payload_mode == "files" else 1)
        self.encrypt_mode_toggle.set_mode(draft.encryption_mode)
        self.on_encrypt_mode_changed(draft.encryption_mode)
        self.encrypt_toggle_switch.setChecked(draft.encryption_enabled)
        self.update_encryption_state(draft.encryption_enabled)
        self.password_input.setText(draft.password)
        self.confirm_input.setText(draft.password)
        self.public_key_drop_zone.clear_all()
        if draft.public_key_path and Path(draft.public_key_path).is_file():
            self.public_key_source.select_path(draft.public_key_path)
        self.update_cover_summary()
        self.update_payload_file_summary()
        self.update_payload_text_summary()

    def validate_draft(self) -> bool:
        """Check manual files and selected output references before saving."""
        try:
            if not self.locomotive_covers:
                raise ValueError("Please select at least one PNG cover image.")
            selected_covers = self.cover_output_picker.selected_outputs()
            for cover in self.locomotive_covers:
                if isinstance(cover.source, StepOutput):
                    if not self.is_config or cover.source not in selected_covers:
                        raise ValueError("A linked PNG cover is unavailable. Select another output.")
                    continue  # The generated PNG is checked when the pipeline runs.
                if not isinstance(cover.source, str):
                    raise ValueError("Select PNG cover images or previous PNG outputs.")
                path = Path(cover.source)
                if not path.is_file() or path.suffix.lower() != ".png":
                    raise ValueError(f"PNG cover is unavailable: {path.name}")
                with Image.open(path) as image:
                    if image.format != "PNG":
                        raise ValueError(f"Cover is not a PNG image: {path.name}")
                    image.verify()
            if self.payload_tabs.currentIndex() == 0:
                if not self.payload_files:
                    raise ValueError("Please select at least one payload file.")
                selected_files = self.payload_output_picker.selected_outputs()
                for source in self.payload_files:
                    if isinstance(source, StepOutput):
                        if not self.is_config or source not in selected_files:
                            raise ValueError("A linked payload file is unavailable. Select another output.")
                    elif not isinstance(source, str) or not Path(source).is_file():
                        raise ValueError("One or more payload files are unavailable.")
            elif not self.payload_text_area.toPlainText().strip():
                raise ValueError("Please enter a secret message.")
            if self.encrypt_toggle_switch.isChecked():
                mode = self.encrypt_mode_toggle.mode()
                if mode == "password":
                    if not self.password_input.text():
                        raise ValueError("Please enter a password for encryption.")
                    if not self.passwords_match():
                        raise ValueError("Passwords do not match.")
                elif mode == "public_key":
                    if not self.public_key_path:
                        raise ValueError("Please select a valid public key for encryption.")
                    result = inspect_public_key(self.public_key_path)
                    self.public_key_status.set_result(result)
                    if not result.valid:
                        raise ValueError(result.message)
                else:
                    raise ValueError("Please select an encryption mode.")
        except (OSError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "Invalid Step Inputs", str(error))
            return False
        return True

    def passwords_match(self) -> bool:
        return self.password_input.text() == self.confirm_input.text()

    def update_cover_summary(self):
        count = len(self.locomotive_covers)
        noun = "PNG" if count == 1 else "PNGs"
        summary = f"Selected: {count} {noun}"
        linked_count = 0
        for cover in self.locomotive_covers:
            if isinstance(cover.source, StepOutput):
                linked_count += 1
        if linked_count:
            summary += f" · Manual: {count - linked_count} · Linked: {linked_count}"
        self.cover_summary_label.setText(summary)

    def update_payload_file_summary(self):
        count = len(self.payload_files)
        total_bytes = 0
        available_count = 0
        linked_count = 0
        for source in self.payload_files:
            if isinstance(source, StepOutput):
                linked_count += 1
                continue
            try:
                total_bytes += Path(source).stat().st_size
                available_count += 1
            except OSError:
                continue
        summary = f"Files: {count} · Total: {format_file_size(total_bytes)}"
        if linked_count:
            # Future output sizes are unknown; show bytes of manual files only.
            summary = f"Files: {count} · Manual size: {format_file_size(total_bytes)} · Linked: {linked_count}"
        if available_count != count - linked_count:
            summary += f" · Available: {available_count}"
        self.payload_file_summary_label.setText(summary)

    def update_payload_text_summary(self):
        size = len(self.payload_text_area.toPlainText().encode("utf-8"))
        self.capacity_label.setText(f"Size: {format_file_size(size)}")

    def on_locomotive_file_selected(self, file_paths: list[str]):
        if self.cover_mode_toggle.mode() == "linked":
            return
        sources = list(file_paths)
        for cover in self.locomotive_covers:
            if isinstance(cover.source, StepOutput):
                sources.append(cover.source)
        self.locomotive_covers = link_sources_to_covers(sources, self.locomotive_covers)
        self.update_cover_summary()

    def on_payload_file_selected(self, file_paths: list[str]):
        if self.payload_mode_toggle.mode() == "linked":
            return
        sources = list(file_paths)
        for source in self.payload_files:
            if isinstance(source, StepOutput):
                sources.append(source)
        self.payload_files = sources
        self.update_payload_file_summary()

    def set_available_outputs(self, outputs: list[StepOutputInfo], payload_outputs: list[StepOutputInfo] | None = None):
        png_outputs = []
        for output in outputs:
            if output.media_type == "png":
                png_outputs.append(output)
        self.cover_output_picker.set_outputs(png_outputs)
        self.payload_output_picker.set_outputs(outputs if payload_outputs is None else payload_outputs)

        linked_covers = []
        for cover in self.locomotive_covers:
            if isinstance(cover.source, StepOutput):
                linked_covers.append(cover.source)
        self.cover_output_picker.set_selected_outputs(linked_covers)
        linked_files = []
        for source in self.payload_files:
            if isinstance(source, StepOutput):
                linked_files.append(source)
        self.payload_output_picker.set_selected_outputs(linked_files)

    def on_cover_mode_changed(self, mode: str):
        # Switching the view does not remove inputs from the other source.
        if mode == "linked":
            self.cover_source_stack.setCurrentWidget(self.cover_output_picker)
        else:
            self.cover_source_stack.setCurrentWidget(self.cover_drop_zone)

    def on_payload_source_mode_changed(self, mode: str):
        if mode == "linked":
            self.payload_source_stack.setCurrentWidget(self.payload_output_picker)
        else:
            self.payload_source_stack.setCurrentWidget(self.payload_file_drop_zone)

    def on_cover_outputs_selected(self, references: list[StepOutput]):
        sources = []
        for cover in self.locomotive_covers:
            if isinstance(cover.source, str):
                sources.append(cover.source)
        sources.extend(references)
        self.locomotive_covers = link_sources_to_covers(sources, self.locomotive_covers)
        self.update_cover_summary()

    def on_payload_outputs_selected(self, references: list[StepOutput]):
        sources = []
        for source in self.payload_files:
            if isinstance(source, str):
                sources.append(source)
        sources.extend(references)
        self.payload_files = sources
        self.update_payload_file_summary()

    def on_encrypt_mode_changed(self, mode: str):
        self.encrypt_stack.setCurrentIndex(0 if mode == "password" else 1)

    def update_encryption_state(self, enabled: bool):
        self.encrypt_stack.setVisible(enabled)
        for button in self.encrypt_mode_toggle.buttons.values():
            button.setEnabled(enabled)

    def on_public_key_selected(self, file_path: str):
        self.public_key_path = None
        if not file_path:
            self.public_key_status.clear_result()
            return
        result = inspect_public_key(file_path)
        self.public_key_status.set_result(result)
        if result.valid:
            self.public_key_path = file_path
