from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QTabWidget, QVBoxLayout, QWidget,
)

from src.core.stego.metadata_handlers.mp3_handler import (
    FRAME_INFO, STANDARD_FRAMES, APIC_TYPES, MULTI_INSTANCE_FRAMES, MetadataMP3Handler,
)
from src.gui.components.file_drop import FileDropWidget
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, create_icon_state, format_file_size

ICON_DIR = Path(__file__).parent.parent.parent / "assets" / "svg"

# frame ที่มีโครงสร้างซับซ้อนกว่า text/url ธรรมดา -> ต้องใช้ sub-field ตามนี้
COMPLEX_FRAME_SPECS = {
    "COMM": ["lang", "desc", "text"],
    "USLT": ["lang", "desc", "text"],
    "USER": ["lang", "text"],
    "TXXX": ["desc", "text"],
    "WXXX": ["desc", "url"],
}
MULTILINE_COMPLEX = {"USLT"}

TINT_CYCLE = ["blue", "purple", "green", "orange"]


def is_text_frame(frame_id: str) -> bool:
    return frame_id.startswith("T") and frame_id not in COMPLEX_FRAME_SPECS


def is_url_frame(frame_id: str) -> bool:
    return frame_id.startswith("W") and frame_id not in COMPLEX_FRAME_SPECS


def make_delete_button(size: int = 22) -> QPushButton:
    btn = QPushButton()
    btn.setObjectName("btnRemoveFile")
    btn.setFixedSize(size, size)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "x.svg", size=12, color_hex="#f43f5e")))
    return btn


def make_tag_badge(text: str, color: str = "neutral") -> QLabel:
    badge = QLabel(text)
    badge.setObjectName("fileInfoBadge")
    badge.setProperty("badgeColor", color)
    return badge


# ==========================================
# Text Frames - Field Widgets
# ==========================================

class TextFrameField(QFrame):
    """1 ช่องกรอกสำหรับ frame ประเภท Text (T*) หรือ URL (W*)"""
    removed = pyqtSignal(object)

    def __init__(self, frame_id: str, removable: bool = False):
        super().__init__()
        self.frame_id = frame_id
        name, _desc = FRAME_INFO.get(frame_id, (frame_id, ""))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)
        label = QLabel(name)
        label.setObjectName("formLabel")
        header.addWidget(label)
        header.addWidget(make_tag_badge(frame_id))
        header.addStretch()
        if removable:
            del_btn = make_delete_button()
            del_btn.clicked.connect(lambda: self.removed.emit(self))
            header.addWidget(del_btn)
        layout.addLayout(header)

        self.input = QLineEdit()
        self.input.setObjectName("formInput")
        layout.addWidget(self.input)

    def get_value(self) -> str:
        return self.input.text().strip()

    def set_value(self, value):
        self.input.setText("" if value is None else str(value))

    def is_empty(self) -> bool:
        return not self.get_value()


class ComplexInstanceRow(QFrame):
    """1 instance ของ frame ซับซ้อน (lang/desc/text หรือ desc/url ฯลฯ)"""
    removed = pyqtSignal(object)

    def __init__(self, fields: list, multiline: bool = False, show_delete: bool = True):
        super().__init__()
        self.fields = fields
        self.multiline = multiline
        self.inputs = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        if "lang" in fields:
            lang_input = QComboBox()
            lang_input.setEditable(True)
            lang_input.addItem("eng")
            lang_input.addItem("tha")
            lang_input.setCurrentIndex(-1)  # ว่างไว้ก่อน ให้ placeholder โชว์
            lang_input.lineEdit().setPlaceholderText("eng")
            lang_input.lineEdit().setMaxLength(3)
            lang_input.setFixedWidth(90)
            self.inputs["lang"] = lang_input
            layout.addWidget(lang_input)

        if "desc" in fields:
            desc_input = QLineEdit()
            desc_input.setObjectName("formInput")
            desc_input.setPlaceholderText("desc (optional)")
            self.inputs["desc"] = desc_input
            layout.addWidget(desc_input, 1)

        main_key = "text" if "text" in fields else "url"
        if self.multiline:
            main_input = QPlainTextEdit()
            main_input.setObjectName("payloadTextArea")
            main_input.setFixedHeight(70)
            main_input.setPlaceholderText("Lyrics...")
        else:
            main_input = QLineEdit()
            main_input.setObjectName("formInput")
            main_input.setPlaceholderText("https://..." if main_key == "url" else "Text...")
        self.inputs[main_key] = main_input
        layout.addWidget(main_input, 2)

        if show_delete:
            del_btn = make_delete_button(26)
            del_btn.clicked.connect(lambda: self.removed.emit(self))
            layout.addWidget(del_btn)

    def get_value(self) -> dict:
        result = {}
        for key, widget in self.inputs.items():
            if isinstance(widget, QPlainTextEdit):
                result[key] = widget.toPlainText().strip()
            elif isinstance(widget, QComboBox):
                result[key] = widget.currentText().strip()
            else:
                result[key] = widget.text().strip()
        return result

    def set_value(self, value: dict):
        if not value:
            return
        for key, widget in self.inputs.items():
            v = value.get(key, "")
            if isinstance(widget, QPlainTextEdit):
                widget.setPlainText(str(v))
            elif isinstance(widget, QComboBox):
                widget.setCurrentText(str(v))
            else:
                widget.setText(str(v))

    def is_empty(self) -> bool:
        main_key = "text" if "text" in self.inputs else "url"
        widget = self.inputs[main_key]
        text = widget.toPlainText() if isinstance(widget, QPlainTextEdit) else widget.text()
        return not text.strip()


