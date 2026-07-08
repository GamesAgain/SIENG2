from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget
from pathlib import Path

from src.gui.components.file_drop import FileDropWidget
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap
from src.gui.components.linked_step_toggle import LinkedStepToggle
from src.gui.components.step_output_picker import StepOutputPicker
from src.gui.tabs.embed.metadata_mp3_editor import MP3MetadataEditor
from src.gui.tabs.embed.metadata_png_editor import PNGMetadataEditor
from src.gui.tabs.metadata_shared import FileInfoBar, get_file_display_info

ICON_DIR = Path(__file__).parent.parent.parent / "assets" / "svg"
ICON_SIZE = 14

class MetadataEmbedTab(QFrame):
    def __init__(self, pipeline_mode: bool = False):
        super().__init__()

        self.cover_file = None
        self.pipeline_mode = pipeline_mode  # True เมื่อฝังใน pipeline step → ซ่อนปุ่ม Save metadata

        # Linked-from-Step (pipeline_mode เท่านั้น) — non-empty = cover มาจาก output ของ step ก่อนหน้า
        self.linked_cover_index: list[int] = []
        self.linked_output_type: str | None = None  # "png"/"mp3" ของ step ที่ link ไว้ (เลือก editor ให้ตรง)
        self.link_candidates: dict[int, dict] = {}

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 11, 4, 4)

        self.cover_file_stack = QStackedWidget()
        cover_dropfile_card = self.build_cover_file_card()
        cover_file_selected_card = self.build_cover_file_selected_card()

        self.cover_file_stack.addWidget(cover_dropfile_card)
        self.cover_file_stack.addWidget(cover_file_selected_card)
        main_layout.addWidget(self.cover_file_stack)

    def build_cover_file_card(self):
        card_frame = QFrame()
        card_frame.setObjectName("card")
        add_shadow_effect(card_frame)

        main_layout = QVBoxLayout(card_frame)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)

        # Icon
        title_icon = QLabel()
        photo_icon = create_icon_pixmap(ICON_DIR / "photo-video.svg", size=16)
        title_icon.setPixmap(photo_icon)

        # Text: Cover File (PNG, MP3)
        title_label = QLabel("Target File (PNG, MP3)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.drop_zone = FileDropWidget("Drop PNG, MP3 files here or click to browse", "Supports PNG, MP3 format only", allowed_extensions=[".png", ".mp3"])
        self.drop_zone.file_selected.connect(self.on_cover_file_selected)

        main_layout.addWidget(title_container, 0) # top

        if self.pipeline_mode:
            self.linked_toggle = LinkedStepToggle()
            title_layout.addWidget(self.linked_toggle)

            # สลับระหว่าง drop zone (Manual Upload) กับ StepOutputPicker (Linked from Step)
            self.cover_source_stack = QStackedWidget()
            self.cover_source_stack.addWidget(self.drop_zone)
            self.cover_picker = StepOutputPicker(max_selection=1)
            self.cover_picker.selectionChanged.connect(self.on_cover_link_changed)
            self.cover_source_stack.addWidget(self.cover_picker)
            self.linked_toggle.modeChanged.connect(self.on_cover_link_mode_changed)

            main_layout.addWidget(self.cover_source_stack, 1)
        else:
            main_layout.addWidget(self.drop_zone, 1) # Stretch factor

        return card_frame

    def build_cover_file_selected_card(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.file_info_bar = FileInfoBar()
        self.file_info_bar.change_file_requested.connect(self.on_change_file_clicked)
        layout.addWidget(self.file_info_bar)

        # MP3: ตัว editor เต็มรูปแบบ (Text Frames / Images tab)
        self.mp3_editor = MP3MetadataEditor(pipeline_mode=self.pipeline_mode)
        self.mp3_editor.hide()
        layout.addWidget(self.mp3_editor)

        # PNG: editor สำหรับ iTXt text chunks (Standard / Custom metadata)
        self.png_editor = PNGMetadataEditor(pipeline_mode=self.pipeline_mode)
        self.png_editor.hide()
        layout.addWidget(self.png_editor)

        return container

    # --- Event Handler ---
    def on_cover_file_selected(self, file_path: str):
        self.cover_file = file_path
        info = get_file_display_info(file_path)
        self.file_info_bar.update_info(info)

        is_mp3 = Path(file_path).suffix.lower() == ".mp3"
        self.mp3_editor.setVisible(is_mp3)
        self.png_editor.setVisible(not is_mp3)
        if is_mp3:
            self.mp3_editor.load_file(file_path)
        else:
            self.png_editor.load_file(file_path)

        self.cover_file_stack.setCurrentIndex(1)

    def on_change_file_clicked(self):
        self.drop_zone.clear_file()
        self.cover_file = None
        self.linked_cover_index = []
        self.linked_output_type = None
        if self.pipeline_mode:
            self.linked_toggle.set_linked(False)
            self.cover_source_stack.setCurrentIndex(0)
            self.cover_picker.clear_selection()
        self.cover_file_stack.setCurrentIndex(0)

    # --- Linked-from-Step: cover (Configurable Pipeline เท่านั้น) ---
    def set_cover_link_candidates(self, candidates: list[dict]):
        """เรียกจาก EmbedConfigurablePage ก่อนเปิด step config ทุกครั้ง — ป้อน list ของ
        step ก่อนหน้าที่ยังว่าง+type ตรงเงื่อนไข ให้ picker แสดง"""
        self.link_candidates = {c["index"]: c for c in candidates}
        self.cover_picker.set_candidates(candidates)

    # --- Linked-from-Step: APIC image (MP3 เท่านั้น — ส่งต่อให้ images_tab ของ mp3_editor) ---
    def set_apic_link_candidates(self, candidates: list[dict]):
        self.mp3_editor.images_tab.set_link_candidates(candidates)

    def on_cover_link_mode_changed(self, is_linked: bool):
        self.cover_source_stack.setCurrentIndex(1 if is_linked else 0)
        if not is_linked:
            self.linked_cover_index = []
            self.cover_picker.clear_selection()

    def on_cover_link_changed(self, index: list[int]):
        if not index:
            self.linked_cover_index = []
            return
        idx = index[0]
        candidate = self.link_candidates.get(idx)
        if candidate:
            self.set_linked_cover(idx, candidate["label"], candidate["type"])

    def set_linked_cover(self, step_index: int, producer_label: str, output_type: str):
        """เลือก cover จาก output ของ step ก่อนหน้าแทนอัปโหลดเอง — ไฟล์จริงยังไม่มีอยู่จนกว่า
        pipeline จะรันจริง เลยเริ่มฟอร์ม metadata แบบว่างเปล่า (merge_existing=False ตอน save
        อยู่แล้ว ไม่ต่างจากไม่โหลดของเดิมมาแต่แรก)"""
        self.cover_file = None
        self.linked_cover_index = [step_index]
        self.linked_output_type = output_type

        is_mp3 = output_type == "mp3"
        self.png_editor.clear_all()
        self.mp3_editor.text_frames_tab.clear_all()
        self.mp3_editor.images_tab.clear_all()
        self.mp3_editor.setVisible(is_mp3)
        self.png_editor.setVisible(not is_mp3)

        info = {
            "icon": str(ICON_DIR / "git-branch.svg"),
            "name": f"Linked from {producer_label}",
            "detail": f"Output type: {output_type.upper()} — not on disk yet, filled in when the pipeline runs",
            "badges": [("LINKED", "orange")],
        }
        self.file_info_bar.update_info(info)
        self.cover_file_stack.setCurrentIndex(1)

    def get_linked_cover_index(self) -> list[int]:
        return self.linked_cover_index

    def clear_links(self):
        """เคลียร์ cover link + linked APIC images กลับเป็น Manual — page เรียกเวลาลบ step ที่ถูก link"""
        if self.pipeline_mode:
            self.linked_toggle.set_linked(False)
            self.cover_source_stack.setCurrentIndex(0)
            self.cover_picker.clear_selection()
            self.mp3_editor.images_tab.clear_linked_images()
        if self.linked_cover_index:   # cover เคย linked → ไม่มีไฟล์จริง กลับไปหน้า drop
            self.cover_file = None
            self.linked_output_type = None
            self.cover_file_stack.setCurrentIndex(0)
        self.linked_cover_index = []

    # --- Input API (ให้ pipeline เรียกใช้) ---
    def get_meta_dict(self) -> dict:
        """คืน metadata dict จาก editor ที่ตรงกับชนิดไฟล์ที่เลือก (PNG/MP3) — ถ้า cover เป็น
        linked ใช้ linked_output_type แทน (ไม่มีไฟล์จริงให้ตรวจนามสกุล) ให้ pipeline เอาไปใส่
        เป็น meta_dict ของ backend (config_mode.handle_metadata)"""
        if self.linked_cover_index:
            editor = self.mp3_editor if self.linked_output_type == "mp3" else self.png_editor
            return editor.collect_data()
        if not self.cover_file:
            return {}
        is_mp3 = Path(self.cover_file).suffix.lower() == ".mp3"
        editor = self.mp3_editor if is_mp3 else self.png_editor
        return editor.collect_data()