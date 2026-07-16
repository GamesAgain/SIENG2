from pathlib import Path
from PyQt6.QtCore import QFileInfo, Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent, QPixmap
from PyQt6.QtWidgets import QFileDialog, QFileIconProvider, QFrame, QLabel, QSizePolicy, QVBoxLayout

from src.gui.components.gui_utils import create_icon_pixmap, format_file_size

ICON_DIR = Path(__file__).parent.parent / "assets" / "svg"

class FileDropWidget(QFrame):
    """Widget สำหรับ drag & drop file"""
    
    file_selected = pyqtSignal(str)
    
    def __init__(
        self,
        text: str,
        sub_text: str,
        icon_path: str = None,
        allowed_extensions: str | list[str] = "*"
    ):
        super().__init__()

        self.setAcceptDrops(True)
        self.setObjectName("fileDropZone")

        if icon_path is None:
            icon_path = ICON_DIR / "upload.svg"

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
        # Initialize state
        self.has_file = False
        self.setProperty("hasFile", False)

        self.file_path = ""
        self.original_pixmap = None
        
        self.default_text = text
        self.default_sub_text = sub_text
        self.icon_path = icon_path
        
        self.setup_ui()
        
        self.update_ui()
    
    def setup_ui(self):
        
        self.setMinimumHeight(100)
        
        # Setup layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(4)
        
        # Icon label
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setMinimumSize(1, 1)
        self.icon_label.setPixmap(create_icon_pixmap(self.icon_path, size=30))
        
        # self.icon_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        
        
        # Text labels
        self.main_label = QLabel()
        self.main_label.setObjectName("mainLabel")
        self.main_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.sub_label = QLabel()
        self.sub_label.setObjectName("subLabel")
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.main_layout.addWidget(self.icon_label)
        self.main_layout.addWidget(self.main_label)
        self.main_layout.addWidget(self.sub_label)
    
    def update_ui(self):
        if self.has_file:
            self.setProperty("hasFile", True)
            
            # ซ่อนข้อความ Labels ทั้งหมด เพื่อเคลียร์พื้นที่ให้รูปภาพ
            self.main_label.hide()
            self.sub_label.hide()
            
            self.main_layout.setContentsMargins(0, 0, 0, 0)
            
            # สั่งวาดรูปให้เต็มพื้นที่กรอบ
            self.render_preview()
        else:
            self.setProperty("hasFile", False)
            
            # คืนค่าสไตล์กล่องเปล่า แสดงข้อความและไอคอนกลับมา
            self.main_label.show()
            self.sub_label.show()
            self.main_label.setText(self.default_text)
            self.sub_label.setText(self.default_sub_text)
            
            self.main_layout.setContentsMargins(10, 10, 10, 10)
            self.icon_label.setPixmap(create_icon_pixmap(self.icon_path, size=30))
        
        # สั่งวาด Style ใหม่    
        self.style().unpolish(self)
        self.style().polish(self)
        
    def render_preview(self):
        if not self.has_file:
            return
            
        file_path_obj = Path(self.file_path)
        file_ext = file_path_obj.suffix.lower()
        
        # กำหนดนามสกุลที่ถือว่าเป็น "รูปภาพ" เพื่อวาดพรีวิว
        image_exts = ['.png', '.jpg', '.jpeg', '.bmp', '.gif']
        
        if file_ext in image_exts and self.original_pixmap is not None:
            # -----------------------------------------
            # โหมดที่ 1: รูปภาพ (วาดรูปเต็มกรอบ)
            # -----------------------------------------
            self.main_label.hide()
            self.sub_label.hide()
            self.main_layout.setContentsMargins(0, 0, 0, 0)
            
            target_w = self.width()
            target_h = self.height()
            
            if target_w <= 0 or target_h <= 0:
                return
                
            scaled_pixmap = self.original_pixmap.scaled(
                target_w, target_h,
                Qt.AspectRatioMode.KeepAspectRatio, # รักษาอัตราส่วน
                Qt.TransformationMode.SmoothTransformation
            )
            self.icon_label.setPixmap(scaled_pixmap)
            
                
        else:
            # -----------------------------------------
            #  โหมดที่ 2: ไฟล์ทั่วไป (แสดง OS Icon + ชื่อไฟล์)
            # -----------------------------------------
            self.main_label.show()
            self.sub_label.show()
            self.main_layout.setContentsMargins(10, 10, 10, 10)
            
            provider = QFileIconProvider()
            file_info = QFileInfo(self.file_path)
            icon = provider.icon(file_info)
            
            # วาดไอคอนขนาด 64x64 (คุณสามารถปรับขนาดได้ตามต้องการ)
            pixmap = icon.pixmap(64, 64)
            self.icon_label.setPixmap(pixmap)
            
            #  ดึงขนาดไฟล์จาก OS (หน่วยเป็น Bytes)
            file_size_bytes = file_path_obj.stat().st_size
            
            # คำนวณแปลงหน่วยให้สวยงามอ่านง่าย
            size_text = format_file_size(file_size_bytes)
                
            self.main_label.setText(file_path_obj.name)
            self.sub_label.setText(size_text)
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # ทุกครั้งที่กรอบมีการยืดหด ให้คำนวณสัดส่วนและตัดรูปภาพใหม่ทันที รูปจะไม่เบี้ยวและเต็มกรอบตลอดเวลา
        if self.has_file:
            self.render_preview()
        
    def process_file(self, file_path: str):
        self.has_file = True
        self.file_path = file_path
        
        # โหลดรูปเก็บไว้ใน Cache
        image_exts = ['.png', '.jpg', '.jpeg', '.bmp', '.gif']
        if Path(file_path).suffix.lower() in image_exts:
            self.original_pixmap = QPixmap(file_path)
        else:
            self.original_pixmap = None
            
        self.update_ui()
        self.file_selected.emit(file_path)

    def clear_file(self):
        """ล้างไฟล์ที่เลือกไว้ กลับไปเป็นกล่อง drop zone ค่าเริ่มต้น"""
        self.has_file = False
        self.file_path = ""
        self.original_pixmap = None

        self.update_ui()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            
            # จัดการ Filter ของ File Dialog
            if "*" in self.file_exts:
                file_filter = "All Files (*.*)"
            else:
                patterns = " ".join(f"*{ext}" for ext in self.file_exts)

                names = ", ".join(
                    ext.replace(".", "").upper()
                    for ext in self.file_exts
                )

                file_filter = f"{names} Files ({patterns})"

            file_path, _ = QFileDialog.getOpenFileName(self, "Select File", "", file_filter)
            
            if file_path:
                self.process_file(file_path)
                
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            file_path = event.mimeData().urls()[0].toLocalFile().lower()
            
            # อนุญาตถ้าเป็นไฟล์อะไรก็ได้ ("*") หรือ ถ้านามสกุลตรงกับที่ตั้งไว้
            if self.is_allowed_file(file_path):
                event.acceptProposedAction()
                
                self.setProperty("isDragging", True)
                self.style().unpolish(self)
                self.style().polish(self)
                return
            
        event.ignore()
    
    def dragLeaveEvent(self, event):
        self.setProperty("isDragging", False)
        self.update_ui()
                
    def dropEvent(self, event: QDropEvent):
        self.setProperty("isDragging", False)
        
        file_path = event.mimeData().urls()[0].toLocalFile()
        self.process_file(file_path)
        
        
    def is_allowed_file(self, file_path: str) -> bool:
        file_path = file_path.lower()

        if "*" in self.file_exts:
            return True

        return any(
            file_path.endswith(ext)
            for ext in self.file_exts
        )