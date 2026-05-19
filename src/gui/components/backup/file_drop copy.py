from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
from PyQt6.QtWidgets import QFileDialog, QFrame, QLabel, QVBoxLayout

from src.gui.components.gui_utils import create_icon_pixmap

class FileDropWidget(QFrame):
    """Widget สำหรับ drag & drop file"""
    
    file_selected = pyqtSignal(str)
    
    def __init__(self, text: str, sub_text: str, icon_path: str, file_extension: str):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("fileDropZone")
        
        self.has_file = False
        self.setProperty("hasFile", False)
        self.file_path = ""
        
        self.default_text = text
        self.default_sub_text = sub_text
        self.icon_path = icon_path
        self.file_ext = file_extension.lower() # เช่น ".png", ".txt", หรือ "*"
        
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(6)
        
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setPixmap(create_icon_pixmap(self.icon_path, size=32))
        
        self.main_label = QLabel()
        self.main_label.setObjectName("mainLabel")
        self.main_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.sub_label = QLabel()
        self.sub_label.setObjectName("subLabel")
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        main_layout.addWidget(self.icon_label)
        main_layout.addWidget(self.main_label)
        main_layout.addWidget(self.sub_label)
        
        self.update_ui()
        
    def update_ui(self):
        if self.has_file:
            self.main_label.setText("File Selected")
            self.sub_label.setText(self.file_path)
            self.setProperty("hasFile", True)
        else:
            self.main_label.setText(self.default_text)
            self.sub_label.setText(self.default_sub_text)
            self.setProperty("hasFile", False)
            
        self.style().unpolish(self)
        self.style().polish(self)
        
    def process_file(self, file_path: str):
        self.has_file = True
        self.file_path = file_path
        self.update_ui()
        self.file_selected.emit(file_path)
        
    
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            
            # จัดการ Filter ของ File Dialog
            if self.file_ext == "*":
                file_filter = "All Files (*.*)"
            else:
                ext_upper = self.file_ext.replace('.', '').upper()
                file_filter = f"{ext_upper} Files (*{self.file_ext})"

            file_path, _ = QFileDialog.getOpenFileName(self, "Select File", "", file_filter)
            
            if file_path:
                self.process_file(file_path)
                
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            file_path = event.mimeData().urls()[0].toLocalFile().lower()
            
            # อนุญาตถ้าเป็นไฟล์อะไรก็ได้ ("*") หรือ ถ้านามสกุลตรงกับที่ตั้งไว้
            if self.file_ext == "*" or file_path.endswith(self.file_ext):
                event.acceptProposedAction()
                
                self.setProperty("isDragging", True)
                self.style().unpolish(self)
                self.style().polish(self)
                return
        event.ignore()
    
    def dragLeaveEvent(self, event):
        self.setProperty("isDragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        
        self.update_ui()
                
    def dropEvent(self, event: QDropEvent):
        file_path = event.mimeData().urls()[0].toLocalFile()
        self.process_file(file_path)