from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QFrame, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from src.gui.pages.sub_pages.embed.pipeline_constants import STEP_META


# ══════════════════════════════════════════════════════════════════════════
# Step config inner widgets + shells
#   - LSB reuse widget จริง (LSBEmbedInputs) จาก tab Standalone
#   - ชนิดอื่น (loco/metadata) ใช้ PlaceholderInputs ไปก่อน (pilot ทำ LSB)
#   - StepConfigDialog (popup) / StepConfigPanel (inline) = "เปลือก" 2 แบบ
#     ที่ห่อ inner widget ตัวเดียวกัน + ปุ่ม Save/Cancel
# ══════════════════════════════════════════════════════════════════════════
class PlaceholderInputs(QWidget):
    """inner แบบย่อสำหรับ step ที่ยังไม่ได้ทำ reuse (loco/metadata ใน pilot นี้)"""

    def __init__(self, idx, step_type):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        name_label = QLabel("Output resource name")
        name_label.setObjectName("formLabel")
        layout.addWidget(name_label)

        self.name_input = QLineEdit()
        self.name_input.setObjectName("formInput")
        self.name_input.setText(f"step{idx + 1}_out")
        layout.addWidget(self.name_input)

        note = QLabel(
            f"(ยังไม่ทำ reuse ของชนิด {STEP_META[step_type]['label']}) — pilot รอบนี้ทำ LSB++ ก่อน "
            "ของจริงจะ reuse widget จากหน้า Standalone เหมือน LSB"
        )
        note.setObjectName("hintLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

    def output_name(self):
        return self.name_input.text().strip()


class StepHeader(QFrame):
    """หัว step config — แถวบน: ชื่อ step (ซ้าย) + ช่องแก้ Step ID (ขวา) · แถวล่าง: Guidenote
    Step ID เป็น primary key แก้ได้ · is_custom = True เมื่อผู้ใช้พิมพ์เอง (จะไม่ให้ระบบ
    auto-regenerate ทับ) — textEdited ยิงเฉพาะตอนพิมพ์เอง ไม่ยิงตอน setText โปรแกรม
    Guidenote = คำใบ้/คำอธิบายที่ผู้ส่งเขียนทิ้งไว้ให้ผู้รับเห็นตอนถอด step นี้ (optional) —
    ไหลไปติดบน extract-node ให้หน้า Extract โชว์ (concept เดิมจาก config_design/example/config_1.yaml)"""

    def __init__(self, title, step_id_default, initial_custom=False, guidenote_default=""):
        super().__init__()
        self._custom = initial_custom

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(8)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("cardTitle")
        id_label = QLabel("Step ID")
        id_label.setObjectName("formLabel")
        self.step_id_edit = QLineEdit(step_id_default)
        self.step_id_edit.setObjectName("formInput")
        self.step_id_edit.setFixedWidth(300)
        self.step_id_edit.textEdited.connect(lambda _: setattr(self, "_custom", True))
        row.addWidget(title_lbl)
        row.addStretch()
        row.addWidget(id_label)
        row.addWidget(self.step_id_edit)
        outer.addLayout(row)

        note_row = QHBoxLayout()
        note_row.setSpacing(8)
        note_label = QLabel("Guidenote")
        note_label.setObjectName("formLabel")
        self.guidenote_edit = QLineEdit(guidenote_default)
        self.guidenote_edit.setObjectName("formInput")
        self.guidenote_edit.setPlaceholderText(
            "Optional — a hint shown to the receiver when they reach this step during extraction"
        )
        note_row.addWidget(note_label)
        note_row.addWidget(self.guidenote_edit, 1)
        outer.addLayout(note_row)

    def step_id(self) -> str:
        return self.step_id_edit.text().strip()

    def is_custom(self) -> bool:
        return self._custom

    def guidenote(self) -> str:
        return self.guidenote_edit.text().strip()


class StepConfigDialog(QDialog):
    """Popup shell — ห่อ inner widget (reuse) + ปุ่ม Save/Cancel
    commit(step_id, is_custom, guidenote) คืน bool: ถ้า False (validate ไม่ผ่าน) จะไม่ปิด dialog"""

    def __init__(self, title, step_id_default, initial_custom, inner, commit, parent=None, guidenote_default=""):
        super().__init__(parent)
        self._commit = commit
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(900, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.header = StepHeader(title, step_id_default, initial_custom, guidenote_default)
        layout.addWidget(self.header)

        scroll = QScrollArea()
        scroll.setObjectName("pipelineScroll")
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save Step")
        save_btn.setObjectName("PrimaryActionBtn")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._try_save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _try_save(self):
        if self._commit(self.header.step_id(), self.header.is_custom(), self.header.guidenote()):
            self.accept()


class StepConfigPanel(QFrame):
    """Inline shell — inner widget (reuse) ตัวเดียวกับ popup แต่ฝังในหน้าเลย"""

    saved = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, title, step_id_default, initial_custom, inner, commit, guidenote_default=""):
        super().__init__()
        self._commit = commit
        self.setObjectName("card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        self.header = StepHeader(title, step_id_default, initial_custom, guidenote_default)
        layout.addWidget(self.header)

        layout.addWidget(inner)
        inner.show()   # inner อาจโดน park_inner() สั่ง .hide() ไว้จากรอบก่อน — addWidget() ไม่ได้ un-hide ให้ (ต่างจาก QScrollArea.setWidget() ที่ StepConfigDialog ใช้)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.cancelled.emit)
        save_btn = QPushButton("Save Step")
        save_btn.setObjectName("PrimaryActionBtn")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._try_save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _try_save(self):
        if self._commit(self.header.step_id(), self.header.is_custom(), self.header.guidenote()):
            self.saved.emit()
