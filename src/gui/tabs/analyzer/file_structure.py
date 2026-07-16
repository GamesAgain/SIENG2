from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, 
    QSplitter, QListWidget, QListWidgetItem, QHBoxLayout,
    QScrollArea, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

class FileStructureTab(QFrame):
    def __init__(self):
        super().__init__() 
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setObjectName("transparentScroll")
        
        scroll_content = QWidget()
        scroll_content.setObjectName("transparentScrollContent")
        content_layout = QHBoxLayout(scroll_content)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)
        
        # --- Left Side: Tree and Binwalk (Stacked Vertically) ---
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        
        #Tree
        tree_frame = QFrame()
        tree_frame.setObjectName("card")
        tree_layout = QVBoxLayout(tree_frame)
        
        tree_title = QLabel("Internal Structure")
        tree_title.setObjectName("cardTitle")
        tree_layout.addWidget(tree_title)
        
        self.tree_widget = QTreeWidget()
        self.tree_widget.setObjectName("structureTree")
        self.tree_widget.setHeaderLabels(["Name", "Size", "Value", "Description", "Warnings"])
        self.tree_widget.setColumnWidth(0, 150)
        self.tree_widget.setColumnWidth(1, 80)
        self.tree_widget.setColumnWidth(2, 150)
        self.tree_widget.setMinimumHeight(350)
        tree_layout.addWidget(self.tree_widget)
        
        # Binwalk List
        binwalk_frame = QFrame()
        binwalk_frame.setObjectName("card")
        binwalk_layout = QVBoxLayout(binwalk_frame)
        
        binwalk_title = QLabel("Embedded Signatures")
        binwalk_title.setObjectName("cardTitle")
        binwalk_layout.addWidget(binwalk_title)
        
        self.binwalk_list = QListWidget()
        self.binwalk_list.setObjectName("binwalkList")
        self.binwalk_list.setMinimumHeight(150)
        binwalk_layout.addWidget(self.binwalk_list)
        
        # ใช้ Vertical Splitter เผื่อผู้ใช้ดึงปรับขนาดได้
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.addWidget(tree_frame)
        left_splitter.addWidget(binwalk_frame)
        left_splitter.setSizes([500, 200])
        left_layout.addWidget(left_splitter)
        
        content_layout.addWidget(left_container, stretch=7) # กินพื้นที่ฝั่งซ้าย 70%

        # --- Right Side: Anomalies & Summary ---
        right_container = QFrame()
        right_container.setObjectName("summaryCard")
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(15, 10, 15, 10)
        
        summary_title = QLabel("Anomalies Detected")
        summary_title.setObjectName("cardTitle")
        right_layout.addWidget(summary_title)
        
        self.summary_list = QListWidget()
        self.summary_list.setObjectName("summaryList")
        self.summary_list.setWordWrap(True) # ตัดคำอัตโนมัติถ้าข้อความยาว
        right_layout.addWidget(self.summary_list)
        
        content_layout.addWidget(right_container, stretch=3) # กินพื้นที่ฝั่งขวา 30%
        
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

    def load_data(self, data: dict):
        self.tree_widget.clear()
        self.binwalk_list.clear()
        self.summary_list.clear()
        
        structure_analysis = data.get("structure_analysis", {})
        if not structure_analysis:
            return
            
        hachoir_raw = structure_analysis.get("hachoir_raw", {})
        structure_list = hachoir_raw.get("structure", [])
        self._populate_tree(structure_list, self.tree_widget)
        self.tree_widget.expandAll()
        
        binwalk_raw = structure_analysis.get("binwalk_raw", {})
        signatures = binwalk_raw.get("signatures", [])
        
        if not signatures:
            item = QListWidgetItem("No embedded signatures found.")
            item.setForeground(QBrush(QColor("#94A3B8")))
            self.binwalk_list.addItem(item)
        else:
            for sig in signatures:
                offset = sig.get("offset", 0)
                desc = sig.get("description", "Unknown")
                item = QListWidgetItem(f"Offset 0x{offset:X} : {desc}")
                self.binwalk_list.addItem(item)
                
        # --- Handle Anomalies / Summary ---
        summaries = []
        
        # 1. Overlay
        overlay_info = structure_analysis.get("overlay_analysis", {})
        if overlay_info.get("has_overlay"):
            size = overlay_info.get("overlay_size_bytes", 0)
            item = QListWidgetItem(f"Found {size} bytes of hidden data appended to the file")
            item.setForeground(QBrush(QColor("#f59e0b"))) 
            self.summary_list.addItem(item)
            summaries.append("overlay")
            
        # 2. Suspicious Chunks
        if structure_analysis.get("has_suspicious_chunks"):
            count = structure_analysis.get("suspicious_chunk_count", 0)
            item = QListWidgetItem(f"Detected {count} abnormal or non-standard data chunks")
            item.setForeground(QBrush(QColor("#f43f5e"))) 
            self.summary_list.addItem(item)
            summaries.append("suspicious")
            
        # 3. Signatures
        if len(signatures) > 0:
            item = QListWidgetItem(f"{len(signatures)} embedded file signatures")
            item.setForeground(QBrush(QColor("#38BDF8"))) 
            self.summary_list.addItem(item)
            summaries.append("signatures")
            
        # 4. Clean
        if not summaries:
            item = QListWidgetItem("No structural anomalies or hidden signatures detected.")
            item.setForeground(QBrush(QColor("#34D399"))) 
            self.summary_list.addItem(item)
            
    def _populate_tree(self, chunks: list, parent_item):
        for chunk in chunks:
            name = chunk.get("name", "")
            size = str(chunk.get("size_bytes", ""))
            value = chunk.get("value", "")
            desc = chunk.get("description", "")
            
            is_suspicious = chunk.get("is_suspicious", False)
            reason = chunk.get("suspicious_reason", "")
            
            if len(value) > 100:
                value = value[:100] + "..."
                
            item = QTreeWidgetItem(parent_item)
            item.setText(0, name)
            item.setText(1, size)
            item.setText(2, value)
            item.setText(3, desc)
            item.setText(4, reason)
            
            if is_suspicious:
                red_brush = QBrush(QColor("#f43f5e"))
                for col in range(5):
                    item.setForeground(col, red_brush)
                    
            sub_chunks = chunk.get("sub_chunks", [])
            if isinstance(sub_chunks, list) and len(sub_chunks) > 0:
                self._populate_tree(sub_chunks, item)