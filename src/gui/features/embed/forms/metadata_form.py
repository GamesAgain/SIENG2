"""
Metadata input form: pick a target file, then edit its metadata.

Card "Target File" (drop zone) -> after a file is chosen, switch to its editor (PNG or MP3).
The form never writes the file:
- Standalone: the tab saves get_entries() itself
- Configurable pipeline (is_config=True): get_inputs() -> MetadataInputsDraft; the file is written when the pipeline runs.
  The target can also be a PNG output of an earlier step (Previous Output): the editor reads the text of the
  file that chain started from (its text is the same as the output's: LSB++ / Locomotive keep text chunks).
"""
from copy import deepcopy
from pathlib import Path

from mutagen import MutagenError
from PyQt6.QtCore import QSignalBlocker, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QStackedWidget, QVBoxLayout

from src.core.configurable.drafts import TECHNIQUE_LABELS, LinkedPicture, MetadataInputsDraft
from src.core.configurable.link import is_linked
from src.core.configurable.step_output import StepOutput, StepOutputInfo
from src.core.stego.metadata_handlers.mp3_handler import MP3Field, MetadataMP3Handler, apic_description
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, truncate_text_middle
from src.gui.components.widgets.files_drop import FileDropWidget
from src.gui.components.widgets.selection_toggle import SelectionToggle
from src.gui.features.embed.configurable.widgets.step_output_picker import StepOutputPicker
from src.gui.features.embed.forms.metadata.mp3_form import MP3MetadataForm
from src.gui.features.embed.forms.metadata.mp3_pictures import read_picture_file
from src.gui.features.embed.forms.metadata.png_form import PNGMetadataForm
from src.path import svg_path

