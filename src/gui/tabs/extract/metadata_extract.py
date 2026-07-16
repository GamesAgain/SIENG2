from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from src.core.stego.metadata_handlers.mp3_handler import (
    APIC_TYPES, FRAME_INFO, MULTI_INSTANCE_FRAMES, MetadataMP3Handler,
)
from src.core.stego.metadata_handlers.png_handler import PNG_TEXT_KEYWORDS, MetadataPNGHandler
from src.gui.components.file_drop import FileDropWidget
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, create_icon_state, format_file_size
from src.gui.tabs.metadata_shared import FileInfoBar, get_file_display_info

ICON_DIR = Path(__file__).parent.parent.parent / "assets" / "svg"

TINT_CYCLE = ["blue", "purple", "green", "orange"]
COMPLEX_FIELDS = {"COMM", "USLT", "USER", "TXXX", "WXXX"}


def make_tag_badge(text: str, color: str = "neutral") -> QLabel:
    badge = QLabel(text)
    badge.setObjectName("fileInfoBadge")
    badge.setProperty("badgeColor", color)
    return badge


def make_readonly_input(value) -> QLineEdit:
    field = QLineEdit(str(value) if value is not None else "")
    field.setObjectName("formInput")
    field.setReadOnly(True)
    field.setCursorPosition(0)
    return field


def make_empty_state(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hintLabel")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


# ==========================================
# Read-only result widgets
# ==========================================

class ResultTextRow(QFrame):
    """1 แถวแสดงค่า text/url ธรรมดา - อ่านอย่างเดียว คัดลอกได้ แก้ไขไม่ได้"""

    def __init__(self, frame_id: str, value):
        super().__init__()
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
        layout.addLayout(header)

        layout.addWidget(make_readonly_input(value))


class ResultComplexRow(QFrame):
    """1 instance ของ frame ซับซ้อน (lang/desc/text หรือ desc/url) - อ่านอย่างเดียว"""

    def __init__(self, frame_id: str, value: dict):
        super().__init__()
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
        layout.addLayout(header)

        row = QHBoxLayout()
        row.setSpacing(6)
        if "lang" in value:
            lang_field = make_readonly_input(value.get("lang", ""))
            lang_field.setFixedWidth(60)
            row.addWidget(lang_field)
        if "desc" in value:
            desc_field = make_readonly_input(value.get("desc", ""))
            row.addWidget(desc_field, 1)
        main_key = "text" if "text" in value else "url"
        main_field = make_readonly_input(value.get(main_key, ""))
        row.addWidget(main_field, 2)
        layout.addLayout(row)


class ResultRawRow(QFrame):
    """frame ที่ไม่มีโครงสร้างชัดเจน (TIPL/POPM/UFID/SEEK/PRIV/GEOB ฯลฯ) - แสดงค่าดิบอย่างเดียว"""

    def __init__(self, frame_id: str, value):
        super().__init__()
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
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_col.addWidget(name_label)
        text_col.addWidget(value_label)
        layout.addLayout(text_col, 1)

    @staticmethod
    def _format_value(value) -> str:
        if isinstance(value, dict):
            parts = [f"{k}: {v}" for k, v in value.items() if k != "data"]
            return ", ".join(parts) if parts else "(binary data)"
        return str(value)


class ResultApicCard(QFrame):
    """การ์ดรูป APIC ที่ extract ได้ - อ่านอย่างเดียว มีแค่ปุ่ม Save Image (ไม่มี Replace/Delete แบบฝั่ง embed)"""

    MIME_EXTENSIONS = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/gif": ".gif",
    }

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

        save_btn = QPushButton("Save Image")
        save_btn.setObjectName("SecondaryBtn")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self.save_image)
        info_layout.addWidget(save_btn)

        layout.addWidget(info)

    @staticmethod
    def _render_preview(data):
        if not data:
            return None
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            return pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return None

    def save_image(self):
        """บันทึกรูปที่ extract ได้ลงไฟล์ - เขียน bytes ดิบตรงๆ ไม่ผ่านการ decode/re-encode ใดๆ
        เพื่อให้ไฟล์ที่ได้เหมือนต้นฉบับที่แนบมา 100%
        """
        data = self.apic_data.get("data") or b""
        if not data:
            QMessageBox.warning(self, "Notice", "This image has no data to save.")
            return

        mime = self.apic_data.get("mime", "image/png")
        ext = self.MIME_EXTENSIONS.get(mime, ".bin")
        desc = (self.apic_data.get("desc") or "").strip()
        type_name = APIC_TYPES.get(self.apic_data.get("type", 0), "Cover").lower().replace(" ", "_").replace("/", "-")
        default_name = f"{desc or type_name}{ext}"

        file_path, _ = QFileDialog.getSaveFileName(self, "Save Image", default_name, f"Image (*{ext})")
        if not file_path:
            return

        try:
            Path(file_path).write_bytes(data)
            QMessageBox.information(self, "Success", f"Image saved to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save image: {e}")