class ComplexFrameField(QFrame):
    """Field สำหรับ Standard Frames ที่ซับซ้อน (ตอนนี้มีแค่ COMM) รองรับหลาย instance ในตัวเดียว"""
    removed = pyqtSignal(object)

    def __init__(self, frame_id: str, removable: bool = False):
        super().__init__()
        self.frame_id = frame_id
        self.fields = COMPLEX_FRAME_SPECS[frame_id]
        self.multiline = frame_id in MULTILINE_COMPLEX
        self.rows = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        name, _desc = FRAME_INFO.get(frame_id, (frame_id, ""))
        label = QLabel(name)
        label.setObjectName("formLabel")
        hint = QLabel("Can have multiple instances")
        hint.setObjectName("hintLabel")
        header.addWidget(label)
        header.addWidget(make_tag_badge(frame_id))
        header.addStretch()
        header.addWidget(hint)
        if removable:
            del_btn = make_delete_button()
            del_btn.clicked.connect(lambda: self.removed.emit(self))
            header.addWidget(del_btn)
        layout.addLayout(header)

        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(6)
        layout.addLayout(self.rows_layout)

        add_row_btn = QPushButton(f"+ Add {frame_id} instance")
        add_row_btn.setObjectName("LinkBtn")
        add_row_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_row_btn.clicked.connect(lambda: self.add_instance())
        layout.addWidget(add_row_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.add_instance()  # เริ่มด้วย 1 แถวว่างเสมอ

    def add_instance(self, value: dict = None):
        row = ComplexInstanceRow(self.fields, self.multiline)
        row.set_value(value)
        row.removed.connect(self.remove_instance)
        self.rows_layout.addWidget(row)
        self.rows.append(row)

    def remove_instance(self, row):
        if row in self.rows:
            self.rows.remove(row)
            row.setParent(None)
            row.deleteLater()
        if not self.rows:
            self.add_instance()

    def get_value(self) -> list:
        return [r.get_value() for r in self.rows if not r.is_empty()]

    def is_empty(self) -> bool:
        return len(self.get_value()) == 0


class OtherComplexInstanceField(QFrame):
    """1 instance ของ frame ซับซ้อนใน Other Frames (เช่น TXXX 1 รายการ) - รายการเดียวโดดๆ ไม่รวมกลุ่ม"""
    removed = pyqtSignal(object)

    def __init__(self, frame_id: str, value: dict = None):
        super().__init__()
        self.frame_id = frame_id
        self.setObjectName("fileItemRow")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        name, _desc = FRAME_INFO.get(frame_id, (frame_id, ""))
        name_label = QLabel(name)
        name_label.setObjectName("fileItemName")
        header.addWidget(name_label)
        header.addWidget(make_tag_badge(frame_id))
        header.addStretch()
        del_btn = make_delete_button()
        del_btn.clicked.connect(lambda: self.removed.emit(self))
        header.addWidget(del_btn)
        layout.addLayout(header)

        self.row = ComplexInstanceRow(COMPLEX_FRAME_SPECS[frame_id], frame_id in MULTILINE_COMPLEX, show_delete=False)
        self.row.set_value(value)
        layout.addWidget(self.row)

    def get_value(self) -> dict:
        return self.row.get_value()

    def is_empty(self) -> bool:
        return self.row.is_empty()


class RawFrameRow(QFrame):
    """frame ที่ไม่รองรับแก้ไขในหน้านี้ (TIPL/POPM/UFID/SEEK/PRIV/GEOB ฯลฯ) - แสดงค่าดิบอย่างเดียว ลบได้ ไม่แก้ไข"""
    removed = pyqtSignal(object)

    def __init__(self, frame_id: str, value):
        super().__init__()
        self.frame_id = frame_id
        self.value = value
        self.setObjectName("fileItemRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        layout.addWidget(make_tag_badge(frame_id))

        name, _desc = FRAME_INFO.get(frame_id, (frame_id, ""))
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name_label = QLabel(name)
        name_label.setObjectName("fileItemName")
        value_label = QLabel(self._format_value(value))
        value_label.setObjectName("fileInfoDetail")
        value_label.setWordWrap(True)
        text_col.addWidget(name_label)
        text_col.addWidget(value_label)
        layout.addLayout(text_col, 1)

        note = QLabel("read-only")
        note.setObjectName("hintLabel")
        layout.addWidget(note)

        del_btn = make_delete_button(26)
        del_btn.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(del_btn)

    @staticmethod
    def _format_value(value) -> str:
        if isinstance(value, dict):
            parts = [f"{k}: {v}" for k, v in value.items() if k != "data"]
            return ", ".join(parts) if parts else "(binary data)"
        return str(value)


# ==========================================
# Tab 1: Text Frames
# ==========================================

class MP3TextFramesTab(QWidget):
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.standard_fields = {}
        self.other_rows = []

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 12, 0, 0)
        self.main_layout.setSpacing(16)

        self.main_layout.addWidget(self._build_standard_frames_section())
        self.other_frames_card = self._build_other_frames_section()
        self.main_layout.addWidget(self.other_frames_card)
        self.main_layout.addWidget(self._build_add_frame_section())
        self.main_layout.addStretch()

    def _build_standard_frames_section(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(ICON_DIR / "tags.svg", size=16))
        title_label = QLabel("Standard Frames")
        title_label.setObjectName("cardTitle")
        hint = QLabel("Always shown")
        hint.setObjectName("hintLabel")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(hint)
        layout.addWidget(title_container)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(12)

        text_ids = [f for f in STANDARD_FRAMES if f not in COMPLEX_FRAME_SPECS]
        for i, frame_id in enumerate(text_ids):
            field = TextFrameField(frame_id, removable=False)
            self.standard_fields[frame_id] = field
            row, col = divmod(i, 2)
            grid.addWidget(field, row, col)
        layout.addLayout(grid)

        for frame_id in STANDARD_FRAMES:
            if frame_id in COMPLEX_FRAME_SPECS:
                complex_field = ComplexFrameField(frame_id, removable=False)
                self.standard_fields[frame_id] = complex_field
                layout.addWidget(complex_field)

        return card

    def _build_other_frames_section(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        outer = QVBoxLayout(card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(ICON_DIR / "file-dots.svg", size=16))
        title_label = QLabel("Other Frames")
        title_label.setObjectName("cardTitle")
        self.other_count_badge = make_tag_badge("0")
        hint = QLabel("Frames read from the file, or added manually")
        hint.setObjectName("hintLabel")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addWidget(self.other_count_badge)
        title_layout.addStretch()
        title_layout.addWidget(hint)
        outer.addWidget(title_container)

        self.other_frames_layout = QVBoxLayout()
        self.other_frames_layout.setSpacing(8)
        outer.addLayout(self.other_frames_layout)

        return card

    def _build_add_frame_section(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QHBoxLayout(card)
        layout.setSpacing(10)

        label = QLabel("Add Frame")
        label.setObjectName("formLabel")
        self.add_frame_combo = QComboBox()
        self._refresh_add_frame_options()

        add_btn = QPushButton("+ Add")
        add_btn.setObjectName("SecondaryBtn")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self.add_selected_frame)

        layout.addWidget(label)
        layout.addWidget(self.add_frame_combo, 1)
        layout.addWidget(add_btn)

        return card

    # --- Frame selection helpers ---
    def _addable_frame_ids(self) -> list:
        single_used = {row.frame_id for row in self.other_rows if row.frame_id not in MULTI_INSTANCE_FRAMES}
        ids = []
        for frame_id in FRAME_INFO:
            if frame_id == "APIC" or frame_id in STANDARD_FRAMES or frame_id in single_used:
                continue
            if is_text_frame(frame_id) or is_url_frame(frame_id) or frame_id in COMPLEX_FRAME_SPECS:
                ids.append(frame_id)
        return sorted(ids)

    def _refresh_add_frame_options(self):
        self.add_frame_combo.clear()
        for frame_id in self._addable_frame_ids():
            name, _desc = FRAME_INFO.get(frame_id, (frame_id, ""))
            self.add_frame_combo.addItem(f"{frame_id} — {name}", frame_id)

    def add_selected_frame(self):
        frame_id = self.add_frame_combo.currentData()
        if not frame_id:
            return
        self._add_other_row(frame_id, None)
        self.changed.emit()

    def _add_other_row(self, frame_id: str, value):
        if frame_id in COMPLEX_FRAME_SPECS:
            row = OtherComplexInstanceField(frame_id, value)
        elif is_text_frame(frame_id) or is_url_frame(frame_id):
            row = TextFrameField(frame_id, removable=True)
            row.set_value(value)
        else:
            row = RawFrameRow(frame_id, value)

        row.removed.connect(self.remove_other_row)
        self.other_rows.append(row)
        self.other_frames_layout.addWidget(row)
        self._refresh_add_frame_options()
        self._update_other_count()

    def remove_other_row(self, row):
        if row in self.other_rows:
            self.other_rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._refresh_add_frame_options()
        self._update_other_count()
        self.changed.emit()

    def _update_other_count(self):
        self.other_count_badge.setText(str(len(self.other_rows)))

    def clear_all(self):
        """ล้าง Standard Frames กลับเป็นค่าว่าง และลบ Other Frames ทั้งหมด (reset หน้า editor ให้โล่ง)"""
        for field in self.standard_fields.values():
            if isinstance(field, ComplexFrameField):
                for row in list(field.rows):
                    field.remove_instance(row)
            else:
                field.set_value("")

        for row in list(self.other_rows):
            self.remove_other_row(row)

    # --- Load / Save ---
    def load_existing(self, metadata: dict):
        # เคลียร์ค่าจากไฟล์เก่าก่อนเสมอ ไม่งั้น field ที่ไฟล์ใหม่ไม่มีจะค้างค่าไฟล์เก่าไว้
        # และ Other Frames จะสะสมของเก่า+ใหม่ปนกันแทนที่จะแทนที่
        self.clear_all()

        for frame_id, field in self.standard_fields.items():
            if frame_id not in metadata:
                continue
            if isinstance(field, ComplexFrameField):
                values = metadata[frame_id] if isinstance(metadata[frame_id], list) else [metadata[frame_id]]
                field.rows[0].set_value(values[0])
                for extra in values[1:]:
                    field.add_instance(extra)
            else:
                field.set_value(metadata[frame_id])

        for frame_id, value in metadata.items():
            if frame_id in self.standard_fields or frame_id == "APIC":
                continue
            values = value if (frame_id in MULTI_INSTANCE_FRAMES and isinstance(value, list)) else [value]
            for v in values:
                self._add_other_row(frame_id, v)

    def get_standard_data(self) -> dict:
        result = {}
        for frame_id, field in self.standard_fields.items():
            if not field.is_empty():
                result[frame_id] = field.get_value()
        return result

    def get_other_data(self) -> dict:
        result = {}
        for row in self.other_rows:
            if isinstance(row, RawFrameRow):
                value = row.value
            elif not row.is_empty():
                value = row.get_value()
            else:
                continue

            if row.frame_id in MULTI_INSTANCE_FRAMES:
                result.setdefault(row.frame_id, [])
                if isinstance(value, list):
                    result[row.frame_id].extend(value)
                else:
                    result[row.frame_id].append(value)
            else:
                result[row.frame_id] = value
        return result

    def total_count(self) -> int:
        std_count = sum(1 for f in self.standard_fields.values() if not f.is_empty())
        other_count = sum(1 for row in self.other_rows if isinstance(row, RawFrameRow) or not row.is_empty())
        return std_count + other_count


# ==========================================
# Tab 2: Attached Pictures (APIC)
# ==========================================

class ApicCard(QFrame):
    replace_requested = pyqtSignal(object)
    delete_requested = pyqtSignal(object)

    def __init__(self, apic_data: dict, tint: str):
        super().__init__()
        self.apic_data = apic_data
        self.setObjectName("apicCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        type_id = apic_data.get("type", 0)
        type_name = APIC_TYPES.get(type_id, "Other")

        preview = QFrame()
        preview.setObjectName("apicPreview")
        preview.setProperty("tintColor", tint)
        preview.setFixedHeight(120)
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(8, 8, 8, 8)

        top_row = QHBoxLayout()
        top_row.addWidget(make_tag_badge(f"Type {type_id} · {type_name}", tint))
        top_row.addStretch()
        preview_layout.addLayout(top_row)
        preview_layout.addStretch()

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = self._render_preview(apic_data.get("data"))
        if pixmap is not None:
            icon_label.setPixmap(pixmap)
        else:
            icon_label.setPixmap(create_icon_pixmap(ICON_DIR / "photo.svg", size=28))
        preview_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
        preview_layout.addStretch()

        layout.addWidget(preview)

        info = QFrame()
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(10, 8, 10, 10)
        info_layout.setSpacing(3)

        caption = QLabel(type_name)
        caption.setObjectName("fileInfoName")
        info_layout.addWidget(caption)

        size_bytes = len(apic_data.get("data") or b"")
        format_label = QLabel(f"{apic_data.get('mime', 'image')} · {format_file_size(size_bytes)}")
        format_label.setObjectName("fileInfoDetail")
        info_layout.addWidget(format_label)

        desc = (apic_data.get("desc") or "").strip()
        if desc:
            desc_label = QLabel(f'desc: "{desc}"')
            desc_label.setObjectName("fileInfoDetail")
            desc_label.setWordWrap(True)
            info_layout.addWidget(desc_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        replace_btn = QPushButton("Replace")
        replace_btn.setObjectName("SecondaryBtn")
        replace_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        replace_btn.clicked.connect(lambda: self.replace_requested.emit(self))

        delete_btn = QPushButton()
        delete_btn.setObjectName("btnRemoveFile")
        delete_btn.setFixedSize(30, 30)
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "trash.svg", size=14, color_hex="#f43f5e")))
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(self))

        btn_row.addWidget(replace_btn, 1)
        btn_row.addWidget(delete_btn)
        info_layout.addLayout(btn_row)

        layout.addWidget(info)

    @staticmethod
    def _render_preview(data):
        if not data:
            return None
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            return pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return None


