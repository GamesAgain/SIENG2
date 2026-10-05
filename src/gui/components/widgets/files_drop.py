from pathlib import Path
from PyQt6.QtCore import QEvent, QFileInfo, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QMouseEvent, QPixmap
from PyQt6.QtWidgets import (
    QFileDialog, QFileIconProvider, QFrame, QLabel,
    QVBoxLayout, QHBoxLayout, QPushButton, QScrollArea, QWidget, QMessageBox, QSizePolicy
)

from src.gui.components.gui_utils import create_icon_pixmap, format_file_size, truncate_text_middle
from src.path import svg_path

IMAGE_EXTENSIONS = [
    # 1. Standard & Web (ไฟล์มาตรฐานที่ใช้งานบ่อยที่สุดและรองรับ Preview)
    '.png', '.jpg', '.jpeg', '.gif', '.webp',
    
    # 2. JPEG Family (นามสกุลย่อยที่มักได้จากการดาวน์โหลดบนเว็บ)
    '.jpe', '.jfif',
    
    # 3. Bitmap & High Res (ไฟล์ภาพดิบและภาพความละเอียดสูงสำหรับงานพิมพ์)
    '.bmp', '.dib', '.tiff', '.tif',
    
    # 4. Icons & Legacy Graphics (ไฟล์ไอคอนและกราฟิกเฉพาะทาง)
    '.ico', '.tga'
]