class AllFramesDialog(QDialog):
    """
    ป๊อปอัพแสดง "ทุก frame ที่มีอยู่จริงในไฟล์" (อ่านตรงจาก ID3 ไม่ผ่านสารบัญ PRIV:S2M)
    ไว้ตอบคำถามว่า "badge บอก N frames แต่ระบบบอก no hidden data ทำไม" - เพราะ badge นับ frame
    ทั้งหมดที่มีอยู่ในไฟล์ (title/artist/album ของจริงที่ไฟล์มีมาก่อน) ซึ่งอาจไม่เกี่ยวกับ SIENG2 เลย
    ส่วน "Extraction Result" หลักจะกรองเฉพาะที่อยู่ใน PRIV:S2M เท่านั้น
    """

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("All Frames In This File")
        self.resize(700, 600)

        layout = QVBoxLayout(self)

        note = QLabel(
            "These are every ID3 frame physically present in this file — including ones that have "
            "nothing to do with SIENG2 (e.g. tags a music player wrote). This is not filtered by the "
            "PRIV:S2M table of contents, unlike the main Extraction Result."
        )
        note.setObjectName("hintLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("fileListScroll")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(8)

        handler = MetadataMP3Handler()
        metadata = handler.read_metadata(file_path)

        row_count = 0
        apic_items = []

        for frame_id, value in metadata.items():
            if frame_id == "APIC":
                apic_items = value if isinstance(value, list) else [value]
                continue

            values = value if (frame_id in MULTI_INSTANCE_FRAMES and isinstance(value, list)) else [value]
            for v in values:
                # PRIV:S2M คือสารบัญของ SIENG2 เอง - โชว์แบบอธิบายให้เข้าใจแทนการโชว์ ciphertext ดิบๆ
                if frame_id == "PRIV" and isinstance(v, dict) and v.get("owner") == "S2M":
                    row = ResultRawRow("PRIV", {"note": "This is SIENG2's own hidden-data marker (encrypted table of contents), not a normal metadata tag"})
                elif frame_id in COMPLEX_FIELDS and isinstance(v, dict):
                    row = ResultComplexRow(frame_id, v)
                elif isinstance(v, (dict, list)):
                    row = ResultRawRow(frame_id, v)
                else:
                    row = ResultTextRow(frame_id, v)
                content_layout.addWidget(row)
                row_count += 1

        if apic_items:
            images_title = QLabel(f"Attached Pictures ({len(apic_items)})")
            images_title.setObjectName("cardTitle")
            content_layout.addWidget(images_title)

            images_grid = QGridLayout()
            images_grid.setSpacing(12)
            for i, apic_data in enumerate(apic_items):
                tint = TINT_CYCLE[i % len(TINT_CYCLE)]
                card = ResultApicCard(apic_data, tint)
                row, col = divmod(i, 2)
                images_grid.addWidget(card, row, col)
            content_layout.addLayout(images_grid)

        if row_count == 0 and not apic_items:
            content_layout.addWidget(make_empty_state("This file has no ID3 tag at all"))

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("SecondaryBtn")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


# ==========================================
# MP3 read-only viewer (extract-side counterpart of MP3MetadataEditor)
# ==========================================

class MP3MetadataViewer(QFrame):
    def __init__(self):
        super().__init__()
        self.handler = MetadataMP3Handler()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("techTabs")
        self.tabs.setIconSize(QSize(16, 16))

        self.text_card, self.text_rows_layout, self.text_empty_label = self._build_text_card()
        self.images_card, self.images_grid, self.images_empty_label = self._build_images_card()

        text_scroll = QScrollArea()
        text_scroll.setWidgetResizable(True)
        text_scroll.setObjectName("fileListScroll")
        text_scroll.setWidget(self.text_card)

        images_scroll = QScrollArea()
        images_scroll.setWidgetResizable(True)
        images_scroll.setObjectName("fileListScroll")
        images_scroll.setWidget(self.images_card)

        text_icon = create_icon_state(str(ICON_DIR / "text-size.svg"))
        images_icon = create_icon_state(str(ICON_DIR / "photo.svg"))
        self.tabs.addTab(text_scroll, text_icon, "Text Frames")
        self.tabs.addTab(images_scroll, images_icon, "Attached Pictures")

        layout.addWidget(self.tabs)

    def _build_text_card(self):
        # โครงสร้างเดียวกับ MP3TextFramesTab ฝั่ง embed เป๊ะๆ: container เดียว margin (0,12,0,0)
        # คุม card ตรงๆ ไม่มี wrapper ซ้อนเพิ่ม ไม่งั้น QScrollArea จะยืดจนเกิดช่องว่างโล่งด้านบน
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 12, 0, 0)
        main_layout.setSpacing(16)

        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        card_layout = QVBoxLayout(card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(ICON_DIR / "tags.svg", size=16))
        title_label = QLabel("Extracted Frames")
        title_label.setObjectName("cardTitle")
        hint = QLabel("Read-only")
        hint.setObjectName("hintLabel")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(hint)
        card_layout.addWidget(title_container)

        rows_layout = QVBoxLayout()
        rows_layout.setSpacing(8)
        card_layout.addLayout(rows_layout)

        empty_label = make_empty_state("No SIENG2 hidden data found in this file")
        card_layout.addWidget(empty_label)

        main_layout.addWidget(card)
        main_layout.addStretch()
        return container, rows_layout, empty_label

    def _build_images_card(self):
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 12, 0, 0)
        main_layout.setSpacing(16)

        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        card_layout = QVBoxLayout(card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(ICON_DIR / "photo.svg", size=16))
        title_label = QLabel("Attached Pictures (APIC)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        card_layout.addWidget(title_container)

        grid = QGridLayout()
        grid.setSpacing(12)
        card_layout.addLayout(grid)

        empty_label = make_empty_state("No SIENG2 hidden images found in this file")
        card_layout.addWidget(empty_label)

        main_layout.addWidget(card)
        main_layout.addStretch()
        return container, grid, empty_label

    def load_file(self, file_path: str):
        extracted = self.handler.extract_metadata(file_path)
        self._render_result(extracted)

    def _render_result(self, extracted: dict):
        # เคลียร์ผลลัพธ์เก่าก่อนเสมอ กันข้อมูลไฟล์ก่อนหน้าค้าง (บทเรียนจาก editor ฝั่ง embed)
        while self.text_rows_layout.count():
            item = self.text_rows_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.deleteLater()

        while self.images_grid.count():
            item = self.images_grid.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.deleteLater()

        text_count = 0
        apic_items = []

        for frame_id, value in extracted.items():
            if frame_id == "APIC":
                apic_items = value if isinstance(value, list) else [value]
                continue

            values = value if (frame_id in MULTI_INSTANCE_FRAMES and isinstance(value, list)) else [value]
            for v in values:
                if frame_id in COMPLEX_FIELDS and isinstance(v, dict):
                    row = ResultComplexRow(frame_id, v)
                elif isinstance(v, (dict, list)):
                    row = ResultRawRow(frame_id, v)
                else:
                    row = ResultTextRow(frame_id, v)
                self.text_rows_layout.addWidget(row)
                text_count += 1

        for i, apic_data in enumerate(apic_items):
            tint = TINT_CYCLE[i % len(TINT_CYCLE)]
            card = ResultApicCard(apic_data, tint)
            row, col = divmod(i, 2)
            self.images_grid.addWidget(card, row, col)

        self.text_empty_label.setVisible(text_count == 0)
        self.images_empty_label.setVisible(len(apic_items) == 0)

        self.tabs.setTabText(0, f"Text Frames  [{text_count}]")
        self.tabs.setTabText(1, f"Attached Pictures [{len(apic_items)}]")


# ==========================================
# PNG read-only widgets
# ==========================================

class PNGResultRow(QFrame):
    """1 แถวแสดง keyword+value ของ PNG ที่ extract ได้ - อ่านอย่างเดียว"""

    def __init__(self, keyword: str, value: str):
        super().__init__()
        name = PNG_TEXT_KEYWORDS.get(keyword, (keyword, ""))[0]

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

        layout.addWidget(make_readonly_input(value))


class PNGAllChunksDialog(QDialog):
    """
    ป๊อปอัพแสดง "ทุก text chunk (iTXt/tEXt/zTXt) ที่มีอยู่จริงในไฟล์" - อ่านตรง ไม่ผ่านสารบัญ stWo
    ตอบคำถามเดียวกับฝั่ง MP3: badge บอก N text chunks แต่ระบบบอก no hidden data เพราะ badge นับ
    text chunk ทั้งหมด (รวมที่โปรแกรมอื่นเขียนไว้) ส่วน Extraction Result กรองเฉพาะที่อยู่ใน stWo
    """

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("All Text Chunks In This File")
        self.resize(700, 600)

        layout = QVBoxLayout(self)

        note = QLabel(
            "These are every text chunk (iTXt/tEXt/zTXt) physically present in this file — including "
            "ones that have nothing to do with SIENG2 (e.g. keywords another editor wrote). This is not "
            "filtered by the stWo table of contents, unlike the main Extraction Result."
        )
        note.setObjectName("hintLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("fileListScroll")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(8)

        metadata = MetadataPNGHandler().read_itxt_chunk(file_path)
        for keyword, value in metadata.items():
            content_layout.addWidget(PNGResultRow(keyword, value))

        if not metadata:
            content_layout.addWidget(make_empty_state("This file has no text metadata chunks"))

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("SecondaryBtn")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


# ==========================================
# PNG read-only viewer (extract-side counterpart of PNGMetadataEditor)
# ==========================================

class PNGMetadataViewer(QFrame):
    def __init__(self):
        super().__init__()
        self.handler = MetadataPNGHandler()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        # โครงเดียวกับ PNG editor / MP3 viewer: container เดียว margin (0,12,0,0) คุม card ตรงๆ
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 12, 0, 0)
        main_layout.setSpacing(16)

        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        card_layout = QVBoxLayout(card)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(ICON_DIR / "tags.svg", size=16))
        self.title_label = QLabel("Extracted Metadata")
        self.title_label.setObjectName("cardTitle")
        hint = QLabel("Read-only — decoded from the stWo table of contents")
        hint.setObjectName("hintLabel")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        title_layout.addWidget(hint)
        card_layout.addWidget(title_container)

        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(8)
        card_layout.addLayout(self.rows_layout)

        self.empty_label = make_empty_state("No SIENG2 hidden data found in this file")
        card_layout.addWidget(self.empty_label)

        main_layout.addWidget(card)
        main_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("fileListScroll")
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def load_file(self, file_path: str):
        extracted = self.handler.extract_metadata(file_path)
        self._render_result(extracted)

    def _render_result(self, extracted: dict):
        # เคลียร์ผลลัพธ์เก่าก่อนเสมอ กันข้อมูลไฟล์ก่อนหน้าค้าง
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.deleteLater()

        for keyword, value in extracted.items():
            self.rows_layout.addWidget(PNGResultRow(keyword, value))

        self.empty_label.setVisible(len(extracted) == 0)
        self.title_label.setText(f"Extracted Metadata  [{len(extracted)}]")