class MP3ImagesTab(QWidget):
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.apic_list = []
        self._pending_image_bytes = None
        self._pending_image_mime = None

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 12, 0, 0)
        self.main_layout.setSpacing(12)

        self.cards_section = self._build_cards_section()
        self.main_layout.addWidget(self.cards_section)
        self.cards_section.hide()  # ซ่อนถ้ายังไม่มีรูป

        self.add_form = self._build_add_form()
        self.main_layout.addWidget(self.add_form)
        self.main_layout.addStretch()

    def _build_cards_section(self) -> QFrame:
        section = QFrame()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(ICON_DIR / "photo.svg", size=16))
        title = QLabel("Attached Pictures (APIC)")
        title.setObjectName("cardTitle")
        hint = QLabel("Can have multiple images, differentiated by type + desc")
        hint.setObjectName("hintLabel")
        self.add_image_top_btn = QPushButton("+ Add Image")
        self.add_image_top_btn.setObjectName("SecondaryBtn")
        self.add_image_top_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        header.addWidget(title_icon)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(hint)
        header.addWidget(self.add_image_top_btn)
        layout.addLayout(header)

        self.cards_grid = QGridLayout()
        self.cards_grid.setSpacing(12)
        layout.addLayout(self.cards_grid)

        return section

    def _build_add_form(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(ICON_DIR / "photo.svg", size=16))
        title_label = QLabel("Add New Image")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addWidget(title_container)

        form_row = QHBoxLayout()
        form_row.setSpacing(16)

        self.image_drop_zone = FileDropWidget("Drop image here", "JPEG · PNG", allowed_extensions=["jpg", "jpeg", "png"])
        self.image_drop_zone.file_selected.connect(self.on_image_file_selected)
        form_row.addWidget(self.image_drop_zone, 1)

        right_col = QVBoxLayout()
        right_col.setSpacing(8)

        type_label = QLabel("Picture Type")
        type_label.setObjectName("formLabel")
        self.type_combo = QComboBox()
        for type_id, type_name in APIC_TYPES.items():
            self.type_combo.addItem(f"{type_id} — {type_name}", type_id)
        self._reset_type_combo()
        right_col.addWidget(type_label)
        right_col.addWidget(self.type_combo)

        desc_label = QLabel("Description")
        desc_label.setObjectName("formLabel")
        self.desc_input = QLineEdit()
        self.desc_input.setObjectName("formInput")
        self.desc_input.setPlaceholderText("Image description (optional)")
        right_col.addWidget(desc_label)
        right_col.addWidget(self.desc_input)
        right_col.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reset_add_form)
        add_btn = QPushButton("+ Add Image")
        add_btn.setObjectName("EmbedBtn")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self.confirm_add_image)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(add_btn)
        right_col.addLayout(btn_row)

        form_row.addLayout(right_col, 1)
        layout.addLayout(form_row)

        return card

    def _reset_type_combo(self):
        idx = self.type_combo.findData(3)  # default: Front cover
        self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)

    # --- Events ---
    def on_image_file_selected(self, file_path: str):
        path_obj = Path(file_path)
        self._pending_image_bytes = path_obj.read_bytes()
        ext = path_obj.suffix.lower()
        self._pending_image_mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(ext, "image/jpeg")

    def confirm_add_image(self):
        if not self._pending_image_bytes:
            QMessageBox.warning(self, "Notice", "Please select an image first")
            return

        apic_data = {
            "mime": self._pending_image_mime,
            "type": self.type_combo.currentData(),
            "desc": self.desc_input.text().strip(),
            "data": self._pending_image_bytes,
        }
        self.apic_list.append(apic_data)
        self.rebuild_cards()
        self.reset_add_form()
        self.changed.emit()

    def reset_add_form(self):
        self.image_drop_zone.clear_file()
        self.desc_input.clear()
        self._reset_type_combo()
        self._pending_image_bytes = None
        self._pending_image_mime = None

    def rebuild_cards(self):
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            w = item.widget()
            if w:
                # ซ่อนทันที (synchronous) เพราะ deleteLater() รอรอบ event loop ถัดไป
                # ถ้าไม่ hide() ก่อน widget เก่าจะค้างเห็นทับกับการ์ดใหม่ชั่วขณะ
                w.hide()
                w.deleteLater()

        for i, apic_data in enumerate(self.apic_list):
            tint = TINT_CYCLE[i % len(TINT_CYCLE)]
            card = ApicCard(apic_data, tint)
            card.delete_requested.connect(self.delete_image)
            card.replace_requested.connect(self.replace_image)
            row, col = divmod(i, 2)
            self.cards_grid.addWidget(card, row, col)

        self.cards_section.setVisible(len(self.apic_list) > 0)

    def delete_image(self, card: ApicCard):
        if card.apic_data in self.apic_list:
            self.apic_list.remove(card.apic_data)
        self.rebuild_cards()
        self.changed.emit()

    def replace_image(self, card: ApicCard):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select new image", "", "Images (*.jpg *.jpeg *.png)")
        if not file_path:
            return
        path_obj = Path(file_path)
        ext = path_obj.suffix.lower()
        card.apic_data["data"] = path_obj.read_bytes()
        card.apic_data["mime"] = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(ext, "image/jpeg")
        self.rebuild_cards()
        self.changed.emit()

    def clear_all(self):
        """ลบรูป APIC ทั้งหมด (reset หน้า editor ให้โล่ง)"""
        self.apic_list = []
        self.rebuild_cards()

    # --- Load / Save ---
    def load_existing(self, apic_items: list):
        self.reset_add_form()  # เคลียร์ฟอร์ม "เพิ่มรูปใหม่" ที่อาจค้างจากไฟล์เก่า (รูปที่เลือกไว้แต่ยังไม่กด Add)
        self.apic_list = list(apic_items)
        self.rebuild_cards()

    def get_value(self) -> list:
        return list(self.apic_list)

    def count(self) -> int:
        return len(self.apic_list)


