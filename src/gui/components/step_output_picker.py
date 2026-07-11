from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

STEP_COL_W = 64      # กว้างคอลัมน์ "STEP"
MODULE_COL_W = 120   # กว้างคอลัมน์ "MODULE"


class StepOutputRow(QFrame):
    """1 แถวของตาราง StepOutputPicker — [Step N] [Module] [Output] คลิกเลือกได้"""

    clicked = pyqtSignal()

    def __init__(self, step_no: int, module: str, output: str, accent: str, parent=None):
        super().__init__(parent)
        self.setObjectName("stepOutputRow")
        self.setProperty("accentColor", accent)
        self.setProperty("selected", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 7, 10, 7)
        row.setSpacing(8)

        step_lbl = QLabel(f"Step {step_no}")
        step_lbl.setObjectName("stepOutputCellStep")
        step_lbl.setFixedWidth(STEP_COL_W)

        module_lbl = QLabel(module)
        module_lbl.setObjectName("stepOutputCellModule")
        module_lbl.setProperty("accentColor", accent)
        module_lbl.setFixedWidth(MODULE_COL_W)

        output_lbl = QLabel(output)
        output_lbl.setObjectName("stepOutputCellOutput")

        row.addWidget(step_lbl)
        row.addWidget(module_lbl)
        row.addWidget(output_lbl, 1)

    def set_selected(self, selected: bool):
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class StepOutputPicker(QFrame):
    """ตารางเลือก output ของ step ก่อนหน้าแทนการอัปโหลดไฟล์เอง ("Linked from Step")

    max_selection=1   → เลือกได้ทีละ 1 รายการ (คลิกแถวใหม่ล้างแถวเก่า — LSB++/Metadata cover เดี่ยว)
    max_selection>1/None → เลือกได้หลายรายการพร้อมกัน (Locomotive cover/payload รับหลายไฟล์)

    candidates ถูกกรองมาแล้วจากภายนอก (backward-only, ยังไม่ถูกจอง, type ตรง) — widget นี้แค่แสดง"""

    selectionChanged = pyqtSignal(list)  # list ของ step-index (int) ที่เลือกอยู่

    def __init__(self, max_selection: int | None = 1, parent=None):
        super().__init__(parent)
        self.max_selection = max_selection
        self._rows: dict[int, StepOutputRow] = {}
        self._selected: list[int] = []

        self.setObjectName("stepOutputPicker")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)

        self._header = self._build_header()
        self._layout.addWidget(self._header)

        self._empty_label = QLabel("No compatible step output available to link yet.")
        self._empty_label.setObjectName("hintLabel")
        self._empty_label.setWordWrap(True)
        self._layout.addWidget(self._empty_label)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("stepOutputHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(8)
        for text, width in (("STEP", STEP_COL_W), ("MODULE", MODULE_COL_W), ("OUTPUT", None)):
            lbl = QLabel(text)
            lbl.setObjectName("stepOutputHeaderCell")
            if width:
                lbl.setFixedWidth(width)
                row.addWidget(lbl)
            else:
                row.addWidget(lbl, 1)
        return header

    def set_candidates(self, candidates: list[dict]):
        """candidates: [{"index", "step_no", "module", "output", "accent"}, ...]"""
        self._clear_rows()

        valid_indices = {c["index"] for c in candidates}
        self._selected = [i for i in self._selected if i in valid_indices]  # ตัด selection ที่หลุดจากลิสต์ใหม่

        self._header.setVisible(bool(candidates))
        self._empty_label.setVisible(not candidates)
        for c in candidates:
            row = StepOutputRow(c["step_no"], c["module"], c["output"], c["accent"])
            row.set_selected(c["index"] in self._selected)
            row.clicked.connect(lambda idx=c["index"]: self._on_row_clicked(idx))
            self._layout.addWidget(row)
            self._rows[c["index"]] = row

    def _clear_rows(self):
        for row in self._rows.values():
            row.setParent(None)
            row.deleteLater()
        self._rows = {}

    def _on_row_clicked(self, index: int):
        if index in self._selected:
            self._selected.remove(index)
        elif self.max_selection == 1:
            self._selected = [index]
        elif self.max_selection is None or len(self._selected) < self.max_selection:
            self._selected.append(index)
        else:
            return  # เต็มโควตาที่เลือกได้แล้ว

        for idx, row in self._rows.items():
            row.set_selected(idx in self._selected)
        self.selectionChanged.emit(list(self._selected))

    def selected_indices(self) -> list[int]:
        return list(self._selected)

    def clear_selection(self):
        self._selected = []
        for row in self._rows.values():
            row.set_selected(False)