ICON_SIZE = 16
FILE_NAME_LIMIT = 60  # characters of an output's file name shown in the file bar (the full name is the tooltip)


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
        self.imported_edits: dict = {}  # kept until a compatible target is selected, then applied once
        self.setup_ui()

    # --- UI construction ---

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 11, 0, 0)

        self.target_card = self.build_target_file_card()
        self.png_form = PNGMetadataForm(is_config=self.is_config)
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

        # แถบไฟล์: ชื่อไฟล์ยาวย่อกลาง (เฉพาะส่วนชื่อ) ชื่อเต็มอยู่ใน tooltip · บรรทัดรายละเอียดไม่พูดชื่อซ้ำ
        technique = TECHNIQUE_LABELS.get(info.technique, info.technique)
        prefix = f"From Step {info.step_number} {technique}, "
        if is_png:
            detail, detail_tip = "Made when the pipeline runs", f"Its text metadata is read from {Path(source).name}."
        else:
            detail = f"Made when the pipeline runs · made from a {Path(source).suffix[1:].upper()} image, no text metadata"
            detail_tip = f"Made from {Path(source).name}: a PNG made from this image starts with no text metadata."
        bar = self.png_form.file_info_bar
        bar.update_info(
            file_path="",
            display_name=prefix + truncate_text_middle(info.display_name, FILE_NAME_LIMIT),
            detail=detail,
            badges=[("PNG", "blue"), ("Previous Output", "neutral")],
            icon_name=info.display_name,  # the output has no file yet: the system icon of its file type (a.png)
        )
        bar.file_name.setToolTip(prefix + info.display_name)  # update_info(file_path="") leaves it empty
        bar.file_detail.setToolTip(detail_tip)
        self.open_editor(self.png_form, source, reference, [])

    def open_editor(self, form, file_path: str, link: StepOutput | None, removed: list[str]):
        self.open_form = form
        self.target_file_path = file_path
        self.target_link = link
        self.removed_frames = removed
        if form is self.mp3_form:
            form.secret_preview.show_removed_frames(removed)
        self.clear_import_marks()
        self.apply_imported_edits(form)
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
        self.clear_import_marks()
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
        if self.imported_edits:
            raise ValueError("Select a target matching the imported metadata type before saving.")
        for widget in self.text_widgets(form):
            text = widget.toPlainText() if hasattr(widget, "toPlainText") else widget.text()
            if widget.property("importPending") and not text:
                widget.setFocus()
                raise ValueError("Fill in the metadata text marked [pending] before saving.")
        return form.get_entries()

    def text_widgets(self, form):
        """Only current rows (removed widgets can still await deleteLater)."""
        if form is self.png_form:
            return [field.value_input for field in form.standard_fields.values()] + [row.value_input for row in form.custom_rows]
        widgets = []
        for field in [*form.text_form.standard_fields.values(), *form.text_form.other_fields.values()]:
            if field.has_rows():
                widgets.extend(row.inputs["text"] for row in field.rows)
            else:
                widgets.append(field.value_input)
        return widgets

    def clear_import_marks(self):
        for form in (self.png_form, self.mp3_form):
            for widget in self.text_widgets(form):
                if widget.property("importPending"):
                    widget.setProperty("importPending", False)
                    widget.setPlaceholderText("")

    def mark_import_pending(self, widget):
        widget.setProperty("importPending", True)
        widget.setPlaceholderText("[pending]")

    def apply_imported_edits(self, form):
        """Apply YAML edits against this file's original values, never against the previous target."""
        edits = self.imported_edits
        if not edits:
            return
        media = "mp3" if form is self.mp3_form else "png"
        if edits["media"] != media:
            QMessageBox.warning(self, "Imported Metadata", "The imported edits cannot be applied to this file type. "
                                f"Select a {edits['media'].upper()} target.")
            return  # keep edits until the user chooses a compatible file
        entries = {key: value for key, value in form.original.items() if key not in edits["remove"]}
        if media == "png":
            entries.update({key: value or "" for key, value in edits["set"].items()})
            form.set_entries(entries)
            for key, value in edits["set"].items():
                if value is None:
                    field = form.standard_fields.get(key)
                    widget = field.value_input if field else next(row.value_input for row in form.custom_rows if row.get_keyword() == key)
                    self.mark_import_pending(widget)
        else:
            fields = [value for value in entries.values() if value.frame_id != "APIC"]
            for value in edits["set"]:
                field = MP3Field(value["frame"], value["text"] or "", value.get("desc", ""), value.get("lang", "eng"))
                fields = [old for old in fields if old.key != field.key or (field.frame_id.startswith("W") and not field.text)]
                fields.append(field)
            form.text_form.set_fields(fields)
            groups = {}
            for field in fields:
                groups.setdefault(field.frame_id, []).append(field)
            for frame_id, values in groups.items():
                field = form.text_form.standard_fields.get(frame_id) or form.text_form.other_fields[frame_id]
                if field.has_rows():
                    for row, value in zip(field.rows, values):
                        if not value.text:
                            self.mark_import_pending(row.inputs["text"])
                elif not values[-1].text:
                    self.mark_import_pending(field.value_input)
            pictures = [value for value in entries.values() if value.frame_id == "APIC"]
            taken = {picture.desc for picture in pictures}
            for value in edits["pictures"]:
                source, picture_type = value["source"], value["type"]
                desc = apic_description(picture_type, taken)
                taken.add(desc)
                if is_linked(source):
                    pictures.append(LinkedPicture(source, picture_type, desc))
                    continue
                mime, data = "", b""
                if source and Path(source).is_file():
                    try:
                        mime, data = read_picture_file(source)
                    except (OSError, ValueError) as error:
                        QMessageBox.warning(self, "Imported Picture", str(error))
                pictures.append(MP3Field("APIC", desc=desc, mime=mime, picture_type=picture_type,
                                         data=data, path=source or ""))
            form.pictures_form.set_pictures(pictures)
            form.update_preview()
        self.imported_edits = {}  # used once; changing files afterward must not inherit these edits

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
        self.imported_edits = deepcopy(draft.imported_edits)
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
        if draft.imported_edits:
            return  # the edits (including empty text/pictures) were applied by open_editor
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