# ==========================================
# Main Tab
# ==========================================

class MetadataExtractTab(QFrame):
    def __init__(self):
        super().__init__()

        self.stego_file = None

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 11, 4, 4)

        self.stego_file_stack = QStackedWidget()
        stego_dropfile_card = self.build_stego_file_card()
        stego_file_selected_card = self.build_stego_file_selected_card()

        self.stego_file_stack.addWidget(stego_dropfile_card)
        self.stego_file_stack.addWidget(stego_file_selected_card)
        main_layout.addWidget(self.stego_file_stack)

    def build_stego_file_card(self):
        card_frame = QFrame()
        card_frame.setObjectName("card")
        add_shadow_effect(card_frame)

        main_layout = QVBoxLayout(card_frame)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)

        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(ICON_DIR / "photo-video.svg", size=16))
        title_label = QLabel("Stego File (PNG, MP3)")
        title_label.setObjectName("cardTitle")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.drop_zone = FileDropWidget("Drop PNG, MP3 files here or click to browse", "Supports PNG, MP3 format only", allowed_extensions=[".png", ".mp3"])
        self.drop_zone.file_selected.connect(self.on_stego_file_selected)

        main_layout.addWidget(title_container, 0)
        main_layout.addWidget(self.drop_zone, 1)

        return card_frame

    def build_stego_file_selected_card(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.file_info_bar = FileInfoBar()
        self.file_info_bar.change_file_requested.connect(self.on_change_file_clicked)
        self.view_frames_btn = self.file_info_bar.add_extra_button("View Frames")
        self.view_frames_btn.clicked.connect(self.on_view_frames_clicked)
        layout.addWidget(self.file_info_bar)

        # MP3: viewer อ่านอย่างเดียว (Text Frames / Images tab)
        self.mp3_viewer = MP3MetadataViewer()
        self.mp3_viewer.hide()
        layout.addWidget(self.mp3_viewer)

        # PNG: viewer อ่านอย่างเดียว (iTXt text chunks จากสารบัญ stWo)
        self.png_viewer = PNGMetadataViewer()
        self.png_viewer.hide()
        layout.addWidget(self.png_viewer)

        return container

    # --- Event Handler ---
    def on_stego_file_selected(self, file_path: str):
        self.stego_file = file_path
        info = get_file_display_info(file_path)
        self.file_info_bar.update_info(info)

        is_mp3 = Path(file_path).suffix.lower() == ".mp3"
        self.mp3_viewer.setVisible(is_mp3)
        self.png_viewer.setVisible(not is_mp3)
        # ปุ่มดูข้อมูลทั้งหมด: MP3 = "View Frames", PNG = "View Chunks"
        self.view_frames_btn.setText("View Frames" if is_mp3 else "View Chunks")
        if is_mp3:
            self.mp3_viewer.load_file(file_path)
        else:
            self.png_viewer.load_file(file_path)

        self.stego_file_stack.setCurrentIndex(1)

    def on_change_file_clicked(self):
        self.drop_zone.clear_file()
        self.stego_file = None
        self.stego_file_stack.setCurrentIndex(0)

    def on_view_frames_clicked(self):
        if not self.stego_file:
            return

        if Path(self.stego_file).suffix.lower() == ".mp3":
            AllFramesDialog(self.stego_file, parent=self).exec()
        else:
            PNGAllChunksDialog(self.stego_file, parent=self).exec()
