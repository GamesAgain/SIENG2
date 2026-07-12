import re
import shutil
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QButtonGroup, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from src.gui.components.flow_layout import FlowLayout
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap
from src.gui.components.step_card import StepCard, center_in_band, make_arrow
from src.gui.components.step_config_widgets import PlaceholderInputs, StepConfigDialog, StepConfigPanel
from src.gui.tabs.embed.lsb_embed import LSBEmbedInputs
from src.gui.tabs.embed.loco_embed import LocoEmbedInputs
from src.gui.tabs.embed.metadata_embed import MetadataEmbedTab

from src.core.configurable.config_mode import (
    CONFIG_WORKSPACE, REF_PATTERN, deliverable_step_ids, generate_extract_pipeline, read_yaml,
    ref_step_slot, run_embed_pipeline, write_yaml,
)

from src.gui.pages.sub_pages.embed.pipeline_constants import (
    ADD_SIZE, CHIP_ICON_SIZE, CLEAR_CHIP_COLOR, ICON_DIR, ICON_SIZE, SCENARIOS,
    STEP_META, TECHNIQUE_CHIPS,
)

# โฟลเดอร์ .yaml ตัวอย่าง (src/templates) — configurable_page.py อยู่ที่ src/gui/pages/sub_pages/embed/
TEMPLATES_DIR = Path(__file__).resolve().parents[4] / "templates"

# (label ที่โชว์ใน dropdown, ชื่อไฟล์ใน TEMPLATES_DIR) — ลำดับตรงกับตัวเลขนำหน้าไฟล์
PIPELINE_TEMPLATES = [
    ("Distributed Key-Split & Locomotive Decoy", "01_distributed_key_split.yaml"),
    ("Nested Concealment → MP3 Carrier",          "02_nested_mp3_carrier.yaml"),
    ("Multi-Cover Fan-Out (DAG)",                 "03_multicover_fanout.yaml"),
    ("Cross-Media Password Split",                "04_crossmedia_key_split.yaml"),
    ("Triple-Stack on One Carrier",               "05_triple_stack_one_carrier.yaml"),
]


def encryption_config(password, public_key):
    """แปลง password/public_key ที่ widget คืนมา → dict encryption ตาม schema ของ backend
    (config_mode.crypto_kwargs) · ไม่เข้ารหัส = None"""
    if password:
        return {"mode": "symmetric", "password": password}
    if public_key:
        return {"mode": "asymmetric", "public_key": public_key}
    return None


# --- Export Config: promote literal path/text (manual, ไม่ใช่ step ref) → ${{ variables.X }} ---
# แนวคิด: pipeline.yaml เป็น "สูตร" ส่วนตัวของผู้ส่งที่ reuse ได้ (ไม่เคยส่งให้ผู้รับ) — ถ้า export
# ออกมาแล้วมีแต่ literal path ฝังทุก step ครั้งหน้าจะเปลี่ยนไฟล์ต้องไล่หาทีละ step อีก ให้ auto-
# promote เป็น variables: block แทน ไม่ว่า pipeline จะมาจาก template ที่มี variables อยู่แล้ว
# (ซึ่งถูก resolve เป็น literal ไปแล้วตอน import) หรือสร้างสด ๆ ในมือ GUI ล้วน ๆ ก็ตาม
# · ไม่แตะ step ref (${{ steps.X... }}) เพราะไม่ใช่ literal · ค่าเดิมซ้ำกัน (เช่น public key ไฟล์
# เดียวใช้หลาย step) ใช้ variable เดียวกัน ไม่สร้างซ้ำ
_NO_PROMOTE_KEYS = {"mode", "type", "desc", "mime"}   # ค่า structural/label ไม่ใช่ path หรือ secret


def _var_tag(step_id: str) -> str:
    """step_id → prefix สำหรับตั้งชื่อ variable เช่น 'LSB++ Embed text in PNG' → 'LSB_EMBED_TEXT_IN_PNG'"""
    return re.sub(r"[^A-Za-z0-9]+", "_", step_id).strip("_").upper() or "STEP"


def _unique_var_name(base: str, used_names: set) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "_", base).strip("_").upper() or "VAR"
    if base not in used_names:
        return base
    n = 2
    while f"{base}_{n}" in used_names:
        n += 1
    return f"{base}_{n}"


def _promote_literals(value, tag_parts: list, variables: dict, value_to_var: dict, used_names: set):
    """เดิน value (str/list/dict) แบบ recursive แทนที่ literal string ที่ไม่ใช่ step ref ด้วย
    ${{ variables.NAME }} แล้วเติมชื่อ+ค่าเข้า variables ระหว่างทาง · int/bool/None ปล่อยผ่าน"""
    if isinstance(value, str):
        if not value or ref_step_slot(value):
            return value
        if value in value_to_var:
            return f"${{{{ variables.{value_to_var[value]} }}}}"
        name = _unique_var_name("_".join(tag_parts), used_names)
        variables[name] = value
        value_to_var[value] = name
        used_names.add(name)
        return f"${{{{ variables.{name} }}}}"
    if isinstance(value, list):
        n = len(value)
        return [
            _promote_literals(item, tag_parts if n == 1 else tag_parts + [str(i + 1)],
                               variables, value_to_var, used_names)
            for i, item in enumerate(value)
        ]
    if isinstance(value, dict):
        return {
            k: (v if k.lower() in _NO_PROMOTE_KEYS else
                _promote_literals(v, tag_parts + [k], variables, value_to_var, used_names))
            for k, v in value.items()
        }
    return value


