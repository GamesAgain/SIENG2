import os
import tempfile
from pathlib import Path

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QStackedWidget, QVBoxLayout,
)

from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, format_file_size

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "svg"


class PayloadResultViewer(QFrame):
    """'Extraction Result' card shared by LSB++'s and Locomotive's Standalone extract
    tabs (and reusable later by the Configurable Pipeline's per-step result view) —
    one widget only needs to be built once per technique instead of duplicated per tab.

    Shows EITHER decoded text (with Copy / Export .txt) OR a recovered binary file
    (with Open / Save As), switched via show_text()/show_file(). LSB++ only ever
    calls show_text(); Locomotive picks one or the other depending on whether its
    recovered payload decodes as UTF-8."""

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        add_shadow_effect(self)
        self._file_data: bytes | None = None
        self._file_name: str = ""
        self._temp_path: Path | None = None

        layout = QVBoxLayout(self)

        title_container = QFrame()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        title_icon = QLabel()
        title_icon.setPixmap(create_icon_pixmap(ICON_DIR / "report-search.svg", size=16, color_hex="#cfcfcf"))
        title_label = QLabel("Extraction Result")
        title_label.setObjectName("cardTitle")
        title_label.setStyleSheet("font-weight: bold; color: #cfcfcf;")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addWidget(title_container)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_text_page())
        self.stack.addWidget(self._build_file_page())
        layout.addWidget(self.stack)

    # ---------------------------------------------------------------- text page
    def _build_text_page(self):
        page = QFrame()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(8)

        self.text_area = QPlainTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.text_area.setObjectName("payloadTextArea")
        self.text_area.setPlaceholderText("Not text extraction available")
        pl.addWidget(self.text_area)

        actions = QHBoxLayout()
        actions.addStretch()
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("SecondaryBtn")
        self.copy_btn.setProperty("textColor", "white")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._on_copy)
        self.export_btn = QPushButton(" Export .txt")
        self.export_btn.setObjectName("SecondaryBtn")
        self.export_btn.setProperty("textColor", "white")
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "file-export.svg", size=14, color_hex="#FFFFFF")))
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._on_export)
        actions.addWidget(self.copy_btn)
        actions.addWidget(self.export_btn)
        pl.addLayout(actions)

        return page

    # ---------------------------------------------------------------- file page
    def _build_file_page(self):
        page = QFrame()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(8)

        card = QFrame()
        card.setObjectName("fileInfoCard")
        cl = QHBoxLayout(card)
        cl.setContentsMargins(12, 12, 12, 12)
        cl.setSpacing(10)

        icon = QLabel()
        icon.setPixmap(create_icon_pixmap(ICON_DIR / "file.svg", size=22, color_hex="#A78BFA"))
        cl.addWidget(icon)

        info = QVBoxLayout()
        info.setSpacing(2)
        self.file_name_label = QLabel("")
        self.file_name_label.setObjectName("fileInfoName")
        self.file_name_label.setWordWrap(True)
        self.file_size_label = QLabel("")
        self.file_size_label.setObjectName("fileInfoDetail")
        info.addWidget(self.file_name_label)
        info.addWidget(self.file_size_label)
        cl.addLayout(info, 1)
        pl.addWidget(card)

        actions = QHBoxLayout()
        actions.addStretch()
        self.open_btn = QPushButton(" Open")
        self.open_btn.setObjectName("SecondaryBtn")
        self.open_btn.setProperty("textColor", "white")
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "file-search.svg", size=14, color_hex="#FFFFFF")))
        self.open_btn.clicked.connect(self._on_open)
        self.save_btn = QPushButton(" Save As...")
        self.save_btn.setObjectName("SecondaryBtn")
        self.save_btn.setProperty("textColor", "white")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "file-export.svg", size=14, color_hex="#FFFFFF")))
        self.save_btn.clicked.connect(self._on_save_as)
        actions.addWidget(self.open_btn)
        actions.addWidget(self.save_btn)
        pl.addLayout(actions)
        pl.addStretch()

        return page

    # ---------------------------------------------------------------- public API
    def show_text(self, text: str):
        self.text_area.setPlainText(text)
        self.copy_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        self.stack.setCurrentIndex(0)

    def show_file(self, data: bytes, suggested_name: str):
        self._file_data = data
        self._file_name = suggested_name or "extracted.bin"
        self._temp_path = None
        self.file_name_label.setText(self._file_name)
        self.file_size_label.setText(format_file_size(len(data)))
        self.stack.setCurrentIndex(1)

    def show_result(self, data: bytes, filename: str):
        """สำหรับ payload ของ Locomotive ที่ 'มีชื่อไฟล์จริงติดมา' — ตัดสิน text-vs-file จาก
        นามสกุลไฟล์ ไม่ใช่จาก decode UTF-8 ได้หรือไม่ (ไฟล์จริงอย่าง .pdf/.png/.docx ต้องเซฟด้วย
        นามสกุลเดิมเสมอ ถึง bytes จะ decode เป็นข้อความได้ก็ตาม เช่น PDF ข้อความล้วน) — เฉพาะไฟล์
        .txt (ข้อความที่ผู้ส่งฝังตรง ๆ) ถึงจะโชว์เป็น text preview (Copy/Export .txt)"""
        if filename.lower().endswith(".txt"):
            self.show_text(data.decode("utf-8", errors="replace"))
        else:
            self.show_file(data, filename)

    def clear(self):
        self.text_area.setPlainText("")
        self.copy_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self._file_data = None
        self._file_name = ""
        self._temp_path = None
        self.stack.setCurrentIndex(0)

    # ---------------------------------------------------------------- handlers
    def _on_copy(self):
        QApplication.clipboard().setText(self.text_area.toPlainText())

    def _on_export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Text", "extracted.txt", "Text files (*.txt);;All files (*.*)")
        if not path:
            return
        try:
            Path(path).write_text(self.text_area.toPlainText(), encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export text:\n{e}")

    def _on_open(self):
        if not self._file_data:
            return
        if self._temp_path is None:
            suffix = Path(self._file_name).suffix or ".bin"
            fd, tmp = tempfile.mkstemp(suffix=suffix, prefix="sieng2_extract_")
            with os.fdopen(fd, "wb") as f:
                f.write(self._file_data)
            self._temp_path = Path(tmp)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._temp_path)))

    def _on_save_as(self):
        if not self._file_data:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Extracted File", self._file_name, "All Files (*)")
        if not path:
            return
        try:
            Path(path).write_bytes(self._file_data)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save file:\n{e}")
