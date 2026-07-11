from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton


class LinkedStepToggle(QFrame):
    """Toggle 'Manual Upload' / 'Linked from Step' — โผล่เฉพาะตอน step ถูกเปิดจากหน้า
    Configurable Pipeline (popup/inline) เพื่อเลือกว่า cover ของ step นี้จะให้ผู้ใช้
    อัปโหลดเองตามปกติ หรือ "ต่อ" จาก output ของ step ก่อนหน้าในพเพลไลน์แทน

    ตอนนี้เป็นแค่ UI toggle (mock) — ยังไม่ผูก logic สลับ widget จริง รอต่อ
    ในเฟสถัดไปเมื่อออกแบบ payload card เสร็จ"""

    modeChanged = pyqtSignal(bool)  # True = linked from step, False = manual upload

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("linkedStepToggleContainer")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)

        self.btn_manual = QPushButton("Manual Upload")
        self.btn_manual.setObjectName("linkedStepToggleBtn")
        self.btn_manual.setCheckable(True)
        self.btn_manual.setChecked(True)
        self.btn_manual.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_linked = QPushButton("Linked from Step")
        self.btn_linked.setObjectName("linkedStepToggleBtn")
        self.btn_linked.setCheckable(True)
        self.btn_linked.setCursor(Qt.CursorShape.PointingHandCursor)

        layout.addWidget(self.btn_manual)
        layout.addWidget(self.btn_linked)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.addButton(self.btn_manual, 0)
        self._group.addButton(self.btn_linked, 1)
        self._group.idClicked.connect(lambda button_id: self.modeChanged.emit(button_id == 1))

    def is_linked(self) -> bool:
        return self.btn_linked.isChecked()

    def set_linked(self, linked: bool):
        (self.btn_linked if linked else self.btn_manual).setChecked(True)