# ══════════════════════════════════════════════════════════════════════════
# EmbedConfigurablePage
# ══════════════════════════════════════════════════════════════════════════
class EmbedConfigurablePage(QFrame):

    def __init__(self):
        super().__init__()
        # state: list ของ {"type": str, "sub": str, "valid": bool}
        self.steps = []
        self.config_variant = "popup"
        self.inline_panel = None
        self.inline_inner = None
        # ผลลัพธ์ของ run ล่าสุด — เก็บไว้ให้ Save Outputs ใช้ (None = ยังไม่มี output ให้ save)
        self.last_run_results = None
        self.last_run_config = None
        self.setup_ui()
        self.render_nodes()

    def setup_ui(self):
        # scroll ทั้งหน้า เผื่อ inline panel / pipeline ยาวในอนาคต
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("pipelineScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("pipelineScrollContent")
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(4, 11, 4, 4)
        main_layout.setSpacing(10)

        main_layout.addWidget(self.build_pipeline_builder_card())

        # ช่องสำหรับ Inline Panel (step config แบบฝังในหน้า) — โผล่ใต้การ์ด
        self.inline_slot = QVBoxLayout()
        main_layout.addLayout(self.inline_slot)

        main_layout.addStretch()
        main_layout.addLayout(self.build_execution_bar())

        scroll.setWidget(content)
        page_layout.addWidget(scroll)

    # --- การ์ด Pipeline Builder ---
    def build_pipeline_builder_card(self):
        card_frame = QFrame()
        card_frame.setObjectName("card")
        add_shadow_effect(card_frame)

        main_layout = QVBoxLayout(card_frame)
        main_layout.setSpacing(10)

        # หัวการ์ด
        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)

        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(ICON_DIR / "git-branch.svg", size=ICON_SIZE))
        title_label = QLabel("Pipeline Builder")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        main_layout.addWidget(title_container)
        main_layout.addLayout(self.build_template_row())
        main_layout.addLayout(self.build_technique_chip_row())
        main_layout.addWidget(self.build_canvas())
        main_layout.addLayout(self.build_step_ui_row())

        return card_frame

    def build_template_row(self):
        template_row = QHBoxLayout()
        template_row.setSpacing(8)

        self.template_combo = QComboBox()
        self.template_combo.addItem("Select a Pipeline Example (Template)", "")
        for i, (label, fname) in enumerate(PIPELINE_TEMPLATES, 1):
            self.template_combo.addItem(f"{i}. {label}", fname)
        self.template_combo.currentIndexChanged.connect(self.on_template_selected)
        template_row.addWidget(self.template_combo, 1)

        self.import_config_btn = QPushButton(" Import Config")
        self.import_config_btn.setObjectName("SecondaryBtn")
        self.import_config_btn.setProperty("textColor", "white")
        self.import_config_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_config_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "file-import.svg", color_hex="#FFFFFF", size=ICON_SIZE)))
        self.import_config_btn.clicked.connect(self.on_import_config)
        template_row.addWidget(self.import_config_btn)
        
        self.export_config_btn = QPushButton(" Export Config")
        self.export_config_btn.setObjectName("SecondaryBtn")
        self.export_config_btn.setProperty("textColor", "white")
        self.export_config_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_config_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "file-export.svg", color_hex="#FFFFFF", size=ICON_SIZE)))
        self.export_config_btn.clicked.connect(self.on_export_config)
        template_row.addWidget(self.export_config_btn)

        return template_row

    def build_technique_chip_row(self):
        chip_row = QHBoxLayout()
        chip_row.setSpacing(8)

        for step_type in TECHNIQUE_CHIPS:
            meta = STEP_META[step_type]
            btn = QPushButton(f" {meta['label']}")
            btn.setObjectName("ChipBtn")
            btn.setProperty("accentColor", meta["accent"])
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "plus.svg", color_hex=meta["hex"], size=CHIP_ICON_SIZE)))
            btn.clicked.connect(lambda checked, type=step_type: self.add_step(type))
            chip_row.addWidget(btn)

        chip_row.addStretch()

        self.clear_pipeline_btn = QPushButton(" Clear")
        self.clear_pipeline_btn.setObjectName("ChipBtn")
        self.clear_pipeline_btn.setProperty("accentColor", "red")
        self.clear_pipeline_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_pipeline_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "trash.svg", color_hex=CLEAR_CHIP_COLOR, size=CHIP_ICON_SIZE)))
        self.clear_pipeline_btn.clicked.connect(self.clear_pipeline)
        chip_row.addWidget(self.clear_pipeline_btn)

        return chip_row

    def build_canvas(self):
        canvas = QFrame()
        canvas.setObjectName("pipelineCanvas")
        canvas.setMinimumHeight(150)

        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(16, 16, 16, 16)

        self.flow_container = QWidget()
        self.flow_layout = FlowLayout(self.flow_container, margin=0, spacing=8)
        canvas_layout.addWidget(self.flow_container)

        return canvas

    def build_step_ui_row(self):
        row = QHBoxLayout()
        row.setSpacing(8)

        label = QLabel("STEP CONFIG UI:")
        label.setObjectName("pipelineSummary")
        row.addWidget(label)

        self.btn_popup = QPushButton(" Popup Dialog")
        self.btn_popup.setObjectName("stepUiBtn")
        self.btn_popup.setCheckable(True)
        self.btn_popup.setChecked(True)
        self.btn_popup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_popup.clicked.connect(lambda: self.set_variant("popup"))

        self.btn_inline = QPushButton(" Inline Panel")
        self.btn_inline.setObjectName("stepUiBtn")
        self.btn_inline.setCheckable(True)
        self.btn_inline.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_inline.clicked.connect(lambda: self.set_variant("inline"))

        variant_group = QButtonGroup(self)
        variant_group.setExclusive(True)
        variant_group.addButton(self.btn_popup)
        variant_group.addButton(self.btn_inline)

        row.addWidget(self.btn_popup)
        row.addWidget(self.btn_inline)
        row.addStretch()
        return row

    # --- แถบล่าง: status + progress + Export/Run ---
    def build_execution_bar(self):
        execution_bar = QHBoxLayout()
        execution_bar.setContentsMargins(0, 0, 0, 0)
        execution_bar.setSpacing(8)

        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QVBoxLayout(status_card)

        self.status_label = QLabel("Status: Ready")
        self.status_label.setObjectName("statusLabel")
        status_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("loadingIndicator")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.progress_bar)

        execution_bar.addWidget(status_card, 1)

        # Save Outputs — เปิดใช้ได้เฉพาะหลัง Run Pipeline สำเร็จ (มีไฟล์ output ให้ save)
        self.save_outputs_btn = QPushButton(" Save Outputs")
        self.save_outputs_btn.setObjectName("SecondaryBtn")
        self.save_outputs_btn.setProperty("textColor", "white")
        self.save_outputs_btn.setFixedHeight(50)
        self.save_outputs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_outputs_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "upload.svg", color_hex="#FFFFFF", size=ICON_SIZE)))
        self.save_outputs_btn.setEnabled(False)
        self.save_outputs_btn.clicked.connect(self.on_save_outputs)
        execution_bar.addWidget(self.save_outputs_btn)

        self.run_pipeline_btn = QPushButton("Run Pipeline")
        self.run_pipeline_btn.setObjectName("PrimaryActionBtn")
        self.run_pipeline_btn.setFixedHeight(50)
        self.run_pipeline_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_pipeline_btn.clicked.connect(self.on_run_pipeline)
        execution_bar.addWidget(self.run_pipeline_btn)

        return execution_bar

    # --- การจัดการ node ---
    def add_step(self, step_type, sub_text=None, valid=False):
        step = {
            "type": step_type,
            "sub": sub_text or STEP_META[step_type]["sub"],
            "valid": valid,
            "step_id_custom": False,
        }
        # provisional step_id (auto, unique) — commit จะ regenerate จาก content จริงถ้าผู้ใช้ไม่แก้เอง
        step["step_id"] = self._unique_step_id(self._step_id_base(step_type), len(self.steps))
        self.steps.append(step)
        self.render_nodes()

    def remove_step(self, idx):
        self.close_inline_panel()
        self.delete_step_inputs(self.steps[idx])
        del self.steps[idx]
        self._reindex_links_after_removal(idx)
        self.render_nodes()

    def _reindex_links_after_removal(self, removed_idx):
        """linked_*_index เก็บ index (ตำแหน่ง) ของ step เป้าหมาย พอลบ step ตำแหน่งขยับหมด
        · step ที่ link ไปหาตัวที่ index >= removed_idx จะได้รับผลกระทบ → เคลียร์ link ทั้งหมด
        ของ step นั้น (ทั้ง state บนหน้า + บน widget) แล้ว invalidate ให้ผู้ใช้เลือกใหม่
        · step ที่ link ไปหาตัวที่ index < removed_idx ไม่กระทบ (ตำแหน่งไม่ขยับ + step_id คงเดิม)
        เลือกวิธี 'เคลียร์+ให้เลือกใหม่' เพราะปลอดภัยชัวร์ ไม่มี ref ค้างชี้ผิด step แบบเงียบๆ"""
        for step in self.steps:
            links = (step.get("linked_cover_index") or []) + (step.get("linked_payload_index") or [])
            links += self.apic_linked_index(step.get("module_inputs", {}).get("meta_dict", {}))
            if any(self._slot_step(j) >= removed_idx for j in links):
                step["linked_cover_index"] = []
                step["linked_payload_index"] = []
                step["valid"] = False
                widget = step.get("inputs")
                if widget is not None and hasattr(widget, "clear_links"):
                    widget.clear_links()

    def clear_pipeline(self):
        self.close_inline_panel()
        for step in self.steps:
            self.delete_step_inputs(step)
        self.steps.clear()
        self.render_nodes()

    def render_nodes(self):
        # ล้างของเดิม — setParent(None) เอาออกจากจอทันที (deleteLater เป็น async
        # ถ้าไม่ตัด parent ก่อน widget เก่าจะยังโชว์ค้างที่ตำแหน่งเดิมจนกว่าจะถูกลบ)
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        for i, data in enumerate(self.steps):
            if i > 0:
                self.flow_layout.addWidget(make_arrow())
            card = StepCard(data["type"], data["sub"], data["valid"])
            card.clicked.connect(lambda idx=i: self.open_step_config(idx))
            card.removeRequested.connect(lambda idx=i: self.remove_step(idx))
            self.flow_layout.addWidget(card)

        # ปุ่มเพิ่ม step (วงกลมเส้นประ) ท้ายแถว
        add_btn = QPushButton()
        add_btn.setObjectName("addStepBtn")
        add_btn.setFixedSize(ADD_SIZE, ADD_SIZE)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "plus.svg", color_hex="#38BDF8", size=18)))
        add_btn.clicked.connect(lambda: self.add_step("lsbpp"))
        self.flow_layout.addWidget(center_in_band(add_btn, ADD_SIZE, ADD_SIZE))

    # --- template / import / export / run ---
    def on_template_selected(self, index):
        """เลือก template จาก dropdown → โหลด .yaml ใน src/templates มาสร้าง pipeline จริง
        (dropdown reset กลับหัวข้อหลังโหลด เพื่อให้เลือกตัวเดิมซ้ำได้)"""
        fname = self.template_combo.itemData(index)
        if not fname:
            return
        path = TEMPLATES_DIR / fname
        if not path.exists():
            QMessageBox.warning(self, "Template", f"ไม่พบไฟล์ template:\n{path}")
        else:
            try:
                n = self.load_config(read_yaml(path))
                self.status_label.setText(f"Loaded template ({n} steps): {fname}")
            except Exception as e:
                QMessageBox.critical(self, "Template", f"โหลด template ไม่สำเร็จ:\n{e}")
        self.template_combo.blockSignals(True)     # กลับไปหัวข้อหลัก ไม่ให้ค้างที่ชื่อ template
        self.template_combo.setCurrentIndex(0)
        self.template_combo.blockSignals(False)

    def on_import_config(self):
        """Import ไฟล์ .yaml (ที่ export ไว้ หรือเขียนเอง) กลับมาเป็น pipeline ที่รันต่อได้"""
        path, _ = QFileDialog.getOpenFileName(self, "Import Config", "", "YAML config (*.yaml *.yml)")
        if not path:
            return
        try:
            n = self.load_config(read_yaml(path))
            self.status_label.setText(f"Imported config ({n} steps)")
            QMessageBox.information(self, "Import Config", f"โหลด {n} step จาก:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Import Config", f"Import ไม่สำเร็จ:\n{e}")

    # --- โหลด config_dict → step model ที่รันได้จริง (ผกผันกับ build_config_dict) ---
    def load_config(self, config_dict: dict) -> int:
        """แปลง config_dict (variables + workflows.embed) → self.steps ที่รัน Run Pipeline ได้ทันที

        โครงสร้าง step ที่สร้างตรงกับที่ commit_step ผลิต (module_inputs + linked_*_index + valid)
        ดังนั้นไม่ต้องสร้าง/กรอก widget เลย — build_config_dict อ่านจาก module_inputs โดยตรง
        · variable ref (${{ variables.X }}) ถูก resolve เป็นค่าจริง · step ref (${{ steps.Y... }})
        ถูกแปลงเป็น linked_*_index (คู่ (step_index, output_pos)) ให้ตรงกับโมเดล Linked-from-Step
        · step ถูก mark 'imported' ไว้ — เปิดแก้ใน panel ครั้งแรกจะเตือนว่าเริ่มจากฟอร์มเปล่า"""
        embed = (config_dict.get("workflows") or {}).get("embed") or []
        if not embed:
            raise ValueError("config นี้ไม่มี workflows.embed ให้โหลด")
        variables = config_dict.get("variables", {})
        id_to_index = {s.get("step_id"): i for i, s in enumerate(embed)}

        self.clear_pipeline()
        for s in embed:
            module = s.get("module")
            if module not in ("lsbpp", "locomotive", "metadata"):
                raise ValueError(f"step '{s.get('step_id')}' ใช้ module ที่ไม่รู้จัก: {module!r}")
            self.steps.append(self._step_from_config(s, variables, id_to_index))
        self.render_nodes()
        return len(self.steps)

    @staticmethod
    def _resolve_vars(value, variables):
        """resolve เฉพาะ ${{ variables.X }} (ทุกที่ใน str/list/dict) · ปล่อย ${{ steps... }} ไว้
        (step ref จัดการแยกเป็น linked index) — ไม่ใช้ resolve_value ของ backend เพราะมันจะพยายาม
        resolve step ref แล้ว error เนื่องจากตอนโหลดยังไม่มี context ของ step outputs"""
        if isinstance(value, str):
            if ref_step_slot(value):
                return value
            return REF_PATTERN.sub(
                lambda m: str(variables.get(m.group(1).strip()[len("variables."):], m.group(0)))
                if m.group(1).strip().startswith("variables.") else m.group(0),
                value,
            )
        if isinstance(value, list):
            return [EmbedConfigurablePage._resolve_vars(v, variables) for v in value]
        if isinstance(value, dict):
            return {k: EmbedConfigurablePage._resolve_vars(v, variables) for k, v in value.items()}
        return value

    def _step_from_config(self, s: dict, variables: dict, id_to_index: dict) -> dict:
        module = s["module"]
        inputs = s.get("inputs", {}) or {}
        step = {
            "type": module, "step_id": s["step_id"], "step_id_custom": True,
            "valid": True, "imported": True,
            "linked_cover_index": [], "linked_payload_index": [],
        }

        # -- covers: แยก manual (resolve var → path) ออกจาก linked (step ref → slot) --
        manual_covers, linked_cover = [], []
        for cover in inputs.get("covers", []) or []:
            if (slot := ref_step_slot(cover)):
                linked_cover.append((id_to_index[slot[0]], slot[1]))
            else:
                manual_covers.append(self._resolve_vars(cover, variables))
        step["linked_cover_index"] = linked_cover

        enc = self._resolve_vars(inputs.get("encryption"), variables)

        if module == "lsbpp":
            mi = {"covers": manual_covers or [""], "encryption": enc}
            if inputs.get("text_payload") is not None:
                mi["text_payload"] = self._resolve_vars(inputs.get("text_payload"), variables)
            if inputs.get("text_file") is not None:
                mi["text_file"] = self._resolve_vars(inputs.get("text_file"), variables)
            step["module_inputs"] = mi

        elif module == "locomotive":
            mi = {"covers": manual_covers or [""], "encryption": enc}
            linked_payload = []
            if inputs.get("file_payload"):
                manual_files = []
                for item in inputs["file_payload"]:
                    if (slot := ref_step_slot(item)):
                        linked_payload.append((id_to_index[slot[0]], slot[1]))
                    else:
                        manual_files.append(self._resolve_vars(item, variables))
                mi["file_payload"] = manual_files   # linked ถูก override ใน build_config_dict
            elif inputs.get("text_payload") is not None:
                mi["text_payload"] = self._resolve_vars(inputs.get("text_payload"), variables)
            step["linked_payload_index"] = linked_payload
            step["module_inputs"] = mi

        else:  # metadata
            meta_dict, apic_links = self._meta_from_config(inputs.get("meta_dict") or {}, variables, id_to_index)
            step["linked_payload_index"] = apic_links
            step["module_inputs"] = {
                "covers": [manual_covers[0] if manual_covers else None],
                "meta_dict": meta_dict,
                "encryption": enc,
            }

        step["sub"] = self._imported_sub(module, manual_covers, linked_cover)
        return step

    def _meta_from_config(self, meta_dict: dict, variables: dict, id_to_index: dict):
        """คืน (meta_dict ที่พร้อมใช้, apic_links) · APIC entry ที่ path เป็น output ของ step อื่น
        ถูกแปลงเป็น marker {"linked_step_index": (idx,pos), ...} แบบเดียวกับที่ GUI สร้างตอน link
        (build_config_dict → resolve_linked_apic จะแปลง marker เป็น path ref ตอนรัน)"""
        apic_links, out = [], {}
        for key, val in meta_dict.items():
            if key == "APIC" and isinstance(val, list):
                apic_out = []
                for item in val:
                    if isinstance(item, dict) and (slot := ref_step_slot(item.get("path"))):
                        pair = (id_to_index[slot[0]], slot[1])
                        apic_links.append(pair)
                        apic_out.append({"linked_step_index": pair,
                                          "type": item.get("type", 3), "desc": item.get("desc", "")})
                    else:
                        apic_out.append(self._resolve_vars(item, variables))
                out["APIC"] = apic_out
            else:
                out[key] = self._resolve_vars(val, variables)
        return out, apic_links

    def _imported_sub(self, module, manual_covers, linked_cover) -> str:
        if linked_cover:
            return f"linked: {self._slot_label(linked_cover[0])}"
        if manual_covers:
            return Path(manual_covers[0]).name if len(manual_covers) == 1 else f"{len(manual_covers)} covers"
        return STEP_META[module]["sub"]

    def _steps_ready(self, title) -> bool:
        """เช็คว่ามี step และทุก step commit แล้ว (มี module_inputs) ก่อน export/run"""
        if not self.steps:
            QMessageBox.warning(self, title, "No steps to process yet.")
            return False
        if not all(step.get("valid") for step in self.steps):
            QMessageBox.warning(self, title, "Some steps are not configured — open each step and click Save Step first.")
            return False
        return True

    def on_export_config(self):
        if not self._steps_ready("Export Config"):
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Config", "pipeline.yaml", "YAML config (*.yaml *.yml)")
        if not path:
            return
        try:
            write_yaml(self.build_export_dict(), path)
            QMessageBox.information(self, "Export Config", f"Config saved ({len(self.steps)} steps):\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Config", f"Export failed:\n{e}")

    def on_run_pipeline(self):
        if not self._steps_ready("Run Pipeline"):
            return
        self._clear_workspace_output()   # ลบ output รันก่อนหน้าทิ้งเสมอ (workspace เป็น temp)
        self.last_run_results = None
        self.last_run_config = None
        self.save_outputs_btn.setEnabled(False)
        self.status_label.setText("Running pipeline...")
        try:
            # run_embed_pipeline validate ก่อนรันเอง เจอ error จะ raise ออกมา (รันแบบ sync — UI ค้างจนเสร็จ)
            config = self.build_config_dict()
            results = run_embed_pipeline(config)
            self.last_run_results = results
            self.last_run_config = config
            self.progress_bar.setValue(100)
            self.save_outputs_btn.setEnabled(True)   # มี output แล้ว → save ได้
            self.status_label.setText(f"Done — {len(results)} steps · click Save Outputs to keep the files")
            QMessageBox.information(self, "Run Pipeline", f"Pipeline finished successfully ({len(results)} steps).")
        except Exception as e:
            self.progress_bar.setValue(0)
            self.status_label.setText("Pipeline failed")
            QMessageBox.critical(self, "Run Pipeline", f"Pipeline run failed:\n{e}")

    # --- Save Outputs (ย้ายไฟล์ผลลัพธ์สุดท้าย + เขียน extract config, แล้วเคลียร์ workspace) ---
    def _clear_workspace_output(self):
        """ลบทุกอย่างใน config_workspace/output ให้ workspace กลับมาว่าง"""
        out_dir = CONFIG_WORKSPACE / "output"
        if not out_dir.exists():
            return
        for item in out_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)

    @staticmethod
    def _output_paths(outputs: dict) -> list:
        """แผ่ path ทั้งหมดจาก outputs ของ step (stego_file เดี่ยว หรือ stego_files เป็น list)
        ลำดับตรงกับลำดับ cover: output[i] มาจาก cover[i]"""
        paths = []
        for value in outputs.values():
            paths += value if isinstance(value, list) else [value]
        return paths

    def _root_stem(self, by_id: dict, step_id: str, cover_pos: int) -> str:
        """ไล่ cover ของ step กลับไปหา 'ไฟล์ต้นฉบับ' (ตาม linked ref) แล้วคืน stem ของมัน
        — เอาไปตั้งชื่อไฟล์ output ให้อิงชื่อไฟล์เดิม แทน step_id ยาวๆ"""
        covers = by_id[step_id]["inputs"].get("covers") or []
        if not covers:
            return step_id
        cover = covers[cover_pos] if cover_pos < len(covers) else covers[0]
        slot = ref_step_slot(cover)   # ${{ steps.X.outputs.Y[i] }} → (X, i), ไฟล์ path ธรรมดา → None
        if slot and slot[0] in by_id:
            return self._root_stem(by_id, slot[0], slot[1])   # ไล่ต่อไปหา cover[i] ของ producer ตาม output slot ที่ ref จริง
        return Path(cover).stem

    @staticmethod
    def _unique_filename(name: str, dest: Path, used: set) -> str:
        """กันชื่อซ้ำ (ทั้งในชุดที่ save รอบนี้ และไฟล์ที่มีอยู่แล้วในโฟลเดอร์ปลายทาง)"""
        stem, ext = Path(name).stem, Path(name).suffix
        candidate, n = name, 2
        while candidate in used or (dest / candidate).exists():
            candidate = f"{stem}_{n}{ext}"
            n += 1
        return candidate

    def on_save_outputs(self):
        if not self.last_run_results:
            return
        dest = QFileDialog.getExistingDirectory(self, "Save Outputs — choose a destination folder")
        if not dest:
            return
        dest = Path(dest)
        try:
            # 1) ย้ายเฉพาะไฟล์ 'ผลลัพธ์สุดท้าย' (deliverable) — ตั้งชื่อ {ไฟล์ต้นฉบับ}_stego.{ext}
            #    เก็บ resources: resource_id (file:STEP#i) -> ชื่อไฟล์ ให้ผู้รับรู้ว่า slot ไหนคือไฟล์ไหน
            by_id = {s["step_id"]: s for s in self.last_run_config["workflows"]["embed"]}
            used, moved, resources = set(), [], {}
            for step_id in deliverable_step_ids(self.last_run_config):
                for i, path in enumerate(self._output_paths(self.last_run_results[step_id]["outputs"])):
                    src = Path(path)
                    if not src.exists():
                        continue
                    name = self._unique_filename(f"{self._root_stem(by_id, step_id, i)}_stego{src.suffix}", dest, used)
                    used.add(name)
                    shutil.move(str(src), str(dest / name))
                    moved.append(name)
                    resources[f"file:{step_id}#{i}"] = name

            # 2) เขียน extract config (workflows.extract + resources filename hint — ไม่มี inputs ฝั่ง embed)
            #    last_run_results ให้ session_id ของ Locomotive แต่ละ step แนบไปด้วย (ดู generate_extract_pipeline)
            extract_cfg = {"workflows": {"extract": generate_extract_pipeline(self.last_run_config, self.last_run_results)}, "resources": resources}
            write_yaml(extract_cfg, dest / "extract_config.yaml")

            # 3) เคลียร์ workspace + ปิดปุ่ม (ไม่มี output ให้ save แล้ว ต้อง run ใหม่)
            self._clear_workspace_output()
            self.last_run_results = None
            self.last_run_config = None
            self.save_outputs_btn.setEnabled(False)
            self.status_label.setText(f"Saved {len(moved)} output file(s) + extract_config.yaml")
            QMessageBox.information(
                self, "Save Outputs",
                f"Saved to:\n{dest}\n\nDeliverable files: {', '.join(moved) or '(none)'}\n+ extract_config.yaml",
            )
        except Exception as e:
            QMessageBox.critical(self, "Save Outputs", f"Save failed:\n{e}")

    # ── step config (Popup Dialog / Inline Panel — reuse inner widget เดียวกัน) ──
    def set_variant(self, variant):
        self.config_variant = variant
        if variant == "popup":
            self.close_inline_panel()

    def make_step_inner(self, idx, step_type):
        """สร้าง inner widget สำหรับ step config — reuse widget จริงจากหน้า Standalone
        (LSB/Loco = *EmbedInputs, Metadata = MetadataEmbedTab ทั้งตัว)"""
        # pipeline_mode=True → โชว์ toggle Manual Upload/Linked from Step บน cover card ทุก technique
        # (Metadata เพิ่ม: ซ่อนปุ่ม "Save metadata" ด้วย เพราะ save = embed จริง ต้องรันผ่าน Run Pipeline)
        if step_type == "lsbpp":
            return LSBEmbedInputs(pipeline_mode=True)
        if step_type == "locomotive":
            return LocoEmbedInputs(pipeline_mode=True)
        if step_type == "metadata":
            return MetadataEmbedTab(pipeline_mode=True)
        return PlaceholderInputs(idx, step_type)

    def  get_step_inner(self, idx):
        """คืน inner widget ของ step — สร้างครั้งแรกแล้วเก็บไว้บน step["inputs"]
        เพื่อ persist ค่าที่กรอก (เปิด config ซ้ำเจอค่าเดิม)"""
        step = self.steps[idx]
        if step.get("inputs") is None:
            step["inputs"] = self.make_step_inner(idx, step["type"])
        return step["inputs"]

    def park_inner(self, inner):
        """ดึง inner กลับมาฝากไว้กับ page แบบซ่อน (ไม่ใช่ setParent(None) เพราะจะ
        กลายเป็น top-level window แว้บ) — คง state ไว้ ไม่โดนลบตอนปิด shell"""
        inner.setParent(self)
        inner.hide()

    def delete_step_inputs(self, step):
        widget = step.get("inputs")
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
            step["inputs"] = None

    def commit_step(self, idx, inner, step_id_text, is_custom):
        """อ่านค่าจาก inner widget → เก็บ backend inputs + Step ID · คืน False ถ้า validate ไม่ผ่าน
        step_id_text/is_custom มาจากช่อง Step ID บนหัว shell · is_custom=True (พิมพ์เอง) → ใช้ค่านั้น
        แต่ต้องไม่ว่าง+ไม่ซ้ำ · is_custom=False → auto-gen จาก technique+content แล้วต่อ suffix กันซ้ำ"""
        step = self.steps[idx]
        step_type = step["type"]
        is_custom = is_custom or step.get("step_id_custom", False)

        # ── Step ID: ถ้าผู้ใช้พิมพ์เอง validate ก่อนเลย (primary key ห้ามว่าง/ซ้ำ) ──
        if is_custom:
            if not step_id_text:
                QMessageBox.warning(self, "Validation Error", "Step ID cannot be empty.")
                return False
            if step_id_text in {s.get("step_id") for i, s in enumerate(self.steps) if i != idx}:
                QMessageBox.warning(self, "Validation Error", f"Step ID '{step_id_text}' is already used by another step.")
                return False

        # content hint สำหรับ auto-gen step_id (เก็บระหว่างอ่าน inputs)
        loco_file = meta_image = False
        meta_fmt = "PNG"

        if step_type == "lsbpp":
            data = inner.get_input_data()   # validate ในตัว (เด้ง warning ถ้าไม่ครบ) — ผ่านได้ทั้ง manual/linked
            if not data:
                return False
            cover, payload_text, password, public_key = data
            linked = inner.get_linked_cover_index()
            if linked:
                step["sub"] = f"linked: {self._slot_label(linked[0])}"
            else:
                step["sub"] = Path(cover).name if cover else STEP_META["lsbpp"]["sub"]
            step["linked_cover_index"] = linked
            step["linked_payload_index"] = []
            step["module_inputs"] = {
                "covers": [cover],   # manual path (ถ้า linked build จะ override จาก index)
                "text_payload": payload_text,
                "encryption": encryption_config(password, public_key),
            }

        elif step_type == "locomotive":
            data = inner.get_input_data()
            if not data:
                return False
            covers_manual, payload_files_manual, raw_text, public_key, password = data
            linked_cover = inner.get_linked_cover_index()
            if linked_cover:
                step["sub"] = f"linked: {len(linked_cover)} step(s)"
            else:
                step["sub"] = Path(covers_manual[0]).name if len(covers_manual) == 1 else f"{len(covers_manual)} covers"
            step["linked_cover_index"] = linked_cover

            linked_payload = inner.get_linked_payload_index()
            module_inputs = {
                "covers": covers_manual,
                "encryption": encryption_config(password, public_key),
            }
            # payload เลือกได้ 3 ทาง: linked จาก step ก่อนหน้า > ไฟล์ manual > raw text
            if linked_payload:
                module_inputs["file_payload"] = []   # build จะ override จาก linked_payload_index
                loco_file = True
            elif payload_files_manual:
                module_inputs["file_payload"] = payload_files_manual
                loco_file = True
            else:
                module_inputs["text_payload"] = raw_text
            step["linked_payload_index"] = linked_payload
            step["module_inputs"] = module_inputs

        elif step_type == "metadata":
            linked_cover = inner.get_linked_cover_index()
            if linked_cover:
                cover_ref = None   # build จะ override covers จาก linked_cover_index
                step["sub"] = f"linked: {self._slot_label(linked_cover[0])}"
                meta_fmt = self.output_type_of_step(linked_cover[0]).upper()
            else:
                if not inner.cover_file:
                    QMessageBox.warning(self, "Validation Error", "Please select a target PNG/MP3 file.")
                    return False
                cover_ref = inner.cover_file
                step["sub"] = Path(inner.cover_file).name
                meta_fmt = "MP3" if inner.cover_file.lower().endswith(".mp3") else "PNG"
            meta_dict = inner.get_meta_dict()   # APIC ยังเป็น marker (linked_step_index) — build จะ resolve
            if not meta_dict:
                QMessageBox.warning(self, "Validation Error", "Please add at least one metadata field.")
                return False
            meta_image = "APIC" in meta_dict
            step["linked_cover_index"] = linked_cover
            step["linked_payload_index"] = self.apic_linked_index(meta_dict)
            step["module_inputs"] = {
                "covers": [cover_ref],
                "meta_dict": meta_dict,
                "encryption": None,   # หน้า Metadata ยังไม่มีช่องเข้ารหัส
            }

        else:
            name = inner.output_name()
            if name:
                step["sub"] = name

        # ── set Step ID: custom = ใช้ที่ผู้ใช้พิมพ์ · auto = gen จาก content + suffix กันซ้ำ ──
        if is_custom:
            step["step_id"] = step_id_text
            step["step_id_custom"] = True
        else:
            base = self._step_id_base(step_type, loco_file=loco_file, meta_fmt=meta_fmt, meta_image=meta_image)
            step["step_id"] = self._unique_step_id(base, idx)
            step["step_id_custom"] = False

        step["valid"] = True
        return True

    # --- สร้าง config_dict (schema ของ config_mode) จาก step ที่ commit แล้ว ---
    def build_config_dict(self) -> dict:
        """ประกอบ config_dict พร้อมส่งให้ run_embed_pipeline / write_yaml

        ref ของ linked slot ถูก resolve 'ตอนนี้' จาก index → step_id ปัจจุบัน (ไม่ใช่ค่าที่ freeze
        ตอน commit) ดังนั้นถ้าผู้ใช้แก้ Step ID ของ target ทีหลัง ref จะตามไปถูกเสมอ"""
        embed_steps = []
        for i, step in enumerate(self.steps):
            module = step["type"]
            step_id = step["step_id"]
            inputs = dict(step["module_inputs"])   # copy — จะ override เฉพาะ slot ที่ linked

            if step.get("linked_cover_index"):
                inputs["covers"] = [self.output_ref_for_index(j) for j in step["linked_cover_index"]]
            if module == "locomotive" and step.get("linked_payload_index"):
                inputs["file_payload"] = [self.output_ref_for_index(j) for j in step["linked_payload_index"]]
            if module == "metadata":
                inputs["meta_dict"] = self.resolve_linked_apic(inputs.get("meta_dict", {}))

            embed_steps.append({
                "step_id": step_id,
                "module": module,
                "inputs": inputs,
                "outputs": self.build_outputs(i, step_id, module, inputs),
            })
        return {"workflows": {"embed": embed_steps}}

    def build_export_dict(self) -> dict:
        """เหมือน build_config_dict() แต่ auto-promote literal path/text ที่ manual (ไม่ใช่ step
        ref) ทุกอันเป็น ${{ variables.X }} + generate variables: block ไว้บนสุด — ใช้เฉพาะตอน
        Export Config (ไม่ใช้กับ Run Pipeline ซึ่งต้องการ literal ตรง ๆ ตอนรันจริง) ให้ไฟล์ที่
        export ออกมาเป็น 'สูตร' reuse ได้ทันที ไม่ต้องไล่หา path ทีละ step ตอนจะใช้ไฟล์ใหม่"""
        config = self.build_config_dict()
        variables, value_to_var, used_names = {}, {}, set()
        for step in config["workflows"]["embed"]:
            tag = _var_tag(step["step_id"])
            step["inputs"] = _promote_literals(step["inputs"], [tag], variables, value_to_var, used_names)
        return {"variables": variables, **config}

    def build_outputs(self, idx, step_id, module, inputs) -> dict:
        """ตั้งชื่อไฟล์ output ต่อ step (backend เติม path ใต้ config_workspace ให้เอง)"""
        if module == "locomotive":
            # loco: output ต้องมีจำนวนเท่ากับ covers
            n = len(inputs["covers"])
            return {"stego_files": [f"output/{step_id}_{j + 1}.png" for j in range(n)]}
        if module == "metadata":
            # metadata คง format เดิมของ cover (.png/.mp3) — ใช้ output_type_of_step แทน
            # Path(...).suffix ตรงๆ เพราะ covers[0] อาจเป็น ${{ steps.ID... }} ref ไม่ใช่ path จริง
            ext = f".{self.output_type_of_step(idx)}"
            return {"stego_file": f"output/{step_id}{ext}"}
        return {"stego_file": f"output/{step_id}.png"}   # lsbpp = PNG เสมอ

    # --- Step ID (primary key แก้ได้ · auto-gen ตาม technique/content) ---
    def _step_id_base(self, step_type, *, loco_file=False, meta_fmt="PNG", meta_image=False) -> str:
        """ชื่อ step_id เริ่มต้นตาม technique + content (ยังไม่รวม suffix กันซ้ำ)"""
        if step_type == "lsbpp":
            return "LSB++ Embed text in PNG"
        if step_type == "locomotive":
            return f"Locomotive Embed {'file' if loco_file else 'text'} in PNG"
        if step_type == "metadata":
            return f"Embed {'Image' if meta_image else 'text'} in {meta_fmt} Metadata"
        return step_type

    def _unique_step_id(self, base, exclude_idx) -> str:
        """ทำให้ base ไม่ซ้ำกับ step อื่นด้วยการต่อท้าย ' - N' (N เริ่มที่ 1)"""
        existing = {s.get("step_id") for i, s in enumerate(self.steps) if i != exclude_idx}
        if base not in existing:
            return base
        n = 1
        while f"{base} - {n}" in existing:
            n += 1
        return f"{base} - {n}"

    # --- Linked-from-Step: id/ref ของ output ต่อ step + รายชื่อ candidate ที่ link ได้ ---
    # "target" ที่ฟังก์ชันกลุ่มนี้รับ คือค่า "index" ที่ candidate ส่งกลับมาจาก available_link_candidates
    # — สำหรับ cover role เป็น tuple (step_idx, output_pos) เพราะเลือกได้เจาะจงเป็นราย output
    # (multi-output producer เอาคนละ output ไป link คนละ step ได้) ส่วน payload/APIC role ยังเป็น
    # step_idx เฉยๆ (ผูกทั้ง step, เจาะจง output ไม่ได้ — ดู available_link_candidates) ทุกฟังก์ชัน
    # ด้านล่าง unwrap ด้วย pattern เดียวกัน: `step_idx, out_pos = target if tuple else (target, 0)`
    # เพื่อรองรับทั้งสองแบบโดยไม่ต้องแยกโค้ดเป็นสองชุด
    @staticmethod
    def _slot_step(target) -> int:
        """เอาแค่ step_idx ออกจาก target ไม่ว่าจะเป็น slot tuple หรือ step_idx เดี่ยว ๆ"""
        return target[0] if isinstance(target, tuple) else target

    def _n_outputs(self, idx) -> int:
        """จำนวนไฟล์ output จริงของ step[idx] ตามที่ commit ไว้แล้ว — มีแค่ Locomotive ที่ได้
        มากกว่า 1 (เท่าจำนวน cover) เทคนิคอื่นมี output เดียวเสมอ"""
        step = self.steps[idx]
        if step["type"] != "locomotive":
            return 1
        linked = step.get("linked_cover_index") or []
        covers = step.get("module_inputs", {}).get("covers") or []
        return max(len(linked) if linked else len(covers), 1)

    def _slot_label(self, target) -> str:
        """label ของ output slot หนึ่งอัน เช่น 'Step 1' หรือ 'Step 1 · O2' ถ้า producer มีหลาย
        output (ไม่งั้นจะไม่รู้ว่า linked ไป output ไหน) — ใช้โชว์ใน step['sub'] ตอน commit"""
        step_idx, out_pos = target if isinstance(target, tuple) else (target, 0)
        label = self.steps[step_idx]["step_id"]
        return f"{label} · O{out_pos + 1}" if self._n_outputs(step_idx) > 1 else label

    def output_type_of_step(self, target) -> str:
        """ชนิดไฟล์ output ของ step ('png'/'mp3') — ใช้ทั้งกรอง candidate ใน StepOutputPicker
        และตอนตั้งนามสกุลไฟล์ output ของ metadata step ที่ link คนอื่นต่อ (ทุก output ของ step
        เดียวเป็นชนิดเดียวกันเสมอ เลยไม่ต้องสน out_pos)"""
        idx = self._slot_step(target)
        step = self.steps[idx]
        if step["type"] in ("lsbpp", "locomotive"):
            return "png"
        # metadata: type ตามไฟล์เป้าหมายของมันเอง (ไล่ตาม link ต่อถ้ามันเองก็ link อยู่)
        linked = step.get("linked_cover_index") or []
        if linked:
            return self.output_type_of_step(linked[0])
        covers = (step.get("module_inputs") or {}).get("covers") or []
        if covers:
            return "mp3" if str(covers[0]).lower().endswith(".mp3") else "png"
        return "png"

    def output_ref_for_index(self, target) -> str:
        """สร้าง ${{ steps.ID.outputs... }} อ้างถึง output ของ target (slot tuple หรือ step_idx
        เดี่ยว ๆ = output[0]) — ใช้ตอน step ถัดไป 'link' เอา output ตัวนี้ไปเป็น cover/payload
        ของตัวเอง (schema เดียวกับ config_mode.REF_PATTERN)"""
        step_idx, out_pos = target if isinstance(target, tuple) else (target, 0)
        step_id = self.steps[step_idx]["step_id"]
        if self.steps[step_idx]["type"] == "locomotive":
            return f"${{{{ steps.{step_id}.outputs.stego_files[{out_pos}] }}}}"
        return f"${{{{ steps.{step_id}.outputs.stego_file }}}}"

    def apic_linked_index(self, meta_dict: dict) -> list:
        """เก็บ step index ของ APIC entry ที่ยังเป็น marker (linked_step_index) — ใช้ตอน commit
        เพื่อ track ว่า step ไหนถูกจอง + ตอน reindex เวลาลบ step"""
        apic = (meta_dict or {}).get("APIC")
        if not isinstance(apic, list):
            return []
        return [it["linked_step_index"] for it in apic if isinstance(it, dict) and "linked_step_index" in it]

    def resolve_linked_apic(self, meta_dict: dict) -> dict:
        """แปลง APIC marker (linked_step_index) → {"path": ref, "type", "desc"} ตอน build
        (schema ที่ MetadataMP3Handler รองรับอยู่แล้ว — อ่านไฟล์จาก path ตอน embed จริง)"""
        apic = meta_dict.get("APIC")
        if not isinstance(apic, list):
            return meta_dict
        resolved = [
            {"path": self.output_ref_for_index(it["linked_step_index"]),
             "type": it.get("type", 3), "desc": it.get("desc", "")}
            if isinstance(it, dict) and "linked_step_index" in it else it
            for it in apic
        ]
        return {**meta_dict, "APIC": resolved}

    def claimed_slots(self, exclude_idx=None) -> set:
        """(step_idx, output_pos) ที่ถูก step อื่น link ไปใช้แล้ว ไม่ว่า role ไหน (cover/payload/
        APIC) — ห้าม slot ไหนถูก ref ซ้ำ ไม่งั้น extract-chain ของ backend งงว่าใครคือ consumer
        จริง (แต่ละ output slot claim ได้แค่ 1 ครั้งรวมทุก role — backend รองรับ per-slot chaining
        ทั้ง cover และ payload แล้ว ทุก role เลย claim แค่ slot จริงที่เลือกเหมือนกันหมด)"""
        claimed = set()
        for i, step in enumerate(self.steps):
            if i == exclude_idx:
                continue
            claimed.update(step.get("linked_cover_index") or [])
            claimed.update(step.get("linked_payload_index") or [])
        return claimed

    # slot กำหนดว่า type ไหนใช้ได้ — ทุก role แสดง candidate แยกรายจริง (index ที่คืนเป็น tuple
    # (step_idx, output_pos)) เพราะ backend chain ได้ระดับ slot ทั้ง cover และ payload แล้ว:
    # · "cover" ตาม module ปัจจุบัน (lsbpp/loco=png, metadata=png/mp3)
    # · "payload_any" ไม่จำกัด type (Locomotive file_payload ฝังไฟล์อะไรก็ได้)
    # · "payload_image" ต้องเป็นรูป (Metadata-MP3 APIC) — ระบบเราสร้าง output ได้แค่ png/mp3 เลยเหลือแค่ png
    def available_link_candidates(self, idx, slot: str = "cover") -> list:
        """list ของ output ก่อนหน้า idx ที่ยัง 'ว่าง' (ไม่ถูกใครจอง) + step ต้น commit แล้ว + type
        ตรงกับ slot ที่ขอ — ป้อนให้ StepOutputPicker ทุกครั้งก่อนเปิด step config"""
        current_module = self.steps[idx]["type"]
        if slot == "payload_any":
            allowed_types = {"png", "mp3"}
        elif slot == "payload_image":
            allowed_types = {"png"}
        else:  # "cover"
            allowed_types = {"png"} if current_module in ("lsbpp", "locomotive") else {"png", "mp3"}
        claimed = self.claimed_slots(exclude_idx=idx)

        candidates = []
        for j in range(idx):  # backward-only — step ทีหลังจะ ref step ก่อนไม่ได้
            step = self.steps[j]
            if not step.get("valid") or self.output_type_of_step(j) not in allowed_types:
                continue
            n = self._n_outputs(j)
            for pos in range(n):
                if (j, pos) in claimed:
                    continue
                suffix = f" (Output {pos + 1}/{n})" if n > 1 else ""
                candidates.append({
                    "index": (j, pos),
                    "step_no": j + 1,
                    "module": STEP_META[step["type"]]["label"],
                    "output": step["sub"] if n == 1 else f"Output {pos + 1}/{n}",
                    "label": f"Step {j + 1} — {STEP_META[step['type']]['label']}{suffix}",   # ใช้ตอนโชว์ใน FileInfoBar (metadata)
                    "accent": STEP_META[step["type"]]["accent"],
                    "type": self.output_type_of_step(j),
                })
        return candidates

    def open_step_config(self, idx):
        step = self.steps[idx]
        step_type = step["type"]
        # step ที่ import มา: config รันได้เลยจาก module_inputs แต่ widget ยังเป็นฟอร์มเปล่า
        # (ยังไม่ทำ rehydrate) — เตือนครั้งเดียวว่าถ้ากด Save Step จะเขียนทับค่าที่ import มา
        if step.pop("imported", False):
            QMessageBox.information(
                self, "Imported step",
                "สเต็ปนี้โหลดมาจาก template/config และจะรันตามค่าที่โหลดมาได้เลย\n\n"
                "การเปิดแก้ที่นี่จะเริ่มจากฟอร์มเปล่า — ถ้ากด Save Step จะเขียนทับค่าที่โหลดมา "
                "(ถ้าแค่อยากรัน ไม่ต้องเปิดแก้ กด Run Pipeline ได้เลย)",
            )
        title = f"Step {idx + 1} : {STEP_META[step_type]['label']}"
        inner = self.get_step_inner(idx)
        if hasattr(inner, "set_cover_link_candidates"):
            inner.set_cover_link_candidates(self.available_link_candidates(idx, slot="cover"))
        if hasattr(inner, "set_payload_link_candidates"):
            inner.set_payload_link_candidates(self.available_link_candidates(idx, slot="payload_any"))
        if hasattr(inner, "set_apic_link_candidates"):
            inner.set_apic_link_candidates(self.available_link_candidates(idx, slot="payload_image"))
        commit = lambda sid, custom: self.commit_step(idx, inner, sid, custom)
        step_id_default = step["step_id"]
        initial_custom = step.get("step_id_custom", False)

        if self.config_variant == "popup":
            dialog = StepConfigDialog(title, step_id_default, initial_custom, inner, commit, self.window())
            dialog.exec()
            self.park_inner(inner)      # เก็บ inner กลับ (persist state) ก่อน dialog ถูกลบ
            dialog.deleteLater()
            self.render_nodes()
        else:
            self.close_inline_panel()
            panel = StepConfigPanel(title, step_id_default, initial_custom, inner, commit)
            panel.saved.connect(self.on_inline_saved)
            panel.cancelled.connect(self.close_inline_panel)
            self.inline_slot.addWidget(panel)
            self.inline_panel = panel
            self.inline_inner = inner

    def on_inline_saved(self):
        self.close_inline_panel()
        self.render_nodes()

    def close_inline_panel(self):
        if self.inline_panel is not None:
            if self.inline_inner is not None:
                self.park_inner(self.inline_inner)   # กัน inner โดนลบไปกับ panel
                self.inline_inner = None
            self.inline_panel.setParent(None)
            self.inline_panel.deleteLater()
            self.inline_panel = None