# ==========================================
# Top-level Editor
# ==========================================

class MP3MetadataEditor(QFrame):
    save_completed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.handler = MetadataMP3Handler()
        self.file_path = None
        self._clear_before_save = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("techTabs")
        self.tabs.setIconSize(QSize(16, 16))

        self.text_frames_tab = MP3TextFramesTab()
        self.images_tab = MP3ImagesTab()

        text_scroll = QScrollArea()
        text_scroll.setWidgetResizable(True)
        text_scroll.setObjectName("fileListScroll")
        text_scroll.setWidget(self.text_frames_tab)

        images_scroll = QScrollArea()
        images_scroll.setWidgetResizable(True)
        images_scroll.setObjectName("fileListScroll")
        images_scroll.setWidget(self.images_tab)
        self.images_tab.add_image_top_btn.clicked.connect(
            lambda: images_scroll.ensureWidgetVisible(self.images_tab.add_form)
        )

        self.text_frames_tab.changed.connect(self.update_status)
        self.images_tab.changed.connect(self.update_status)

        text_icon = create_icon_state(str(ICON_DIR / "text-size.svg"))
        images_icon = create_icon_state(str(ICON_DIR / "photo.svg"))
        self.tabs.addTab(text_scroll, text_icon, "Text Frames")
        self.tabs.addTab(images_scroll, images_icon, "Attached Pictures")
        layout.addWidget(self.tabs)

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

    def load_file(self, file_path: str):
        self.file_path = file_path
        self._clear_before_save = False
        metadata = self.handler.read_metadata(file_path)

        apic_list = metadata.get("APIC", [])
        if isinstance(apic_list, dict):
            apic_list = [apic_list]
        self.images_tab.load_existing(apic_list)

        text_metadata = {k: v for k, v in metadata.items() if k != "APIC"}

        # ถ้าไฟล์เคย embed มาก่อน จะมี PRIV:S2M (สารบัญภายในของแอปเอง) ติดมาด้วย
        # ต้องกรองออกก่อนโชว์ ไม่งั้นจะโผล่เป็น "Other Frame" ปกติทั้งที่เป็นแค่ bookkeeping
        if "PRIV" in text_metadata:
            real_priv = [p for p in text_metadata["PRIV"] if p.get("owner") != "S2M"]
            if real_priv:
                text_metadata["PRIV"] = real_priv
            else:
                del text_metadata["PRIV"]

        self.text_frames_tab.load_existing(text_metadata)

        self.update_status()

    def update_status(self):
        self.tabs.setTabText(0, f"Text Frames  [{self.text_frames_tab.total_count()}]")
        self.tabs.setTabText(1, f"Attached Pictures [{self.images_tab.count()}]")

    def clear_metadata(self):
        """ล้างทุก field/tag ที่แสดงอยู่ในหน้านี้ - เหมือน normalize ไฟล์ให้กลับเป็นผ้าขาวสะอาด
        พร้อมใส่ข้อมูลใหม่ (การ save ครั้งถัดไปจะลบ frame เดิมในไฟล์ทิ้งจริงๆ ก่อนเขียน data ใหม่)
        """
        reply = QMessageBox.question(
            self,
            "Clear Metadata",
            "This clears every field shown here. The next save will start from a completely blank tag "
            "(all existing frames removed first). Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.text_frames_tab.clear_all()
        self.images_tab.clear_all()
        self._clear_before_save = True
        self.update_status()

    def save_metadata(self):
        if not self.file_path:
            return

        data = {}
        data.update(self.text_frames_tab.get_standard_data())
        data.update(self.text_frames_tab.get_other_data())

        apic_items = self.images_tab.get_value()
        if apic_items:
            data["APIC"] = apic_items

        # ถ้าเพิ่งกด Clear มา ยอมให้ data ว่างได้ (ตั้งใจ save ไฟล์เปล่าจริงๆ)
        if not data and not self._clear_before_save:
            QMessageBox.warning(self, "Notice", "No data to save yet")
            return

        # เสนอชื่อไฟล์ปลายทางเป็น {ชื่อเดิม}_metadata.{นามสกุล} เสมอ - ไม่ทับ/เปลี่ยนชื่อไฟล์ต้นฉบับ
        src_path = Path(self.file_path)
        default_path = src_path.with_name(f"{src_path.stem}_metadata{src_path.suffix}")
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Metadata File",
            str(default_path),
            f"MP3 Files (*{src_path.suffix})"
        )
        if not save_path:
            return

        try:
            saved_path = self.handler.embed_metadata(
                self.file_path, data, save_path=save_path, clear_existing=self._clear_before_save
            )
            self._clear_before_save = False
            QMessageBox.information(self, "Success", f"Metadata saved successfully\nSaved to:\n{saved_path}")
            self.save_completed.emit(saved_path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Save failed: {e}")
