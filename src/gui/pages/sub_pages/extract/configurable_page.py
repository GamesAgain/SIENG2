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
    extract_nodes, read_yaml, required_resources, run_extract_from_config,
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
        self.import_btn.setText(f" {Path(path).name}")
        self._populate_resources(config)
        self._populate_workflow(config)
        self.run_btn.setEnabled(True)
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
        nodes = extract_nodes(config)
        hints = config.get("resources", {})
        self.workflow_hint.setVisible(not nodes)
        for i, node in enumerate(nodes):
            self.workflow_layout.addWidget(self._step_row(i + 1, node, hints))

    def _step_row(self, n, node, hints):
        meta = STEP_META.get(node["module"], {"label": node["module"], "accent": "blue"})
        row = QFrame()
        row.setObjectName("extractStepRow")
        row.setProperty("accentColor", meta["accent"])
        rl = QHBoxLayout(row)
        rl.setContentsMargins(12, 10, 12, 10)
        rl.setSpacing(12)

        no = QLabel(f"#{n}")
        no.setObjectName("extractStepNo")
        rl.addWidget(no)

        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(f"{node['embed_id']}  —  {meta['label']}")
        title.setObjectName("extractStepTitle")
        title.setProperty("accentColor", meta["accent"])
        needs = ", ".join(res_label(r, hints) for r in node.get("needs", []))
        provides = ", ".join(res_label(r, hints) for r in node.get("provides", []))
        lock = "  🔒" if node.get("decrypt") else ""
        sub = QLabel(f"needs: {needs}  →  provides: {provides}{lock}")
        sub.setObjectName("extractStepSub")
        sub.setWordWrap(True)
        col.addWidget(title)
        col.addWidget(sub)
        rl.addLayout(col, 1)
        return row

    # ── Run handler ──
    def on_run(self):
        if not self.extract_config:
            return
        # 1) ทุก resource ต้องแนบไฟล์ครบ
        missing = [r for r in self.resource_rows if not r.file_path]
        if missing:
            QMessageBox.warning(self, "Run Extract", "Please attach all required files first.")
            return
        resource_files = {r.resource_id: r.file_path for r in self.resource_rows}

        # 2) ขอ secret ของ step ที่เข้ารหัส (ไม่ได้เก็บใน config)
        try:
            secrets = self._collect_secrets()
        except _Cancelled:
            return

        # 3) รันจริง
        self.status_label.setText("Extracting...")
        try:
            recovered = run_extract_from_config(self.extract_config, resource_files, secrets)
            self.progress_bar.setValue(100)
            self._show_results(recovered)
            self.status_label.setText("Status: Extraction complete.")
        except Exception as e:
            self.progress_bar.setValue(0)
            self.status_label.setText("Status: Extraction failed.")
            QMessageBox.critical(self, "Run Extract", f"Extraction failed:\n{e}")

    def _collect_secrets(self) -> dict:
        """ถาม password / private key ต่อ step ที่เข้ารหัส (ครั้งเดียวต่อ embed_id)"""
        secrets = {}
        for node in extract_nodes(self.extract_config):
            decrypt = node.get("decrypt")
            eid = node["embed_id"]
            if not decrypt or eid in secrets:
                continue
            if decrypt["mode"] == "symmetric":
                pw, ok = QInputDialog.getText(
                    self, "Password required", f"Password for '{eid}':", QLineEdit.EchoMode.Password
                )
                if not ok:
                    raise _Cancelled()
                secrets[eid] = {"password": pw}
            elif decrypt["mode"] == "asymmetric":
                key, _ = QFileDialog.getOpenFileName(
                    self, f"Private key for '{eid}'", "", "Key files (*.pem *.der *.ssh);;All files (*.*)"
                )
                if not key:
                    raise _Cancelled()
                secrets[eid] = {"private_key_path": key}
        return secrets

    def _show_results(self, recovered: dict):
        lines = []
        for res, value in recovered.items():
            if res.startswith("payload:"):   # ความลับจริงที่กู้ได้ (recovered:* เป็นไฟล์ชั้นในระหว่างทาง)
                who = res[len("payload:"):]
                shown = value if not isinstance(value, str) else value
                lines.append(f"• {who}:\n    {shown}")
        body = "\n\n".join(lines) if lines else "(no text payloads — check the extract workspace for recovered files)"
        QMessageBox.information(self, "Extraction Result", f"Recovered {len(lines)} secret(s):\n\n{body}")


class _Cancelled(Exception):
    """ผู้ใช้กดยกเลิกตอนถูกถาม secret"""
