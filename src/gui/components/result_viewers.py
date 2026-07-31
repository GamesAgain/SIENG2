import os
import tempfile
from pathlib import Path

from PyQt6.QtCore import QUrl, Qt, QFileInfo
from PyQt6.QtGui import QDesktopServices, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QStackedWidget, QVBoxLayout, QScrollArea, QWidget, QFileIconProvider
)

from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, format_file_size, truncate_text_middle

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "svg"


class ResultFileItemWidget(QFrame):
    """File item display for extraction results (Read-only, no remove button)"""
    def __init__(self, filename: str, data: bytes):
        super().__init__()
        self.filename = filename
        self.data = data
        self._temp_path: Path | None = None
        self.setObjectName("fileItemRow")
        self.setFixedHeight(56)
        
        self.setToolTip("Double-click to open")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # 1. Preview / Icon
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(40, 40)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        file_ext = Path(filename).suffix.lower()
        image_exts = ['.png', '.jpg', '.jpeg', '.bmp', '.gif']

        if file_ext in image_exts:
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                scaled_pixmap = pixmap.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                self.icon_label.setPixmap(scaled_pixmap)
            else:
                provider = QFileIconProvider()
                icon = provider.icon(QFileInfo(filename))
                self.icon_label.setPixmap(icon.pixmap(32, 32))
        else:
            provider = QFileIconProvider()
            icon = provider.icon(QFileInfo(filename))
            self.icon_label.setPixmap(icon.pixmap(32, 32))

        layout.addWidget(self.icon_label)

        # 2. Text Info (Name & Size)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        display_name = truncate_text_middle(filename, max_length=40)
        name_label = QLabel(display_name)
        name_label.setObjectName("fileItemName")
        name_label.setToolTip(filename)

        size_label = QLabel(format_file_size(len(data)))
        size_label.setObjectName("fileItemSize")

        text_layout.addWidget(name_label)
        text_layout.addWidget(size_label)
        layout.addLayout(text_layout)
        layout.addStretch()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._temp_path is None:
                suffix = Path(self.filename).suffix or ".bin"
                fd, tmp = tempfile.mkstemp(suffix=suffix, prefix="sieng2_extract_")
                with os.fdopen(fd, "wb") as f:
                    f.write(self.data)
                self._temp_path = Path(tmp)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._temp_path)))


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
        self._files_dict: dict[str, bytes] = {}
        self._raw_zip_data: bytes | None = None
        self._temp_paths: list[Path] = []

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
        self.stack.addWidget(self._build_files_page())
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

    # ---------------------------------------------------------------- files page
    def _build_files_page(self):
        page = QFrame()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(8)

        # 1. Scroll Area สำหรับแสดงรายชื่อไฟล์
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("fileListScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")

        self.list_container = QWidget()
        self.list_container.setObjectName("fileListContainer")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(6)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.list_container)
        pl.addWidget(self.scroll_area, 1)

        # 2. Actions (Save / Open)
        actions = QHBoxLayout()
        actions.addStretch()
        
        self.save_btn = QPushButton(" Save All...")
        self.save_btn.setObjectName("SecondaryBtn")
        self.save_btn.setProperty("textColor", "white")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setIcon(QIcon(create_icon_pixmap(ICON_DIR / "file-export.svg", size=14, color_hex="#FFFFFF")))
        self.save_btn.clicked.connect(self._on_save_all)
        
        actions.addWidget(self.save_btn)
        pl.addLayout(actions)

        return page

    # ---------------------------------------------------------------- public API
    def show_text(self, text: str):
        self.text_area.setPlainText(text)
        self.copy_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        self.stack.setCurrentIndex(0)

    def show_files(self, files_dict: dict[str, bytes], raw_zip_data: bytes = None):
        self._files_dict = files_dict
        self._raw_zip_data = raw_zip_data
        self._temp_paths.clear()
        
        # Update button text
        if len(files_dict) == 1 and not raw_zip_data:
            self.save_btn.setText(" Save As...")
        else:
            self.save_btn.setText(" Save All...")
        
        # Clear existing widgets
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Add new items
        for filename, data in files_dict.items():
            item_widget = ResultFileItemWidget(filename, data)
            self.list_layout.addWidget(item_widget)
            
        self.stack.setCurrentIndex(1)

    def show_result(self, data: bytes, filename: str):
        """สำหรับ payload ของ Locomotive ที่ 'มีชื่อไฟล์จริงติดมา' — ตัดสิน text-vs-file จาก
        ชื่อไฟล์ที่ถูกกำหนดไว้สำหรับ Raw Text โดยเฉพาะ ("secret_message.txt") ถ้าเป็นชื่ออื่น
        ให้ถือว่าเป็นไฟล์แนบ (รวมถึงไฟล์ .txt ที่อัปโหลดมาด้วย) เพื่อให้ผู้ใช้สามารถเซฟต้นฉบับได้"""
        if filename == "secret_message.txt":
            self.show_text(data.decode("utf-8", errors="replace"))
        elif filename == "secret_files.zip":
            # กรณีที่ Locomotive ห่อ zip มาให้ (ผู้ใช้แนบหลายไฟล์)
            import zipfile
            import io
            files_dict = {}
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for info in zf.infolist():
                        if not info.is_dir():
                            files_dict[info.filename] = zf.read(info.filename)
                self.show_files(files_dict, raw_zip_data=data)
            except zipfile.BadZipFile:
                # ถ้าพัง ให้ fallback เป็นไฟล์ zip ธรรมดา
                self.show_files({filename: data})
        else:
            # กรณีเป็นไฟล์เดี่ยว หรือผู้ใช้อัปโหลดไฟล์ zip มาเอง
            self.show_files({filename: data})

    def clear(self):
        self.text_area.setPlainText("")
        self.copy_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self._files_dict.clear()
        self._raw_zip_data = None
        self._temp_paths.clear()
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

    def _on_save_all(self):
        if not self._files_dict:
            return
            
        # ถ้ามีแค่ไฟล์เดียว และไม่ใช่ zip ที่ระบบแพ็คให้
        if len(self._files_dict) == 1 and not self._raw_zip_data:
            filename, data = list(self._files_dict.items())[0]
            path, _ = QFileDialog.getSaveFileName(self, "Save Extracted File", filename, "All Files (*)")
            if not path:
                return
            try:
                Path(path).write_bytes(data)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file:\n{e}")
            return

        # ถ้ามีหลายไฟล์ (zip) ให้โหลดออกมาเป็น secret_files.zip ตรงๆ
        if self._raw_zip_data:
            path, _ = QFileDialog.getSaveFileName(self, "Save Extracted Zip", "secret_files.zip", "Zip Files (*.zip);;All Files (*)")
            if not path:
                return
            try:
                Path(path).write_bytes(self._raw_zip_data)
                QMessageBox.information(self, "Success", "Saved secret_files.zip successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save zip:\n{e}")
