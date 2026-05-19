from pathlib import Path
from PyQt6.QtCore import QFileInfo, Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QMouseEvent, QPixmap
from PyQt6.QtWidgets import (
    QFileDialog, QFileIconProvider, QFrame, QLabel, 
    QVBoxLayout, QHBoxLayout, QPushButton, QScrollArea, QWidget, QMessageBox
)

from src.gui.components.gui_utils import create_icon_pixmap, format_file_size, truncate_text_middle

ICON_DIR = Path(__file__).parent.parent / "assets" / "svg"

# ==========================================
# 1. คลาสสำหรับ 1 แถวของไฟล์ (File Item Row)
# ==========================================
class FileItemWidget(QFrame):
    remove_requested = pyqtSignal(str) # ส่งสัญญาณพร้อม path ไฟล์เมื่อกดปุ่มลบ

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self.setObjectName("fileItemRow")
        self.setFixedHeight(56) # ล็อกความสูงให้ดูเป็นระเบียบ
        
        # ใส่สไตล์ให้ Row ดู Modern และเข้ากับธีม
        self.setStyleSheet("""
            QFrame#fileItemRow {
                background-color: #262D30;
                border: 1px solid #304B57;
                border-radius: 6px;
            }
            QFrame#fileItemRow:hover {
                background-color: #2C3539;
                border: 1px solid #38BDF8;
            }
            QLabel#fileItemName {
                color: #E2E8F0;
                font-size: 12px;
                font-weight: 600;
                border: none;
            }
            QLabel#fileItemSize {
                color: #94A3B8;
                font-size: 10px;
                font-family: 'Courier New', monospace;
                border: none;
            }
            QPushButton#btnRemoveFile {
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }
            QPushButton#btnRemoveFile:hover {
                background-color: rgba(244, 63, 94, 0.1);
            }
            QPushButton#btnRemoveFile:pressed {
                background-color: rgba(244, 63, 94, 0.2);
            }
        """)
        
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        
        file_path_obj = Path(self.file_path)
        file_ext = file_path_obj.suffix.lower()
        image_exts = ['.png', '.jpg', '.jpeg', '.bmp', '.gif']
        
        # 1. Preview / Icon
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(40, 40)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("background-color: #181818; border-radius: 4px; border: none;")
        
        if file_ext in image_exts:
            pixmap = QPixmap(self.file_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                self.icon_label.setPixmap(scaled_pixmap)
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
        
        size_bytes = file_path_obj.stat().st_size
        size_label = QLabel(format_file_size(size_bytes))
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
        remove_icon = QIcon(create_icon_pixmap(ICON_DIR / "x.svg", size=14, color_hex="#f43f5e"))
        self.btn_remove.setIcon(remove_icon)
        self.btn_remove.clicked.connect(lambda: self.remove_requested.emit(self.file_path))
        
        layout.addWidget(self.btn_remove)


# ==========================================
# 2. คลาสหลัก Multi File Drop Zone
# ==========================================
class MultiFileDropWidget(QFrame):
    files_changed = pyqtSignal(list) # ส่ง list ของ path ทั้งหมดเวลามีการเปลี่ยนแปลง

    def __init__(
        self,
        text: str,
        sub_text: str,
        icon_path: str = None,
        allowed_extensions: str | list[str] = "*",
        max_files: int = None  # None = ไม่จำกัด
    ):
        super().__init__()
        self.setAcceptDrops(True)
        
        # Normalize extensions
        if isinstance(allowed_extensions, str):
            if allowed_extensions == "*":
                self.file_exts = ["*"]
            else:
                self.file_exts = [allowed_extensions.lower()]
        else:
            self.file_exts = [
                ext.lower()
                for ext in allowed_extensions
            ]
            
        self.max_files = max_files
        self.selected_files = [] # List เก็บ Path ไฟล์ที่ไม่ซ้ำ
        
        self.init_ui(text, sub_text, icon_path)

    def init_ui(self, text, sub_text, icon_path):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(8)
        
        # 1. Drop Zone (คลิก/ลากวางได้เสมอ)
        self.drop_zone = QFrame()
        self.drop_zone.setObjectName("fileDropZone")
        self.drop_zone.setMinimumHeight(80) 
        self.drop_zone.setCursor(Qt.CursorShape.PointingHandCursor) # ให้รู้ว่าคลิกได้
        # ผูก Event คลิกเฉพาะที่กรอบ Drop Zone (ป้องกันการไปกดโดน ScrollArea แล้วเด้งหน้าต่างเลือกไฟล์)
        self.drop_zone.mousePressEvent = self.open_file_dialog
        
        # แจ้งสถานะเริ่มต้นให้ QSS ทราบว่า "ยังไม่มีไฟล์"
        self.drop_zone.setProperty("hasFile", False)
        
        drop_layout = QVBoxLayout(self.drop_zone)
        drop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon_label = QLabel()
        icon_label.setPixmap(create_icon_pixmap(icon_path or (str(ICON_DIR / "upload.svg")), size=24))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.main_label = QLabel(text)
        self.main_label.setObjectName("mainLabel")
        self.sub_label = QLabel(sub_text)
        self.sub_label.setObjectName("subLabel")
        
        drop_layout.addWidget(icon_label)
        drop_layout.addWidget(self.main_label, alignment=Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(self.sub_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.main_layout.addWidget(self.drop_zone)
        
        # 2. Scroll Area สำหรับแสดงรายชื่อไฟล์
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("fileListScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea#fileListScroll {
                border: none;
                background-color: transparent;
            }
            QWidget#fileListContainer {
                background-color: transparent;
            }
        """)
        self.scroll_area.hide() # ซ่อนไว้ก่อนจนกว่าจะมีไฟล์
        
        self.list_container = QWidget()
        self.list_container.setObjectName("fileListContainer")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(6)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.list_container)
        self.main_layout.addWidget(self.scroll_area, 1) # ยืดขยายพื้นที่ที่เหลือ

    # --- Core Logic ---
    def add_files(self, file_paths: list[str]):
        added_count = 0
        for path in file_paths:
            path_lower = path.lower()
            
            # เช็คสกุลไฟล์
            if not self.is_allowed_file(path_lower):
                continue
                
            # เช็คไฟล์ซ้ำ (เก็บ Path จริงๆ ที่ไม่แปลง lower เพื่อความถูกต้องในการดึงไฟล์)
            if path in self.selected_files:
                continue
                
            # เช็ค Limit
            if self.max_files is not None and len(self.selected_files) >= self.max_files:
                QMessageBox.warning(self, "Limit Reached", f"You can only add up to {self.max_files} files.")
                break
                
            self.selected_files.append(path)
            added_count += 1
            
            # สร้าง UI Row ใหม่
            item_widget = FileItemWidget(path)
            item_widget.remove_requested.connect(self.remove_file)
            self.list_layout.addWidget(item_widget)
            
        if added_count > 0:
            self.scroll_area.show()
            self.update_drop_zone_state()
            self.files_changed.emit(self.selected_files)

    def remove_file(self, file_path: str):
        if file_path in self.selected_files:
            self.selected_files.remove(file_path)
            
            # ลบ Widget ออกจาก Layout
            for i in range(self.list_layout.count()):
                widget = self.list_layout.itemAt(i).widget()
                if isinstance(widget, FileItemWidget) and widget.file_path == file_path:
                    widget.setParent(None)
                    widget.deleteLater()
                    break
                    
            if not self.selected_files:
                self.scroll_area.hide() # ถ้าไม่มีไฟล์แล้ว ให้ซ่อนกรอบ
                
            self.update_drop_zone_state()    
            self.files_changed.emit(self.selected_files)

    # --- Event Overrides ---
    def open_file_dialog(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            # จัดการ Filter ของ File Dialog
            if "*" in self.file_exts:
                file_filter = "All Files (*.*)"
            else:
                patterns = " ".join(f"*{ext}" for ext in self.file_exts)
                names = ", ".join(ext.replace(".", "").upper() for ext in self.file_exts)
                file_filter = f"{names} Files ({patterns})"
                
            file_paths, _ = QFileDialog.getOpenFileNames(self, "Select Files", "", file_filter)
            if file_paths: 
                self.add_files(file_paths)
            
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            file_paths = [url.toLocalFile() for url in event.mimeData().urls()]
            
            # เช็คว่ามีอย่างน้อย 1 ไฟล์ที่นามสกุลผ่านเกณฑ์ ถึงจะยอมให้ลากวาง
            if any(self.is_allowed_file(p.lower()) for p in file_paths):
                event.acceptProposedAction()
                
                self.drop_zone.setProperty("isDragging", True)
                self.drop_zone.style().unpolish(self.drop_zone)
                self.drop_zone.style().polish(self.drop_zone)
                return
            
        event.ignore()
    
    def dragLeaveEvent(self, event):
        self.drop_zone.setProperty("isDragging", False)
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)

    def dropEvent(self, event: QDropEvent):
        self.drop_zone.setProperty("isDragging", False)
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)
        
        file_paths = [url.toLocalFile() for url in event.mimeData().urls()]
        self.add_files(file_paths)
        
    def is_allowed_file(self, file_path: str) -> bool:
        if "*" in self.file_exts:
            return True
            
        return any(
            file_path.endswith(ext)
            for ext in self.file_exts
        )
        
    def update_drop_zone_state(self):
        has_file = len(self.selected_files) > 0
        self.drop_zone.setProperty("hasFile", has_file)
        
        # สั่งให้ PyQt รีเฟรช Style (Unpolish & Polish) เพื่อบังคับให้ CSS อัปเดตใหม่ทันที
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)