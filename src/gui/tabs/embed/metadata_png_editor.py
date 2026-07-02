from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from src.core.stego.metadata_handlers.png_handler import (
    MAX_KEYWORD_LENGTH, PNG_TEXT_KEYWORDS, STANDARD_KEYWORDS, MetadataPNGHandler,
)
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap

ICON_DIR = Path(__file__).parent.parent.parent / "assets" / "svg"

# keyword ที่แนะนำใน dropdown "Add" (registered keyword ที่ไม่ได้อยู่ในกลุ่ม standard always-shown)
SUGGESTED_KEYWORDS = [k for k in PNG_TEXT_KEYWORDS if k not in STANDARD_KEYWORDS]


def make_tag_badge(text: str, color: str = "neutral") -> QLabel:
    badge = QLabel(text)
    badge.setObjectName("fileInfoBadge")
    badge.setProperty("badgeColor", color)
    return badge


def make_delete_button(size: int = 26) -> QPushButton:
    btn = QPushButton()
    btn.setObjectName("btnRemoveFile")
    btn.setFixedSize(size, size)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "x.svg", size=12, color_hex="#f43f5e")))
    return btn


# ==========================================
# Field widgets
# ==========================================

class PNGStandardField(QFrame):
    """1 field ของ standard keyword (Title/Author/...) - keyword คงที่ แก้ได้แค่ value, แสดงเสมอ"""

    def __init__(self, keyword: str):
        super().__init__()
        self.keyword = keyword
        name, _desc = PNG_TEXT_KEYWORDS.get(keyword, (keyword, ""))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)
        label = QLabel(name)
        label.setObjectName("formLabel")
        header.addWidget(label)
        header.addWidget(make_tag_badge(keyword))
        header.addStretch()
        layout.addLayout(header)

        self.value_input = QLineEdit()
        self.value_input.setObjectName("formInput")
        layout.addWidget(self.value_input)

    def get_value(self) -> str:
        return self.value_input.text().strip()

    def set_value(self, value):
        self.value_input.setText("" if value is None else str(value))

    def is_empty(self) -> bool:
        return not self.get_value()


class PNGCustomRow(QFrame):
    """1 row ของ custom metadata - keyword + value แก้ได้ทั้งคู่, ลบได้"""
    removed = pyqtSignal(object)

    def __init__(self, keyword: str = "", value: str = ""):
        super().__init__()
        self.setObjectName("fileItemRow")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        title = QLabel("Custom Keyword")
        title.setObjectName("fileItemName")
        header.addWidget(title)
        header.addStretch()
        del_btn = make_delete_button()
        del_btn.clicked.connect(lambda: self.removed.emit(self))
        header.addWidget(del_btn)
        layout.addLayout(header)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.keyword_input = QLineEdit(keyword)
        self.keyword_input.setObjectName("formInput")
        self.keyword_input.setPlaceholderText("keyword")
        self.keyword_input.setMaxLength(MAX_KEYWORD_LENGTH)
        self.keyword_input.setFixedWidth(220)
        self.value_input = QLineEdit(value)
        self.value_input.setObjectName("formInput")
        self.value_input.setPlaceholderText("value")
        row.addWidget(self.keyword_input)
        row.addWidget(self.value_input, 1)
        layout.addLayout(row)

    def get_keyword(self) -> str:
        return self.keyword_input.text().strip()

    def get_value(self) -> str:
        return self.value_input.text().strip()

    def is_empty(self) -> bool:
        return not self.get_keyword()


# ==========================================
# Main editor
# ==========================================

