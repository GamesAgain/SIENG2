"""
Metadata input form: pick a target file, then edit its metadata.

Card "Target File" (drop zone) -> after a file is chosen, switch to its editor (PNG or MP3).
The form never writes the file:
- Standalone: the tab saves get_entries() itself
- Configurable pipeline (is_config=True): get_inputs() -> MetadataInputsDraft; the file is written when the pipeline runs.
  The target can also be a PNG output of an earlier step (Previous Output): the editor reads the text of the
  file that chain started from (its text is the same as the output's: LSB++ / Locomotive keep text chunks).
"""
from pathlib import Path

from mutagen import MutagenError
from PyQt6.QtCore import QSignalBlocker, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QStackedWidget, QVBoxLayout

from src.core.configurable.drafts import TECHNIQUE_LABELS, MetadataInputsDraft
from src.core.configurable.link import is_linked
from src.core.configurable.step_output import StepOutput, StepOutputInfo
from src.core.stego.metadata_handlers.mp3_handler import MetadataMP3Handler
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap
from src.gui.components.widgets.files_drop import FileDropWidget
from src.gui.components.widgets.selection_toggle import SelectionToggle
from src.gui.features.embed.configurable.widgets.step_output_picker import StepOutputPicker
from src.gui.features.embed.forms.metadata.mp3_form import MP3MetadataForm
from src.gui.features.embed.forms.metadata.png_form import PNGMetadataForm
from src.path import svg_path

ICON_SIZE = 16


