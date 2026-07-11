from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from src.gui.components.gui_utils import create_icon_pixmap
from src.gui.pages.sub_pages.embed.pipeline_constants import (
    CARD_HEIGHT, CARD_WIDTH, CLOSE_BTN_SIZE, DOT_SIZE, ICON_DIR, OVERLAP, STEP_META, WRAP_HEIGHT, WRAP_WIDTH,
)

# ==========================================================================
# StepCard — การ์ด step 1 ใบ + จุดสถานะ + ปุ่มปิด (โผล่ตอน hover)
# หมายเหตุ: จุด/ปุ่มปิดต้องเป็น "พี่น้อง" ของการ์ด (ไม่ใช่ลูก) เพราะ Qt clip
# widget ลูกให้อยู่ในกรอบแม่ — badge ที่ยื่นออกนอกมุมจะโดนตัด ถ้าเป็นลูก
# ==========================================================================
class StepCard(QWidget):
    clicked = pyqtSignal()
    removeRequested = pyqtSignal()

    def __init__(self, step_type, sub_text, valid=False, parent=None):
        super().__init__(parent)
        meta = STEP_META[step_type]
        self.setFixedSize(WRAP_WIDTH, WRAP_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # การ์ดที่มองเห็น
        self.card = QFrame(self)
        self.card.setObjectName("stepCard")
        self.card.setProperty("accentColor", meta["accent"])
        self.card.setGeometry(OVERLAP, OVERLAP, CARD_WIDTH, CARD_HEIGHT)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(10, 6, 10, 6)
        card_layout.setSpacing(2)

        title = QLabel(meta["label"])
        title.setObjectName("stepCardTitle")
        title.setProperty("accentColor", meta["accent"])
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.sub_label = QLabel(sub_text)
        self.sub_label.setObjectName("stepCardSub")
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_label.setWordWrap(True)

        card_layout.addStretch()
        card_layout.addWidget(title)
        card_layout.addWidget(self.sub_label)
        card_layout.addStretch()

        # จุดสถานะ (มุมบนซ้าย) — พี่น้องของการ์ด
        self.dot = QLabel(self)
        self.dot.setObjectName("stepStatusDot")
        self.dot.setFixedSize(DOT_SIZE, DOT_SIZE)
        self.dot.move(OVERLAP - DOT_SIZE // 2, OVERLAP - DOT_SIZE // 2)

        # ปุ่มปิด (มุมบนขวา) — ซ่อนจนกว่าจะ hover
        self.close_btn = QPushButton(self)
        self.close_btn.setObjectName("stepCloseBtn")
        self.close_btn.setFixedSize(CLOSE_BTN_SIZE, CLOSE_BTN_SIZE)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "x.svg", color_hex="#FFFFFF", size=11)))
        self.close_btn.move(OVERLAP + CARD_WIDTH - CLOSE_BTN_SIZE // 2, OVERLAP - CLOSE_BTN_SIZE // 2)
        self.close_btn.clicked.connect(self.removeRequested.emit)
        self.close_btn.hide()

        self.set_valid(valid)

    def set_valid(self, valid):
        self.dot.setProperty("state", "valid" if valid else "invalid")
        self.dot.setToolTip("Inputs complete" if valid else "Missing inputs")
        self._repolish(self.dot)

    def set_sub(self, text):
        self.sub_label.setText(text)

    @staticmethod
    def _repolish(widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def enterEvent(self, event):
        self.close_btn.show()
        self.close_btn.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.close_btn.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def center_in_band(inner, inner_w, inner_h):
    """วาง widget ให้อยู่กึ่งกลางแนวตั้ง 'ในแถบของการ์ด' (y = OVERLAP..OVERLAP+CARD_H)
    เพื่อให้ arrow / ปุ่มเพิ่ม อยู่ระดับเดียวกับกึ่งกลางการ์ดพอดี ไม่เบี้ยวขึ้นบน"""
    container = QWidget()
    container.setFixedSize(inner_w, WRAP_HEIGHT)
    inner.setParent(container)
    inner.move(0, OVERLAP + (CARD_HEIGHT - inner_h) // 2)
    return container


def make_arrow():
    arrow = QLabel()
    arrow.setPixmap(create_icon_pixmap(ICON_DIR / "arrow-narrow-right.svg", color_hex="#64748B", size=20))
    arrow.setFixedSize(20, 20)
    arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return center_in_band(arrow, 20, 20)