class PNGMetadataEditor(QFrame):
    save_completed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.handler = MetadataPNGHandler()
        self.file_path = None
        self._clear_before_save = False
        self.standard_fields = {}
        self.custom_rows = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        # เนื้อหาทั้งหมดอยู่ใน scroll area เดียว (PNG ไม่มี tab แยกเหมือน MP3 เพราะไม่มี APIC images)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(16)

        self.content_layout.addWidget(self._build_standard_card())
        self.other_card = self._build_other_card()
        self.content_layout.addWidget(self.other_card)
        self.content_layout.addWidget(self._build_add_card())
        self.content_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("fileListScroll")
        scroll.setWidget(content)
        layout.addWidget(scroll)

        # แถวปุ่มล่างสุด (Clear / Save) - เหมือน MP3 editor
        status_row = QHBoxLayout()
        status_row.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("SecondaryBtn")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self.clear_metadata)
        status_row.addWidget(clear_btn)

        save_btn = QPushButton("Save metadata")
        save_btn.setObjectName("EmbedBtn")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self.save_metadata)
        status_row.addWidget(save_btn)

        layout.addLayout(status_row)

    # --- Builders ---
    def _build_standard_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(ICON_DIR / "tags.svg", size=16))
        title_label = QLabel("Standard Metadata")
        title_label.setObjectName("cardTitle")
        hint = QLabel("Always shown — keys File Explorer reads")
        hint.setObjectName("hintLabel")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(hint)
        layout.addWidget(title_container)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(12)
        for i, keyword in enumerate(STANDARD_KEYWORDS):
            field = PNGStandardField(keyword)
            self.standard_fields[keyword] = field
            row, col = divmod(i, 2)
            grid.addWidget(field, row, col)
        layout.addLayout(grid)

        return card

    def _build_other_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        outer = QVBoxLayout(card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(ICON_DIR / "file-dots.svg", size=16))
        title_label = QLabel("Custom Metadata")
        title_label.setObjectName("cardTitle")
        self.custom_count_badge = make_tag_badge("0")
        hint = QLabel("Keys read from the file, or added manually")
        hint.setObjectName("hintLabel")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addWidget(self.custom_count_badge)
        title_layout.addStretch()
        title_layout.addWidget(hint)
        outer.addWidget(title_container)

        self.custom_rows_layout = QVBoxLayout()
        self.custom_rows_layout.setSpacing(8)
        outer.addLayout(self.custom_rows_layout)

        return card

    def _build_add_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QHBoxLayout(card)
        layout.setSpacing(10)

        label = QLabel("Add Metadata")
        label.setObjectName("formLabel")

        self.add_keyword_combo = QComboBox()
        self.add_keyword_combo.setEditable(True)
        self.add_keyword_combo.addItems(SUGGESTED_KEYWORDS)
        self.add_keyword_combo.setCurrentIndex(-1)
        self.add_keyword_combo.lineEdit().setPlaceholderText("keyword (pick one or type a custom keyword)")
        self.add_keyword_combo.lineEdit().setMaxLength(MAX_KEYWORD_LENGTH)

        add_btn = QPushButton("+ Add")
        add_btn.setObjectName("SecondaryBtn")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self.add_custom_from_combo)

        layout.addWidget(label)
        layout.addWidget(self.add_keyword_combo, 1)
        layout.addWidget(add_btn)

        return card

    # --- Custom row management ---
    def add_custom_from_combo(self):
        keyword = self.add_keyword_combo.currentText().strip()
        self._add_custom_row(keyword, "")
        self.add_keyword_combo.setCurrentIndex(-1)
        self.add_keyword_combo.clearEditText()

    def _add_custom_row(self, keyword: str, value: str):
        row = PNGCustomRow(keyword, value)
        row.removed.connect(self.remove_custom_row)
        self.custom_rows.append(row)
        self.custom_rows_layout.addWidget(row)
        self._update_custom_count()

    def remove_custom_row(self, row):
        if row in self.custom_rows:
            self.custom_rows.remove(row)
        row.hide()  # deleteLater() รอรอบ event loop ถัดไป ต้อง hide() ก่อนกันค้างเห็นซ้อนกัน
        row.deleteLater()
        self._update_custom_count()

    def _update_custom_count(self):
        self.custom_count_badge.setText(str(len(self.custom_rows)))

    def clear_all(self):
        """ล้างทุก field/row ให้ว่าง (reset editor)"""
        for field in self.standard_fields.values():
            field.set_value("")
        for row in list(self.custom_rows):
            self.remove_custom_row(row)

    # --- Load / Save ---
    def load_file(self, file_path: str):
        self.file_path = file_path
        self._clear_before_save = False
        self.clear_all()  # เคลียร์ค่าจากไฟล์ก่อนหน้าเสมอ กันค้างข้ามไฟล์

        metadata = self.handler.read_itxt_chunk(file_path)  # dict {keyword: value} ทั้งหมดในไฟล์
        for keyword, value in metadata.items():
            if keyword in self.standard_fields:
                self.standard_fields[keyword].set_value(value)
            else:
                self._add_custom_row(keyword, value)

    def collect_data(self) -> dict:
        data = {}
        # standard: keyword คงที่, ใส่เฉพาะที่มีค่า
        for keyword, field in self.standard_fields.items():
            if not field.is_empty():
                data[keyword] = field.get_value()
        # custom: keyword เป็นตัวกำหนด (ข้ามที่ keyword ว่าง), keyword ซ้ำ = ตัวหลังทับ
        for row in self.custom_rows:
            if not row.is_empty():
                data[row.get_keyword()] = row.get_value()
        return data

    def clear_metadata(self):
        reply = QMessageBox.question(
            self,
            "Clear Metadata",
            "This clears every field shown here. The next save will write a PNG with no text metadata "
            "(all existing keys removed). Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.clear_all()
        self._clear_before_save = True

    def save_metadata(self):
        if not self.file_path:
            return

        data = self.collect_data()

        if not data and not self._clear_before_save:
            QMessageBox.warning(self, "Notice", "No metadata to save yet")
            return

        src_path = Path(self.file_path)
        default_path = src_path.with_name(f"{src_path.stem}_metadata{src_path.suffix}")
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Metadata File", str(default_path), "PNG Files (*.png)"
        )
        if not save_path:
            return

        try:
            # merge_existing=False: editor โหลด metadata ครบแล้ว เขียน state เป๊ะๆ (ลบ key ได้จริง)
            saved_path = self.handler.embed_metadata(self.file_path, data, save_path=save_path, merge_existing=False)
            self._clear_before_save = False
            QMessageBox.information(self, "Success", f"Metadata saved successfully\nSaved to:\n{saved_path}")
            self.save_completed.emit(saved_path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Save failed: {e}")
