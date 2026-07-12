from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap
from src.gui.pages.sub_pages.embed.pipeline_constants import STEP_META

from src.core.configurable.config_mode import (
    ExtractSession, extract_nodes, read_yaml, required_resources,
)

ICON_DIR = Path(__file__).resolve().parents[3] / "assets" / "svg"
ICON_SIZE = 16


def res_label(res: str, hints: dict) -> str:
    """แปลง resource id → ข้อความอ่านง่ายสำหรับ needs/provides
    file:X#i → ชื่อไฟล์ (จาก hints) · recovered:X / payload:X → 'จาก X'"""
    if res.startswith("file:"):
        return hints.get(res, res[len("file:"):].split("#")[0])
    if res.startswith("recovered:"):
        return f"recovered file: {res[len('recovered:'):]}"
    if res.startswith("payload:"):
        return f"secret: {res[len('payload:'):]}"
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
        self.session = None              # ExtractSession ระหว่างรัน (คงอยู่ข้าม on_run/_retry_node — resume ได้)
        self.workflow_rows = {}          # embed_id -> {"row","status_label","retry_btn"} สำหรับอัปเดตสถานะสด
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
        main.addLayout(self.build_execution_bar())

        scroll.setWidget(content)
        page_layout.addWidget(scroll)

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
        self.workflow_hint = QLabel("The ordered extract steps will appear here after import.")
        self.workflow_hint.setObjectName("hintLabel")
        self.workflow_hint.setWordWrap(True)
        layout.addWidget(self.workflow_hint)
        layout.addLayout(self.workflow_layout)
        return card

    # ── 4) Execute bar ──
    def build_execution_bar(self):
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(8)

        status_card = QFrame()
        status_card.setObjectName("card")
        sl = QVBoxLayout(status_card)
        self.status_label = QLabel("Status: Ready")
        self.status_label.setObjectName("statusLabel")
        sl.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("loadingIndicator")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        sl.addWidget(self.progress_bar)
        bar.addWidget(status_card, 1)

        self.run_btn = QPushButton(" Run Extract Pipeline")
        self.run_btn.setObjectName("PrimaryActionBtn")
        self.run_btn.setFixedHeight(50)
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "lock-open.svg", color_hex="#FFFFFF", size=ICON_SIZE)))
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self.on_run)
        bar.addWidget(self.run_btn)
        return bar

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
        self.session = None   # config ใหม่ — session เก่า (ถ้ามี) ใช้ต่อไม่ได้แล้ว
        self.import_btn.setText(f" {Path(path).name}")
        self._populate_resources(config)
        self._populate_workflow(config)
        self.run_btn.setEnabled(True)
        self.run_btn.setText(" Run Extract Pipeline")
        self.status_label.setText("Status: Config loaded — attach the required files, then run.")

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
            self.resources_layout.addWidget(row)
            self.resource_rows.append(row)

    def _populate_workflow(self, config):
        self._clear_layout(self.workflow_layout)
        self.workflow_rows = {}
        nodes = extract_nodes(config)
        hints = config.get("resources", {})
        self.workflow_hint.setVisible(not nodes)
        for i, node in enumerate(nodes):
            row, refs = self._step_row(i + 1, node, hints)
            self.workflow_layout.addWidget(row)
            self.workflow_rows[node["embed_id"]] = refs

    def _step_row(self, n, node, hints):
        """คืน (row widget, {"row","status_label","retry_btn","result_label"}) — เก็บ ref ไว้ใน
        workflow_rows เพื่อให้ _refresh_workflow_status() อัปเดตสถานะ + ผลที่แกะได้สดระหว่างรัน"""
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
        col.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title = QLabel(f"{node['embed_id']}  —  {meta['label']}")
        title.setObjectName("extractStepTitle")
        title.setProperty("accentColor", meta["accent"])
        title_row.addWidget(title)
        if node.get("decrypt"):
            lock_icon = QLabel()
            lock_icon.setPixmap(create_icon_pixmap(ICON_DIR / "lock.svg", color_hex="#F59E0F", size=13))
            lock_icon.setToolTip("Needs a password / private key to decrypt")
            title_row.addWidget(lock_icon)
        title_row.addStretch()
        col.addLayout(title_row)

        needs = ", ".join(res_label(r, hints) for r in node.get("needs", []))
        provides = ", ".join(res_label(r, hints) for r in node.get("provides", []))
        sub = QLabel(f"needs: {needs}  →  provides: {provides}")
        sub.setObjectName("extractStepSub")
        sub.setWordWrap(True)
        col.addWidget(sub)

        status_label = QLabel("Pending")
        status_label.setObjectName("extractStepStatus")
        col.addWidget(status_label)

        # โชว์ผลที่แกะได้จาก step นี้ทันทีที่เสร็จ (ไม่ต้องรอ popup สรุปตอนจบ) — ข้อความ select
        # ได้ด้วยเมาส์ (ไม่มีปุ่ม Copy แยก) เพื่อให้ copy เอาไปกรอกเป็น secret ของ step ถัดไปได้ตรง ๆ
        # เช่น เห็น 'Part1: Pass' + 'Part2: word' ก่อนจะโดนถาม password ของ step ที่เข้ารหัส
        result_label = QLabel("")
        result_label.setObjectName("extractStepResult")
        result_label.setWordWrap(True)
        result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        result_label.setCursor(Qt.CursorShape.IBeamCursor)
        result_label.setVisible(False)
        col.addWidget(result_label)

        rl.addLayout(col, 1)

        # icon placeholder: ยังไม่มี retry/refresh icon โดยเฉพาะใน assets — ใช้ key.svg ไปก่อน
        # (สื่อว่าต้องกรอก credential) เปลี่ยนได้ทีหลังถ้ามี icon ที่เหมาะกว่า
        retry_btn = QPushButton(" Retry")
        retry_btn.setObjectName("SecondaryBtn")
        retry_btn.setProperty("textColor", "white")
        retry_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "key.svg", color_hex="#FFFFFF", size=ICON_SIZE)))
        retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        retry_btn.setVisible(False)
        retry_btn.clicked.connect(lambda: self._retry_node(node))
        rl.addWidget(retry_btn)

        return row, {"row": row, "status_label": status_label, "retry_btn": retry_btn, "result_label": result_label}

    # ── Run handler — interactive, resumable: รันทุกอย่างที่ไม่ต้องใช้ secret ก่อนเสมอ, step ที่
    # เข้ารหัสถามทีเดียวตอนเพิ่ง ready (ถ้า cancel/ไม่รู้ตอนนี้ → ข้ามไปก่อน ไม่ abort ทั้งหมด —
    # กด Retry ที่แถวนั้นทีหลังได้เรื่อย ๆ หลังเห็นเบาะแสจาก step อื่นที่แกะออกมาได้แล้ว) ──
    def on_run(self):
        if not self.extract_config:
            return
        if self.session is None:
            missing = [r for r in self.resource_rows if not r.file_path]
            if missing:
                QMessageBox.warning(self, "Run Extract", "Please attach all required files first.")
                return
            resource_files = {r.resource_id: r.file_path for r in self.resource_rows}
            self.session = ExtractSession(self.extract_config, resource_files)

        self.status_label.setText("Status: Extracting...")
        try:
            self._run_ready_and_ask()
            while not self.session.is_done:
                blocked_ready = [n for n in self.session.ready_nodes() if n.get("decrypt")]
                if not blocked_ready:
                    break   # ไม่มีอะไรพร้อมรันเพิ่มแล้ว (ต้องรอ node อื่นก่อน ไม่ใช่รอ secret)
                progressed = self._ask_and_run(blocked_ready)
                self._run_ready_and_ask()
                if not progressed:
                    break   # ผู้ใช้ cancel ทุกตัวที่ถามได้รอบนี้ — หยุดรอกด Retry เอง
        except Exception as e:
            self.status_label.setText("Status: Extraction failed.")
            QMessageBox.critical(self, "Run Extract", f"Extraction failed:\n{e}")
            self._refresh_workflow_status()
            return

        self._refresh_workflow_status()
        self._finish_or_wait()

    def _run_ready_and_ask(self):
        self.session.run_ready_without_secrets()

    def _ask_and_run(self, nodes: list) -> bool:
        """ถาม secret ทีละ node ใน nodes แล้วรันถ้าได้คำตอบ · คืน True ถ้ามีอย่างน้อย 1 node คืบหน้า"""
        progressed = False
        for node in nodes:
            secret = self._ask_secret(node)
            if secret is None:
                continue   # ยังไม่รู้ตอนนี้ — ข้ามไปก่อน ไม่ถามซ้ำจนกว่าจะกด Retry
            self.session.run_node(node, secret)
            progressed = True
        return progressed

    def _ask_secret(self, node: dict):
        """ถาม password/private key สำหรับ node เดียว · คืน None ถ้าผู้ใช้ cancel/ไม่กรอก"""
        decrypt = node["decrypt"]
        eid = node["embed_id"]
        if decrypt["mode"] == "symmetric":
            pw, ok = QInputDialog.getText(
                self, "Password required", f"Password for '{eid}':", QLineEdit.EchoMode.Password
            )
            return {"password": pw} if ok else None
        if decrypt["mode"] == "asymmetric":
            key, _ = QFileDialog.getOpenFileName(
                self, f"Private key for '{eid}'", "", "Key files (*.pem *.der *.ssh);;All files (*.*)"
            )
            return {"private_key_path": key} if key else None
        return {}

    def _retry_node(self, node: dict):
        """ปุ่ม Retry ต่อแถวที่ blocked — ถามใหม่แล้วรันต่อ (รวม node อื่นที่เพิ่งปลดล็อกด้วย)"""
        if self.session is None or not self.session.is_ready(node):
            return
        secret = self._ask_secret(node)
        if secret is None:
            return
        try:
            self.session.run_node(node, secret)
            self._run_ready_and_ask()
        except Exception as e:
            QMessageBox.critical(self, "Run Extract", f"Extraction failed:\n{e}")
        self._refresh_workflow_status()
        self._finish_or_wait()

    def _refresh_workflow_status(self):
        """อัปเดต Pending/Done/Blocked + โชว์-ซ่อนปุ่ม Retry + preview ผลที่แกะได้ต่อแถว ให้ตรงกับ
        session ปัจจุบัน"""
        if self.session is None:
            return
        for node in self.session.nodes:
            refs = self.workflow_rows.get(node["embed_id"])
            if not refs:
                continue
            done = node["embed_id"] in self.session.done_ids
            blocked = (not done) and self.session.is_ready(node) and bool(node.get("decrypt"))
            status = "done" if done else ("blocked" if blocked else "pending")
            refs["status_label"].setText({"done": "Done", "blocked": "Blocked — needs password/key", "pending": "Pending"}[status])
            refs["retry_btn"].setVisible(blocked)
            refs["row"].setProperty("stepStatus", status)
            refs["row"].style().unpolish(refs["row"])
            refs["row"].style().polish(refs["row"])

            preview = self._result_preview(node) if done else ""
            refs["result_label"].setText(preview)
            refs["result_label"].setVisible(bool(preview))

    def _result_preview(self, node: dict) -> str:
        """ข้อความ preview สั้น ๆ ของสิ่งที่ step นี้แกะได้ — โชว์ทันทีที่เสร็จ ไม่ต้องรอ popup
        สรุปตอนจบ ให้เห็นเบาะแส (เช่น password fragment จาก metadata) ก่อนจะโดนถาม secret ของ
        step ถัดไป · เลือกได้เฉพาะ payload ของตัวเอง (ไม่ยุ่งกับไฟล์ที่ผลิตให้ step อื่นไปกินต่อ)"""
        value = self.session.recovered.get(f"payload:{node['embed_id']}")
        if value is None:
            n_files = sum(1 for p in node["provides"] if p.startswith("file:"))
            return f"→ produced {n_files} file(s) for a later step" if n_files else ""
        if isinstance(value, str):
            # ค่าที่เป็น path ไฟล์จริง (เช่น Locomotive คืน path ไฟล์ไบนารี/zip) ไม่ใช่ text ให้อ่าน
            if Path(value).exists():
                return f"Recovered file: {Path(value).name}"
            return f'Recovered: "{value}"'
        if isinstance(value, dict):
            lines = []
            for key, v in value.items():
                if key == "APIC":
                    n = len(v) if isinstance(v, list) else 1
                    lines.append(f"{n} image(s) recovered")
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict) and "text" in item:
                            lines.append(f"{item.get('desc') or key}: {item['text']}")
                        else:
                            lines.append(f"{key}: {item}")
                else:
                    lines.append(f"{key}: {v}")
            return "  |  ".join(lines) if lines else ""
        return str(value)

    def _finish_or_wait(self):
        if self.session.is_done:
            self.progress_bar.setValue(100)
            self._show_results(self.session.recovered)
            self.status_label.setText("Status: Extraction complete.")
            self.run_btn.setEnabled(False)
        else:
            n_left = len(self.session.remaining_nodes())
            n_total = len(self.session.nodes)
            self.progress_bar.setValue(round((n_total - n_left) / n_total * 100))
            self.status_label.setText(
                f"Status: {n_left} of {n_total} step(s) left — click Retry on a blocked step below once you know its password/key."
            )
            self.run_btn.setText(" Continue Extraction")

    def _show_results(self, recovered: dict):
        lines = []
        for res, value in recovered.items():
            if res.startswith("payload:"):   # ความลับจริงที่กู้ได้ (recovered:* เป็นไฟล์ชั้นในระหว่างทาง)
                who = res[len("payload:"):]
                shown = value if not isinstance(value, str) else value
                lines.append(f"- {who}:\n    {shown}")
        body = "\n\n".join(lines) if lines else "(no text payloads — check the extract workspace for recovered files)"
        QMessageBox.information(self, "Extraction Result", f"Recovered {len(lines)} secret(s):\n\n{body}")
