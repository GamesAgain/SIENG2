from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap
from src.gui.components.result_viewers import PayloadResultViewer
from src.gui.pages.sub_pages.embed.pipeline_constants import STEP_META
from src.gui.tabs.extract.metadata_extract import AllFramesDialog, MP3MetadataViewer, PNGAllChunksDialog, PNGMetadataViewer

from src.core.configurable.config_mode import (
    ExtractSession, extract_nodes, order_extract_nodes, read_yaml, required_resources,
)

ICON_DIR = Path(__file__).resolve().parents[3] / "assets" / "svg"
ICON_SIZE = 16


def res_label(res: str, hints: dict) -> str:
    """แปลง resource id → ข้อความอ่านง่ายสำหรับ Need
    file:X#i → ชื่อไฟล์ (จาก hints) · payload:X → 'จาก X'"""
    if res.startswith("file:"):
        return hints.get(res, res[len("file:"):].split("#")[0])
    if res.startswith("payload:"):
        return f"output of {res[len('payload:'):]}"
    return res


# ══════════════════════════════════════════════════════════════════════════
# 1 แถวของไฟล์ทรัพยากรตั้งต้น — โชว์ชื่อไฟล์ที่ต้องการ + ปุ่มแนบไฟล์จริง
# ══════════════════════════════════════════════════════════════════════════
class ResourceRow(QFrame):
    attached = pyqtSignal()

    def __init__(self, resource_id: str, suggested_name: str):
        super().__init__()
        self.resource_id = resource_id
        self.file_path = None
        self.setObjectName("extractResourceRow")
        self.setProperty("attached", False)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)

        icon = QLabel()
        icon.setPixmap(create_icon_pixmap(ICON_DIR / "file-import.svg", color_hex="#38BDF8", size=16))
        name = QLabel(suggested_name)
        name.setObjectName("extractResourceName")

        self.status = QLabel("")
        self.status.setObjectName("extractResourceStatus")

        self.attach_btn = QPushButton(" Attach File")
        self.attach_btn.setObjectName("SecondaryBtn")
        self.attach_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.attach_btn.clicked.connect(self._browse)

        row.addWidget(icon)
        row.addWidget(name)
        row.addStretch()
        row.addWidget(self.status)
        row.addWidget(self.attach_btn)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Attach file", "", "Stego files (*.png *.mp3);;All files (*.*)")
        if not path:
            return
        self.file_path = path
        self.status.setText(f"✓ {Path(path).name}")
        self.attach_btn.setText(" Change")
        self.setProperty("attached", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.attached.emit()


# ══════════════════════════════════════════════════════════════════════════
# ExtractConfigurablePage
# ══════════════════════════════════════════════════════════════════════════
class ExtractConfigurablePage(QFrame):
    def __init__(self):
        super().__init__()
        self.extract_config = None       # dict ที่ import มา
        self.resource_rows = []          # ResourceRow ต่อไฟล์ตั้งต้น
        self.session = None              # ExtractSession — สร้างตอน import, res_path อัปเดตสดตามที่แนบไฟล์
        self.workflow_rows = {}          # embed_id -> refs สำหรับอัปเดตสถานะสด
        self.setup_ui()

    def setup_ui(self):
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("pipelineScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("pipelineScrollContent")
        main = QVBoxLayout(content)
        main.setContentsMargins(4, 11, 4, 4)
        main.setSpacing(10)

        main.addWidget(self.build_import_card())
        main.addWidget(self.build_resources_card())
        main.addWidget(self.build_workflow_card())
        main.addStretch()

        scroll.setWidget(content)
        page_layout.addWidget(scroll)

        status_layout = QVBoxLayout()
        status_layout.setContentsMargins(4, 0, 4, 4)
        status_layout.addWidget(self.build_status_bar())
        page_layout.addLayout(status_layout)

    def _card(self, icon_name, title):
        """การ์ดเปล่า + หัวข้อ (icon + title) คืน (card_frame, body_layout ที่ต่อเนื้อหาได้)"""
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        title_row = QFrame()
        title_row.setObjectName("titleContainer")
        tl = QHBoxLayout(title_row)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self._icon(icon_name))
        label = QLabel(title)
        label.setObjectName("cardTitle")
        tl.addWidget(label)
        tl.addStretch()
        layout.addWidget(title_row)
        return card, layout

    @staticmethod
    def _icon(name):
        lbl = QLabel()
        lbl.setPixmap(create_icon_pixmap(ICON_DIR / name, size=ICON_SIZE))
        return lbl

    # ── 1) Import ──
    def build_import_card(self):
        card, layout = self._card("file-import.svg", "Import Config")
        self.import_btn = QPushButton(" Browse extract_config.yaml")
        self.import_btn.setObjectName("SecondaryBtn")
        self.import_btn.setProperty("textColor", "white")
        self.import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "upload.svg", color_hex="#FFFFFF", size=ICON_SIZE)))
        self.import_btn.clicked.connect(self.on_import)
        row = QHBoxLayout()
        row.addWidget(self.import_btn)
        row.addStretch()
        layout.addLayout(row)
        return card

    # ── 2) Required Initial Resources ──
    def build_resources_card(self):
        card, layout = self._card("folder-open.svg", "Required Initial Resources")
        self.resources_layout = QVBoxLayout()
        self.resources_layout.setSpacing(8)
        self.resources_hint = QLabel("Import an extract config to see the files the receiver must provide.")
        self.resources_hint.setObjectName("hintLabel")
        self.resources_hint.setWordWrap(True)
        layout.addWidget(self.resources_hint)
        layout.addLayout(self.resources_layout)
        return card

    # ── 3) Extract Workflow ──
    def build_workflow_card(self):
        card, layout = self._card("list-numbers.svg", "Extract Workflow")
        self.workflow_layout = QVBoxLayout()
        self.workflow_layout.setSpacing(8)
        self.workflow_hint = QLabel("The ordered extract steps will appear here after import. Extract each step yourself once its required file(s) are ready.")
        self.workflow_hint.setObjectName("hintLabel")
        self.workflow_hint.setWordWrap(True)
        layout.addWidget(self.workflow_hint)
        layout.addLayout(self.workflow_layout)
        return card

    # ── 4) Status bar — ไม่มีปุ่ม Execute (ถอดทีละการ์ดเองแล้ว) แค่โชว์ความคืบหน้ารวม ──
    def build_status_bar(self):
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        self.status_label = QLabel("Status: Ready")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("loadingIndicator")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        return card

    # ── Import handler → populate resources + workflow ──
    def on_import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Extract Config", "", "YAML config (*.yaml *.yml)")
        if not path:
            return
        try:
            config = read_yaml(path)
            if not extract_nodes(config):
                raise ValueError("This file has no 'workflows.extract' — pick an extract_config.yaml.")
        except Exception as e:
            QMessageBox.critical(self, "Import Config", f"Could not load config:\n{e}")
            return

        self.extract_config = config
        self.session = ExtractSession(config, {})   # res_path เริ่มว่าง เติมสดทีละไฟล์ตอนแนบ
        self.import_btn.setText(f" {Path(path).name}")
        self._populate_resources(config)
        self._populate_workflow(config)
        self._refresh_all_rows()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _populate_resources(self, config):
        self._clear_layout(self.resources_layout)
        self.resource_rows = []
        resources = required_resources(config)
        self.resources_hint.setVisible(not resources)
        for res_id, suggested in resources:
            row = ResourceRow(res_id, suggested)
            row.attached.connect(lambda r=row: self._on_resource_attached(r))
            self.resources_layout.addWidget(row)
            self.resource_rows.append(row)

    def _on_resource_attached(self, row: ResourceRow):
        self.session.res_path[row.resource_id] = row.file_path
        self._refresh_all_rows()

    def _populate_workflow(self, config):
        self._clear_layout(self.workflow_layout)
        self.workflow_rows = {}
        nodes = extract_nodes(config)
        hints = config.get("resources", {})
        self.workflow_hint.setVisible(not nodes)
        if not nodes:
            return

        # จัดลำดับการ์ดใหม่ด้วย heuristic เดียวกับ generate (เผยเบาะแสก่อน step ที่ล็อกรหัส) —
        # ไม่เชื่อลำดับดิบใน .yaml เผื่อ config เก่าถูก generate ด้วย sort เวอร์ชันก่อนหน้า
        provided = {p for nd in nodes for p in nd["provides"]}
        initial = {r for nd in nodes for r in nd["needs"] if r not in provided}
        nodes = order_extract_nodes(nodes, initial)

        # resource_id → เลข step ที่ผลิตมัน (ใช้แปลง need ที่เป็นไฟล์กลางให้เป็น 'จาก Step #N')
        res_to_stepnum = {p: i for i, nd in enumerate(nodes, 1) for p in nd["provides"]}

        for i, node in enumerate(nodes, 1):
            row, refs = self._step_row(i, node, hints, res_to_stepnum)
            self.workflow_layout.addWidget(row)
            self.workflow_rows[node["embed_id"]] = refs

    def _need_text(self, node: dict, hints: dict, res_to_stepnum: dict) -> str:
        """Need ที่ผู้รับอ่านรู้เรื่อง: ไฟล์ตั้งต้นโชว์ชื่อไฟล์ (ที่ต้องแนบ), ไฟล์กลางโชว์ 'จาก Step #N'
        (ต้องถอด step นั้นก่อน) — แทนการโชว์ resource id ดิบ (file:pdf_fragment#0) ที่ผู้รับงง"""
        parts = []
        for r in node.get("needs", []):
            if r in hints:                      # ไฟล์ตั้งต้นที่ผู้รับอัปโหลดเอง
                label = hints[r]
            elif r in res_to_stepnum:           # ไฟล์กลางจาก step ก่อนหน้า
                label = f"from Step #{res_to_stepnum[r]}"
            else:
                label = res_label(r, hints)
            if label not in parts:              # dedup (เช่น 2 need ที่มาจาก step เดียวกัน)
                parts.append(label)
        return ", ".join(parts) if parts else "(nothing)"

    # ── 1 การ์ด step: #no · {Technique} — {step_id} · Need · Extracted Data · Guidenote ·
    # (ถ้าเข้ารหัส) ช่องกรอก secret แทรกในตัว · [View Result][Extract] ──
    def _step_row(self, n, node, hints, res_to_stepnum):
        meta = STEP_META.get(node["module"], {"label": node["module"], "accent": "blue"})
        row = QFrame()
        row.setObjectName("extractStepRow")
        row.setProperty("accentColor", meta["accent"])
        row.setProperty("stepStatus", "pending")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(12, 10, 12, 10)
        rl.setSpacing(12)

        no = QLabel(f"#{n}")
        no.setObjectName("extractStepNo")
        rl.addWidget(no)

        col = QVBoxLayout()
        col.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title = QLabel(f"{meta['label']} — {node['embed_id']}")
        title.setObjectName("extractStepTitle")
        title.setProperty("accentColor", meta["accent"])
        title_row.addWidget(title)
        if node.get("decrypt"):
            lock_icon = QLabel()
            lock_icon.setPixmap(create_icon_pixmap(ICON_DIR / "lock.svg", color_hex="#F59E0F", size=13))
            lock_icon.setToolTip("Needs a password / private key to decrypt")
            title_row.addWidget(lock_icon)
        status_label = QLabel("Pending")
        status_label.setObjectName("extractStepStatus")
        title_row.addWidget(status_label)
        title_row.addStretch()
        col.addLayout(title_row)

        need_label = QLabel(f"Need: {self._need_text(node, hints, res_to_stepnum)}")
        need_label.setObjectName("extractStepSub")
        need_label.setWordWrap(True)
        col.addWidget(need_label)

        extracted_label = QLabel("Extracted: not extracted yet")
        extracted_label.setObjectName("extractStepSub")
        extracted_label.setWordWrap(True)
        extracted_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        col.addWidget(extracted_label)

        if node.get("guidenote"):
            guidenote_label = QLabel(f"Guidenote: {node['guidenote']}")
            guidenote_label.setObjectName("extractStepGuidenote")
            guidenote_label.setWordWrap(True)
            col.addWidget(guidenote_label)

        refs = {
            "row": row, "status_label": status_label, "extracted_label": extracted_label,
            "secret_row": None, "secret_password_edit": None, "key_path": None, "key_path_label": None,
        }

        if node.get("decrypt"):
            secret_row = QHBoxLayout()
            secret_row.setSpacing(8)
            if node["decrypt"]["mode"] == "symmetric":
                pw_edit = QLineEdit()
                pw_edit.setObjectName("formInput")
                pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
                pw_edit.setPlaceholderText("Password for this step")
                secret_row.addWidget(pw_edit, 1)
                refs["secret_password_edit"] = pw_edit
            else:
                key_btn = QPushButton(" Choose private key...")
                key_btn.setObjectName("SecondaryBtn")
                key_btn.setProperty("textColor", "white")
                key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                key_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "key.svg", color_hex="#FFFFFF", size=ICON_SIZE)))
                key_btn.clicked.connect(lambda: self._browse_key_for_row(node))
                key_path_label = QLabel("No file selected")
                key_path_label.setObjectName("hintLabel")
                secret_row.addWidget(key_btn)
                secret_row.addWidget(key_path_label, 1)
                refs["key_path_label"] = key_path_label
            secret_row_frame = QFrame()
            secret_row_frame.setLayout(secret_row)
            col.addWidget(secret_row_frame)
            refs["secret_row"] = secret_row_frame

        rl.addLayout(col, 1)

        actions = QVBoxLayout()
        actions.setSpacing(6)
        view_btn = QPushButton(" View Result")
        view_btn.setObjectName("SecondaryBtn")
        view_btn.setProperty("textColor", "white")
        view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "file-search.svg", color_hex="#FFFFFF", size=ICON_SIZE)))
        view_btn.setEnabled(False)
        view_btn.clicked.connect(lambda: self._on_view_result_clicked(node))
        extract_btn = QPushButton(" Extract")
        extract_btn.setObjectName("PrimaryActionBtn")
        extract_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        extract_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "lock-open.svg", color_hex="#FFFFFF", size=ICON_SIZE)))
        extract_btn.setEnabled(False)
        extract_btn.clicked.connect(lambda: self._on_extract_clicked(node))
        actions.addWidget(view_btn)
        actions.addWidget(extract_btn)
        rl.addLayout(actions)

        refs["view_btn"] = view_btn
        refs["extract_btn"] = extract_btn
        return row, refs

    def _browse_key_for_row(self, node: dict):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Private key for '{node['embed_id']}'", "", "Key files (*.pem *.der *.ssh);;All files (*.*)"
        )
        if not path:
            return
        refs = self.workflow_rows[node["embed_id"]]
        refs["key_path"] = path
        refs["key_path_label"].setText(Path(path).name)

    # ── ปุ่ม Extract ต่อการ์ด — รันเฉพาะ node นี้ทีเดียว (ไม่ cascade ต่อให้เอง ต้องกดทีละการ์ด) ──
    def _on_extract_clicked(self, node: dict):
        if self.session is None or not self.session.is_ready(node):
            QMessageBox.warning(
                self, "Extract",
                "This step isn't ready yet — extract the step(s) it depends on first, or attach any missing files above."
            )
            return

        secret = None
        if node.get("decrypt"):
            refs = self.workflow_rows[node["embed_id"]]
            if node["decrypt"]["mode"] == "symmetric":
                pw = refs["secret_password_edit"].text()
                if not pw:
                    QMessageBox.warning(self, "Extract", "Enter a password for this step first.")
                    return
                secret = {"password": pw}
            else:
                if not refs["key_path"]:
                    QMessageBox.warning(self, "Extract", "Select a private key file for this step first.")
                    return
                secret = {"private_key_path": refs["key_path"]}

        try:
            self.session.run_node(node, secret)
        except Exception as e:
            QMessageBox.critical(self, "Extract", f"Extraction failed:\n{e}")
            return
        self._refresh_all_rows()

    # ── ปุ่ม View Result — เปิด dialog ที่ reuse ตัว viewer เดียวกับ Standalone extract ──
    def _on_view_result_clicked(self, node: dict):
        eid, module = node["embed_id"], node["module"]
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Result — {eid}")
        layout = QVBoxLayout(dialog)

        is_mp3 = False
        if module == "metadata":
            source_path = self.session.res_path.get(node["needs"][0], "")
            is_mp3 = source_path.lower().endswith(".mp3")
            viewer = MP3MetadataViewer() if is_mp3 else PNGMetadataViewer()
            viewer.load_file(source_path)
            layout.addWidget(viewer)
        else:
            # ผลจริงของ node นี้อาจอยู่ที่ payload:eid (ผลลัพธ์สุดท้าย) หรือ file:eid#i (ไฟล์
            # กลางที่ป้อนให้ step ถัดไปกินต่อ — เช่น Locomotive ที่ recover ภาพซ้อนอีกชั้นหนึ่ง ไม่ใช่
            # secret ปลายทาง) แล้วแต่ node นี้เป็น "ปลายทาง" หรือ "ทางผ่าน" — โชว์ทุกอันที่มีค่าจริง
            # (ปกติมีอันเดียว มีมากกว่า 1 เฉพาะ Locomotive ที่ payload มาจากหลาย producer พร้อมกัน)
            provided_ids = list(node["provides"])
            if f"payload:{eid}" not in provided_ids:
                provided_ids.insert(0, f"payload:{eid}")
            values = [self.session.recovered[p] for p in provided_ids if p in self.session.recovered]
            if not values:
                values = [None]

            scroll = QScrollArea()
            scroll.setObjectName("pipelineScroll")
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            content = QWidget()
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setSpacing(10)
            for value in values:
                sub_viewer = PayloadResultViewer()
                if isinstance(value, str) and Path(value).exists():
                    # Locomotive คืน path ไฟล์จริง — โชว์เป็นไฟล์ตามนามสกุลเดิม (.pdf เซฟเป็น .pdf)
                    # ตัดคำนำหน้า '{eid}_' ที่ engine เติมตอนเซฟลง workspace ออก ให้ default ชื่อสะอาด
                    name = Path(value).name
                    if name.startswith(eid + "_"):
                        name = name[len(eid) + 1:]
                    sub_viewer.show_result(Path(value).read_bytes(), name)
                else:
                    # lsbpp คืนข้อความล้วน
                    sub_viewer.show_text(str(value) if value is not None else "(no result to show)")
                content_layout.addWidget(sub_viewer)
            scroll.setWidget(content)
            layout.addWidget(scroll)

        close_row = QHBoxLayout()
        if module == "metadata":
            # เผื่อ guidenote บอกว่ารหัส/เบาะแสซ่อนอยู่ใน frame/chunk ที่ไม่ได้อยู่ใน TOC ของเราเอง
            # (เช่น "รหัสอยู่ใน COMM ของไฟล์นี้") — ต้อง scan ทุก frame/chunk ที่มีจริงในไฟล์ดิบ ๆ
            # ไม่ใช่แค่ที่ระบบ SIENG2 filter ให้ (ปุ่มนี้มีอยู่แล้วฝั่ง Standalone — reuse ตรง ๆ)
            scan_btn = QPushButton(f" View All {'Frames' if is_mp3 else 'Text Chunks'}")
            scan_btn.setObjectName("SecondaryBtn")
            scan_btn.setProperty("textColor", "white")
            scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            scan_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "report.svg", color_hex="#FFFFFF", size=ICON_SIZE)))
            if is_mp3:
                scan_btn.clicked.connect(lambda: AllFramesDialog(source_path, dialog).exec())
            else:
                scan_btn.clicked.connect(lambda: PNGAllChunksDialog(source_path, dialog).exec())
            close_row.addWidget(scan_btn)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("SecondaryBtn")
        close_btn.setProperty("textColor", "white")
        close_btn.clicked.connect(dialog.accept)
        close_row.addStretch()
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        dialog.resize(560, 620)
        dialog.exec()

    # ── อัปเดตสถานะ/ปุ่ม/preview ของทุกการ์ด ให้ตรงกับ session ปัจจุบัน ──
    def _refresh_all_rows(self):
        if self.session is None:
            return
        for node in self.session.nodes:
            refs = self.workflow_rows.get(node["embed_id"])
            if not refs:
                continue
            eid = node["embed_id"]
            done = eid in self.session.done_ids
            ready = self.session.is_ready(node)

            # 4 สถานะแยกด้วยตา: done(เขียว) / ready(ฟ้า พร้อมถอด) / locked(ส้ม รอกรอกรหัส) /
            # waiting(เทา รอ step ก่อนหน้า) — เดิม ready กับ waiting เป็นเทาเหมือนกัน แยกไม่ออก
            if done:
                status = "done"
            elif not ready:
                status = "waiting"
            elif node.get("decrypt"):
                status = "locked"
            else:
                status = "ready"
            refs["status_label"].setText({
                "done": "Done", "ready": "Ready to extract",
                "locked": "Ready — enter password/key", "waiting": "Waiting for earlier steps",
            }[status])
            # QSS มี stepStatus: done / ready / blocked(=locked ส้ม) / pending(=waiting เทา)
            refs["row"].setProperty("stepStatus", {"done": "done", "ready": "ready", "locked": "blocked", "waiting": "pending"}[status])
            refs["row"].style().unpolish(refs["row"])
            refs["row"].style().polish(refs["row"])

            refs["extract_btn"].setEnabled(ready and not done)
            refs["view_btn"].setEnabled(done)
            if refs["secret_row"] is not None:
                refs["secret_row"].setVisible(ready and not done)

            refs["extracted_label"].setText(f"Extracted: {self._extracted_summary(node)}" if done else "Extracted: not extracted yet")

        self._refresh_status_bar()

    def _refresh_status_bar(self):
        """สรุปความคืบหน้ารวม — ไม่มีปุ่ม Execute ตรงนี้แล้ว แค่โชว์ผลจากการกด Extract ทีละการ์ด"""
        total = len(self.session.nodes)
        done = len(self.session.done_ids)
        self.progress_bar.setValue(round(done / total * 100) if total else 0)
        if done == total:
            self.status_label.setText("Status: Extraction complete.")
        else:
            self.status_label.setText(f"Status: {done} of {total} step(s) extracted — use Extract on a card below.")

    def _extracted_summary(self, node: dict) -> str:
        """ตัวอย่างสั้น ๆ ของสิ่งที่ step นี้แกะได้ — รายละเอียดเต็มอยู่ใน View Result"""
        value = self.session.recovered.get(f"payload:{node['embed_id']}")
        if value is None:
            n_files = sum(1 for p in node["provides"] if p.startswith("file:"))
            return f"{n_files} file(s) passed to a later step" if n_files else "no readable output"
        if isinstance(value, dict):
            n_tags = sum(1 for k in value if k != "APIC")
            apic = value.get("APIC")
            n_imgs = len(apic) if isinstance(apic, list) else (1 if apic else 0)
            parts = []
            if n_tags:
                parts.append(f"{n_tags} tag(s)")
            if n_imgs:
                parts.append(f"{n_imgs} image(s)")
            return ", ".join(parts) if parts else "no tags found"
        if isinstance(value, str) and Path(value).exists():
            return f"file: {Path(value).name}"
        if isinstance(value, str):
            preview = value if len(value) <= 40 else value[:37] + "..."
            return f'"{preview}"'
        return str(value)