class MetadataInputForm(QFrame):

    target_file_changed = pyqtSignal(str)  # path ของไฟล์ที่เปิดอยู่ ("" = ยังไม่ได้เลือก)

    def __init__(self, is_config: bool = False, parent=None):
        super().__init__(parent)
        self.is_config = is_config
        self.target_file_path: str | None = None    # ไฟล์ที่ editor อ่าน (Manual หรือไฟล์ต้นสายของ Previous Output)
        self.target_link: StepOutput | None = None  # Previous Output ที่เลือก (pipeline เท่านั้น)
        self.output_infos: dict[StepOutput, StepOutputInfo] = {}
        self.removed_frames: list[str] = []         # MP3 frame ที่ v2.3 เก็บไม่ได้ (pipeline ลบตอน Run)
        self.open_form: PNGMetadataForm | MP3MetadataForm | None = None  # editor ที่เปิดอยู่
        self.setup_ui()

    # --- UI construction ---

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 11, 0, 0)

        self.target_card = self.build_target_file_card()
        self.png_form = PNGMetadataForm()
        self.mp3_form = MP3MetadataForm(is_config=self.is_config)
        self.forms = {".png": self.png_form, ".mp3": self.mp3_form}  # นามสกุล -> editor
        for form in self.forms.values():
            form.change_file_requested.connect(self.reset_target)

        # หน้าเลือกไฟล์ <-> หน้าแก้ metadata
        self.target_stack = QStackedWidget()
        self.target_stack.addWidget(self.target_card)
        self.target_stack.addWidget(self.png_form)
        self.target_stack.addWidget(self.mp3_form)
        main_layout.addWidget(self.target_stack, 1)

    def build_target_file_card(self) -> QFrame:
        target_card = QFrame()
        target_card.setObjectName("card")
        add_shadow_effect(target_card)

        target_layout = QVBoxLayout(target_card)
        target_layout.setContentsMargins(10, 10, 10, 10)

        title_container = QFrame()
        title_layout = QHBoxLayout(title_container)
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(svg_path("photo-video.svg"), size=ICON_SIZE))
        title_label = QLabel("Target File (PNG, MP3)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.target_mode_toggle = SelectionToggle([
            {"text": "Manual File", "value": "manual", "variant": "source"},
            {"text": "Previous Output", "value": "previous", "variant": "source"},
        ])
        self.target_mode_toggle.mode_changed.connect(self.on_target_mode_changed)
        self.target_mode_toggle.setVisible(self.is_config)  # Standalone: hidden, Configurable: shown

        self.target_drop_zone = FileDropWidget(
            text="Drop PNG or MP3 file here or click to browse",
            sub_text="Opens the file's metadata for editing",
            icon_path=str(svg_path("photo-video.svg")),
            allowed_extensions=[".png", ".mp3"],
            show_preview=False,
        )
        self.target_drop_zone.file_selected.connect(self.on_target_file_selected)

        # Previous Output: PNG outputs of earlier steps that have no Metadata layer yet (the page filters them)
        self.output_picker = StepOutputPicker()
        self.output_picker.selection_changed.connect(self.on_target_output_selected)

        self.target_source_stack = QStackedWidget()
        self.target_source_stack.addWidget(self.target_drop_zone)
        self.target_source_stack.addWidget(self.output_picker)

        target_layout.addWidget(title_container)
        target_layout.addWidget(self.target_mode_toggle)
        target_layout.addWidget(self.target_source_stack, 1)
        return target_card

    # --- Actions ---

    def on_target_mode_changed(self, mode: str):
        self.target_source_stack.setCurrentIndex(0 if mode == "manual" else 1)

    def on_target_file_selected(self, file_path: str):
        if not file_path or file_path == self.target_file_path:
            return

        form = self.forms.get(Path(file_path).suffix.lower())
        try:
            if form is None:
                raise ValueError("Please select a PNG or MP3 file.")
            form.load_file(file_path)
            removed = self.unsupported_frames(file_path)
        except (OSError, ValueError, MutagenError) as error:
            self.reset_target()
            QMessageBox.warning(self, "Cannot read file", str(error))
            return

        self.open_editor(form, file_path, None, removed)

    def on_target_output_selected(self, reference: StepOutput | None):
        """A Previous Output was picked: edit it from the file its chain started from (the output has no file before the run)."""
        info = self.output_infos.get(reference)
        if info is None:
            return
        source = info.preview_path
        try:
            if not source or not Path(source).is_file():
                raise ValueError("The file this output starts from is unavailable. Select its source file again in that step.")
            # Previous Output ของ Metadata เป็น PNG เสมอ (LSB++ ทำ PNG จากภาพทุกชนิด) แต่ไฟล์ต้นสายอาจเป็น JPG/WebP ...
            # ต้นสายเป็น PNG -> ข้อความเดิมของมันอยู่ใน output ด้วย · ต้นสายเป็นภาพอื่น -> output ไม่มีข้อความเดิม
            is_png = Path(source).suffix.lower() == ".png"
            if is_png:
                self.png_form.load_file(source)
            else:
                self.png_form.load_empty()
        except (OSError, ValueError) as error:
            self.reset_target()
            QMessageBox.warning(self, "Cannot read file", str(error))
            return

        technique = TECHNIQUE_LABELS.get(info.technique, info.technique)
        origin = (f"values read from {Path(source).name}" if is_png
                  else f"made from {Path(source).name}, so it starts with no text metadata")
        self.png_form.file_info_bar.update_info(
            file_path="",
            display_name=f"From Step {info.step_number} {technique}, {info.display_name}",
            detail=f"Made when the pipeline runs · {origin}",
            badges=[("PNG", "blue"), ("Previous Output", "neutral")],
            icon_name=info.display_name,  # the output has no file yet: the system icon of its file type (a.png)
        )
        self.open_editor(self.png_form, source, reference, [])

    def open_editor(self, form, file_path: str, link: StepOutput | None, removed: list[str]):
        self.open_form = form
        self.target_file_path = file_path
        self.target_link = link
        self.removed_frames = removed
        if form is self.mp3_form:
            form.secret_preview.show_removed_frames(removed)
        self.target_stack.setCurrentWidget(form)
        self.target_file_changed.emit(file_path)

    def unsupported_frames(self, file_path: str) -> list[str]:
        """Pipeline only: MP3 frames ID3v2.3 cannot keep. The form shows them; saving the step = remove them at run time.
        (Standalone asks Yes/No when it saves instead.)"""
        if not self.is_config or Path(file_path).suffix.lower() != ".mp3":
            return []
        return MetadataMP3Handler().read_unsupported(file_path)

    def reset_target(self):
        """Back to the target card; the edits of the previous file are discarded."""
        self.open_form = None
        self.target_file_path = None
        self.target_link = None
        self.removed_frames = []
        with QSignalBlocker(self.target_drop_zone):  # clear_all() ส่ง file_selected("") ไม่ต้องรับซ้ำ
            self.target_drop_zone.clear_all()
        self.output_picker.set_selection(None)
        for form in self.forms.values():
            form.clear_all()
        # Change File: the focused button is hidden by the page switch and Qt moves focus to the picker list,
        # which then picks its first row by itself and reopens the editor -> keep focus on the form instead
        self.setFocus()
        self.target_stack.setCurrentWidget(self.target_card)
        self.target_file_changed.emit("")

    # --- Input API ---

    def current_form(self) -> PNGMetadataForm | MP3MetadataForm | None:
        """The editor that is open (not found by the file name: a Previous Output reads from its source, which can be a JPG)."""
        return self.open_form

    def get_entries(self) -> dict:
        """Checked values of the open file ({keyword: text} for PNG, {key: MP3Field} for MP3). Raises ValueError."""
        form = self.current_form()
        if form is None:
            raise ValueError("Please select a target PNG or MP3 file.")
        return form.get_entries()

    def key_labels(self, keys: list[str]) -> list[str]:
        """Readable names of saved keys, for messages."""
        form = self.current_form()
        return form.key_labels(keys) if form else list(keys)

    # --- Pipeline API (same as the LSB++ / Locomotive forms) ---

    def get_inputs(self) -> MetadataInputsDraft:
        """The step draft. Raises ValueError (the page shows it) when the inputs cannot be saved."""
        entries = self.get_entries()
        form = self.current_form()
        if form is self.mp3_form:
            linked_pictures = form.linked_pictures()
            payload_keys = form.payload_keys(entries)  # รวมภาพจาก step ก่อน (ใหม่เสมอ)
        else:
            linked_pictures = []
            payload_keys = form.handler.changed_keys(form.original, entries)
        return MetadataInputsDraft(
            target=self.target_link or self.target_file_path,
            entries=entries,
            payload_keys=payload_keys,
            removed_frames=list(self.removed_frames),
            linked_pictures=linked_pictures,
        )

    def load_draft(self, draft: MetadataInputsDraft) -> None:
        """Fill the form from a saved draft. A missing file / output leaves the target empty (the draft is not changed)."""
        self.reset_target()
        target = draft.target
        if is_linked(target):
            # The page gives the list (set_output_choices) before this; an output that is no longer in it stays unpicked
            self.target_mode_toggle.set_mode("previous")  # set_mode does not emit mode_changed
            self.on_target_mode_changed("previous")
            if target in self.output_infos:
                self.output_picker.set_selection(target)
                self.on_target_output_selected(target)
        elif target and Path(target).is_file():
            self.target_mode_toggle.set_mode("manual")
            self.on_target_mode_changed("manual")
            with QSignalBlocker(self.target_drop_zone):
                self.target_drop_zone.add_files([target])
            self.on_target_file_selected(target)

        # ค่าเดิมของไฟล์ = original, ค่าที่บันทึกไว้ = entries (+ ภาพจาก step ก่อน สำหรับ MP3)
        form = self.current_form()
        if form is self.mp3_form:
            form.set_entries(draft.entries, draft.linked_pictures)
        elif form is not None:
            form.set_entries(draft.entries)

    def set_output_choices(self, choices: list[StepOutputInfo], picture_choices: list[StepOutputInfo] = ()):
        """The page gives the outputs this step may pick: choices = the target (PNG, no Metadata layer),
        picture_choices = MP3 pictures (any free PNG). The form only passes them on."""
        self.output_infos = {info.reference: info for info in choices}
        self.output_picker.set_outputs(choices)
        self.mp3_form.pictures_form.set_picture_choices(list(picture_choices))