# ==========================================
# 1. คลาสสำหรับ 1 แถวของไฟล์ (File Item Row)
# ==========================================
class FileItemWidget(QFrame):
    remove_requested = pyqtSignal(str) # ส่งสัญญาณพร้อม path ไฟล์เมื่อกดปุ่มลบ

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self.size_bytes = Path(file_path).stat().st_size
        self.setObjectName("fileItemRow")
        self.setFixedHeight(56) # ล็อกความสูงให้ดูเป็นระเบียบ

        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        file_path_obj = Path(self.file_path)
        file_ext = file_path_obj.suffix.lower()

        # 1. Preview / Icon
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(40, 40)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pixmap = QPixmap(self.file_path) if file_ext in IMAGE_EXTENSIONS else QPixmap()
        if not pixmap.isNull():
            self.icon_label.setPixmap(pixmap.scaled(
                40, 40, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            provider = QFileIconProvider()
            icon = provider.icon(QFileInfo(self.file_path))
            self.icon_label.setPixmap(icon.pixmap(32, 32))

        layout.addWidget(self.icon_label)

        # 2. Text Info (Name & Size)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Truncate filename if too long
        full_name = file_path_obj.name
        display_name = truncate_text_middle(full_name, max_length=40)

        name_label = QLabel(display_name)
        name_label.setObjectName("fileItemName")
        name_label.setToolTip(full_name)

        size_label = QLabel(format_file_size(self.size_bytes))
        size_label.setObjectName("fileItemSize")

        text_layout.addWidget(name_label)
        text_layout.addWidget(size_label)
        layout.addLayout(text_layout)

        # ดันให้ปุ่มลบไปอยู่ขวาสุด
        layout.addStretch()

        # 3. Remove Button
        self.btn_remove = QPushButton()
        self.btn_remove.setObjectName("btnRemoveFile")
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.setFixedSize(28, 28)
        remove_icon = QIcon(create_icon_pixmap(svg_path("x.svg"), size=14, color_hex="#f43f5e"))
        self.btn_remove.setIcon(remove_icon)
        self.btn_remove.clicked.connect(lambda: self.remove_requested.emit(self.file_path))

        layout.addWidget(self.btn_remove)


# ==========================================
# 2. คลาสหลัก Unified File Drop Zone
# ==========================================
class FilesDropWidget(QFrame):
    """Widget สำหรับจัดการ Drag & Drop ไฟล์ รองรับทั้งโหมดไฟล์เดียว (Single File) 
    และหลายไฟล์ (Multi File) ผ่านพารามิเตอร์ max_files (1 = ไฟล์เดียว, None = ไม่จำกัด)"""

    file_selected = pyqtSignal(str)   # Signal แจ้งเตือนเมื่อเลือกไฟล์ (คืนค่า path ไฟล์แรก)
    files_changed = pyqtSignal(list)  # Signal แจ้งเตือนเมื่อรายการไฟล์เปลี่ยนแปลง (คืนค่า list ของ path)

    def __init__(
        self,
        text: str,
        sub_text: str,
        icon_path: str = None,
        allowed_extensions: str | list[str] = "*",
        max_files: int = None,       # None = ไม่จำกัด, 1 = Single File Mode
        multi_file: bool = None,     # Helper: False → max_files=1
        *,
        show_preview: bool = True,  # False: selection only; caller displays file details
        parent=None,
    ):
        super().__init__(parent)
        self.setAcceptDrops(True)

        # Resolve multi_file helper → max_files
        if multi_file is not None and not multi_file:
            max_files = 1

        # Keep extension checks consistent for callers using "png" or ".png".
        if isinstance(allowed_extensions, str):
            if allowed_extensions == "*":
                self.file_exts = ["*"]
            else:
                self.file_exts = [self.normalize_extension(allowed_extensions)]
        else:
            self.file_exts = [
                self.normalize_extension(ext)
                for ext in allowed_extensions
            ]

        self.max_files = max_files
        if max_files is not None and max_files < 1:
            raise ValueError("max_files must be positive or None")
        self.show_preview = show_preview
        self.selected_files = []  # List เก็บ Path ไฟล์ที่ไม่ซ้ำ
        self._preview_pixmap = None

        # เก็บค่า Default ไว้ใช้ตอน Reset
        self.default_text = text
        self.default_sub_text = sub_text
        self.default_icon_path = icon_path or str(svg_path("upload.svg"))

        self.init_ui()

    @property
    def is_single_mode(self) -> bool:
        return self.max_files == 1

    # --- Properties สำหรับโหมดไฟล์เดียว ---
    @property
    def has_file(self) -> bool:
        return len(self.selected_files) > 0

    @property
    def file_path(self) -> str:
        return self.selected_files[0] if self.selected_files else ""

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(8)

        # 1. Drop Zone (คลิก/ลากวางได้เสมอ)
        self.drop_zone = QFrame()
        self.drop_zone.installEventFilter(self)
        self.drop_zone.setObjectName("fileDropZone")
        self.drop_zone.setCursor(Qt.CursorShape.PointingHandCursor)
        # ผูก Event คลิกเฉพาะที่กรอบ Drop Zone
        self.drop_zone.mousePressEvent = self.open_file_dialog

        # แจ้งสถานะเริ่มต้นให้ QSS ทราบว่า "ยังไม่มีไฟล์"
        self.drop_zone.setProperty("hasFile", False)

        self.drop_layout = QVBoxLayout(self.drop_zone)
        self.drop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_layout.setSpacing(4)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(create_icon_pixmap(self.default_icon_path, size=30))
        self.icon_label.setMinimumSize(1, 1)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.main_label = QLabel(self.default_text)
        self.main_label.setObjectName("mainLabel")
        self.main_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_label = QLabel(self.default_sub_text)
        self.sub_label.setObjectName("subLabel")
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.drop_layout.addWidget(self.icon_label)
        self.drop_layout.addWidget(self.main_label, alignment=Qt.AlignmentFlag.AlignCenter)
        self.drop_layout.addWidget(self.sub_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.main_layout.addWidget(self.drop_zone, 1)

        # 2. Scroll Area สำหรับแสดงรายชื่อไฟล์
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("fileListScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.hide() # ซ่อนไว้ก่อนจนกว่าจะมีไฟล์

        self.list_container = QWidget()
        self.list_container.setObjectName("fileListContainer")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(6)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.list_container)
        self.main_layout.addWidget(self.scroll_area, 0)

        # Single mode: เก็บ reference ของ FileItemWidget ที่แสดงตรงๆ ใน main_layout
        self._single_item_widget = None
        self.restore_default_drop_zone()

    # --- Core Logic ---
    def add_files(self, file_paths: list[str]) -> bool:
        """Add valid local files; return whether any file was accepted."""
        added_count = 0

        if self.is_single_mode:
            file_paths = file_paths[:1]  # Keep the original first-file policy.

        for path in file_paths:
            if not self.is_allowed_file(path):
                continue

            # Resolve aliases before checking duplicates.
            try:
                path = str(Path(path).resolve())
            except OSError:
                continue

            if not self.is_single_mode and path in self.selected_files:
                continue

            if not self.is_single_mode and self.max_files is not None and len(self.selected_files) >= self.max_files:
                QMessageBox.warning(self, "Limit Reached", f"You can only add up to {self.max_files} files.")
                break

            try:
                Path(path).stat()
                item_widget = FileItemWidget(path) if self.show_preview else None
            except OSError:
                continue

            # Prepare the replacement before removing the current file.
            if self.is_single_mode:
                self._clear_list_widgets()
                self.selected_files.clear()

            self.selected_files.append(path)
            added_count += 1

            if item_widget is None:
                continue
            item_widget.remove_requested.connect(self.remove_file)

            if self.is_single_mode:
                # Single mode: แสดง FileItemWidget ตรงๆ ใน main_layout (ไม่ใช้ scroll_area)
                self._single_item_widget = item_widget
                self.main_layout.addWidget(item_widget)
            else:
                self.list_layout.addWidget(item_widget)

        if added_count > 0:
            self.update_drop_zone_state()
            self._emit_signals()
        return added_count > 0

    def remove_file(self, file_path: str):
        if file_path in self.selected_files:
            self.selected_files.remove(file_path)

            if self.is_single_mode and self._single_item_widget:
                # Single mode: ลบ widget ที่อยู่ตรงๆ ใน main_layout
                self.main_layout.removeWidget(self._single_item_widget)
                self._single_item_widget.hide()
                self._single_item_widget.deleteLater()
                self._single_item_widget = None
            else:
                # Multi mode: ลบ widget ออกจาก list_layout (ใน scroll_area)
                for i in range(self.list_layout.count()):
                    widget = self.list_layout.itemAt(i).widget()
                    if isinstance(widget, FileItemWidget) and widget.file_path == file_path:
                        self.list_layout.removeWidget(widget)
                        widget.hide()
                        widget.deleteLater()
                        break

            self.update_drop_zone_state()
            self._emit_signals()

    def clear_file(self):
        """ล้างไฟล์ที่เลือกไว้ กลับไปเป็นกล่อง drop zone ค่าเริ่มต้น"""
        self.clear_all()

    def clear_all(self):
        """ล้างไฟล์ที่เลือกไว้ทั้งหมด กลับไปเป็นกล่อง drop zone ค่าเริ่มต้น"""
        self._clear_list_widgets()
        self.selected_files.clear()
        self._preview_pixmap = None
        self.update_drop_zone_state()
        self._emit_signals()

    def get_selected_files(self) -> list[str]:
        return list(self.selected_files)

    def process_file(self, file_path: str):
        """ประมวลผลเพิ่มไฟล์ที่เลือกลงใน Widget"""
        self.add_files([file_path])

    # --- Internal Helpers ---
    def _clear_list_widgets(self):
        # ล้าง Single mode widget (ถ้ามี)
        if self._single_item_widget:
            self.main_layout.removeWidget(self._single_item_widget)
            self._single_item_widget.hide()
            self._single_item_widget.deleteLater()
            self._single_item_widget = None

        # ล้าง Multi mode widgets ใน scroll_area
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.deleteLater()

    def _emit_signals(self):
        self.files_changed.emit(list(self.selected_files))
        # ส่งสัญญาณ file_selected สอดคล้องตามไฟล์แรกที่เลือก
        self.file_selected.emit(self.file_path)

    # --- Event Overrides ---
    def eventFilter(self, watched, event):
        if watched is self.drop_zone and event.type() == QEvent.Type.Resize and self._preview_pixmap is not None:
            # The child layout must settle before measuring its preview area.
            QTimer.singleShot(0, self._scale_preview)
        return super().eventFilter(watched, event)

    def open_file_dialog(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            # จัดการ Filter ของ File Dialog
            if "*" in self.file_exts:
                file_filter = "All Files (*.*)"
            else:
                patterns = " ".join(f"*{ext}" for ext in self.file_exts)
                names = ", ".join(ext.replace(".", "").upper() for ext in self.file_exts)
                file_filter = f"{names} Files ({patterns})"

            if self.is_single_mode:
                file_path, _ = QFileDialog.getOpenFileName(self, "Select File", "", file_filter)
                if file_path:
                    self.add_files([file_path])
            else:
                file_paths, _ = QFileDialog.getOpenFileNames(self, "Select Files", "", file_filter)
                if file_paths:
                    self.add_files(file_paths)

    def dragEnterEvent(self, event: QDragEnterEvent):
        file_paths = self._local_drop_paths(event)
        accepted = any(self.is_allowed_file(path) for path in file_paths)
        self._set_dragging(accepted)
        if accepted:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_dragging(False)

    def dropEvent(self, event: QDropEvent):
        self._set_dragging(False)
        if self.add_files(self._local_drop_paths(event)):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _local_drop_paths(self, event) -> list[str]:
        urls = event.mimeData().urls()
        # Single mode considers only the first URL, just like add_files().
        if self.is_single_mode:
            urls = urls[:1]
        return [url.toLocalFile() for url in urls if url.isLocalFile()]

    def _set_dragging(self, active: bool):
        self.drop_zone.setProperty("isDragging", active)
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)

    def is_allowed_file(self, file_path: str) -> bool:
        if not file_path:
            return False
        try:
            path = Path(file_path)
            return path.is_file() and (
                "*" in self.file_exts or path.suffix.lower() in self.file_exts
            )
        except OSError:
            return False

    @staticmethod
    def normalize_extension(extension: str) -> str:
        if extension == "*":
            return extension

        extension = extension.lower()
        return extension if extension.startswith(".") else f".{extension}"

    # --- Drop Zone State & Preview ---
    def update_drop_zone_state(self):
        count = len(self.selected_files)
        self._preview_pixmap = None
        self.scroll_area.setVisible(self.show_preview and not self.is_single_mode and count > 0)
        self.main_layout.setStretch(0, 0 if self.show_preview and count > 1 else 1)
        self.main_layout.setStretch(1, 1 if self.show_preview and count > 1 else 0)

        if count != 1 or not self.show_preview:
            self.restore_default_drop_zone()
        else:
            file_path = self.selected_files[0]
            if Path(file_path).suffix.lower() in IMAGE_EXTENSIONS:
                pixmap = QPixmap(file_path)
                if not pixmap.isNull():
                    self._preview_pixmap = pixmap
            self.render_single_preview(file_path)

        self.drop_zone.setProperty("hasFile", count > 0)
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)

    def restore_default_drop_zone(self):
        self.drop_layout.setContentsMargins(10, 10, 10, 10)
        self.drop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.icon_label.setMaximumSize(16777215, 16777215)
        self.icon_label.setPixmap(create_icon_pixmap(self.default_icon_path, size=30))
        self.main_label.setText(self.default_text)
        self.sub_label.setText(self.default_sub_text)
        self.main_label.show()
        self.sub_label.show()

    def render_single_preview(self, file_path):
        file_path_obj = Path(file_path)
        self.drop_layout.setContentsMargins(10, 10, 10, 10)
        self.icon_label.setMaximumSize(16777215, 16777215)

        if self._preview_pixmap is not None:
            # The scaled image must follow the layout, not change its size hint.
            self.icon_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            self.drop_layout.setAlignment(Qt.AlignmentFlag(0))
            self.main_label.hide()
            self.sub_label.hide()
            self._scale_preview()
        else:
            self.icon_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self.drop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.main_label.show()
            self.sub_label.show()

            provider = QFileIconProvider()
            icon = provider.icon(QFileInfo(file_path))
            self.icon_label.setPixmap(icon.pixmap(48, 48))

            self.main_label.setText(truncate_text_middle(file_path_obj.name, 40))
            try:
                self.sub_label.setText(format_file_size(file_path_obj.stat().st_size))
            except OSError:
                self.sub_label.setText("File unavailable")

    def _scale_preview(self):
        """Resize only the cached image; do not read file metadata on resize."""
        if self._preview_pixmap is None:
            return
        margins = self.drop_layout.contentsMargins()
        # contentsRect excludes the styled border; margins belong to the layout.
        content = self.drop_zone.contentsRect()
        target_w = max(1, content.width() - margins.left() - margins.right())
        target_h = max(1, content.height() - margins.top() - margins.bottom())
        self.icon_label.setMaximumSize(target_w, target_h)
        self.icon_label.setPixmap(self._preview_pixmap.scaled(
            target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))


# ==========================================
# 3. Helper Wrappers สำหรับโหมด Single / Multi
# ==========================================
class FileDropWidget(FilesDropWidget):
    """Widget สำหรับ Drag & Drop ในโหมดไฟล์เดียว (Single File)"""

    def __init__(
        self,
        text: str,
        sub_text: str,
        icon_path: str = None,
        allowed_extensions: str | list[str] = "*",
        *,
        show_preview: bool = True,
        parent=None,
    ):
        super().__init__(
            text=text,
            sub_text=sub_text,
            icon_path=icon_path,
            allowed_extensions=allowed_extensions,
            max_files=1,
            show_preview=show_preview,
            parent=parent,
        )


class MultiFileDropWidget(FilesDropWidget):
    """Widget สำหรับ Drag & Drop ในโหมดหลายไฟล์ (Multi File)"""

    def __init__(
        self,
        text: str,
        sub_text: str,
        icon_path: str = None,
        allowed_extensions: str | list[str] = "*",
        max_files: int = None,
        *,
        show_preview: bool = True,
        parent=None,
    ):
        super().__init__(
            text=text,
            sub_text=sub_text,
            icon_path=icon_path,
            allowed_extensions=allowed_extensions,
            max_files=max_files,
            show_preview=show_preview,
            parent=parent,
        )
