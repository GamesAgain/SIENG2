from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, 
    QSplitter, QListWidget, QListWidgetItem, QHBoxLayout,
    QScrollArea, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

class StructDiffTab(QFrame):
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
        
        tree_title = QLabel("Internal Structure (Stego File)")
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
        
        binwalk_title = QLabel("Embedded Signatures (Stego File)")
        binwalk_title.setObjectName("cardTitle")
        binwalk_layout.addWidget(binwalk_title)
        
        self.binwalk_list = QListWidget()
        self.binwalk_list.setObjectName("binwalkList")
        self.binwalk_list.setMinimumHeight(150)
        binwalk_layout.addWidget(self.binwalk_list)
        
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.addWidget(tree_frame)
        left_splitter.addWidget(binwalk_frame)
        left_splitter.setSizes([500, 200])
        left_layout.addWidget(left_splitter)
        
        content_layout.addWidget(left_container, stretch=7) # 70%
        
        # --- Right Side: Anomalies & Summary ---
        right_container = QFrame()
        right_container.setObjectName("summaryCard")
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(15, 10, 15, 10)
        
        summary_title = QLabel("Structural Comparison & Anomalies")
        summary_title.setObjectName("cardTitle")
        right_layout.addWidget(summary_title)
        
        self.summary_list = QListWidget()
        self.summary_list.setObjectName("summaryList")
        self.summary_list.setWordWrap(True)
        right_layout.addWidget(self.summary_list)
        
        content_layout.addWidget(right_container, stretch=3) # 30%
        
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

    def load_data(self, struct_diff: dict):
        self.tree_widget.clear()
        self.binwalk_list.clear()
        self.summary_list.clear()
        
        if not struct_diff:
            return
            
        orig_res = struct_diff.get("original", {})
        stego_res = struct_diff.get("stego", {})
        
        orig_chunks = orig_res.get("hachoir_raw", {}).get("structure", [])
        stego_chunks = stego_res.get("hachoir_raw", {}).get("structure", [])
        
        self.added_chunks = 0
        self.modified_chunks = 0
        
        self._populate_tree(stego_chunks, orig_chunks, self.tree_widget)
        self.tree_widget.expandAll()
        
        orig_sigs = orig_res.get("binwalk_raw", {}).get("signatures", [])
        stego_sigs = stego_res.get("binwalk_raw", {}).get("signatures", [])
        self._populate_binwalk(stego_sigs, orig_sigs, self.binwalk_list)
        
        self._build_summary(orig_res, stego_res, self.summary_list)

    def _populate_tree(self, stego_chunks: list, orig_chunks: list, parent_item):
        i = 0
        
        for j, stego_c in enumerate(stego_chunks):
            # Try to get corresponding orig chunk by matching index and name
            orig_c = None
            if i < len(orig_chunks) and orig_chunks[i].get("name") == stego_c.get("name"):
                orig_c = orig_chunks[i]
                i += 1
            
            name = stego_c.get("name", "")
            size = str(stego_c.get("size_bytes", ""))
            value = stego_c.get("value", "")
            desc = stego_c.get("description", "")
            reason = stego_c.get("suspicious_reason", "")
            
            if len(value) > 100:
                value = value[:100] + "..."
                
            item = QTreeWidgetItem(parent_item)
            item.setText(0, name)
            item.setText(1, size)
            item.setText(2, value)
            item.setText(3, desc)
            item.setText(4, reason)
            
            # Determine color highlight based on comparison
            color_hex = None
            
            if not orig_c:
                # Stego has a chunk that Original doesn't have in this sequence
                color_hex = "#EF4444" # Red for ADDED
                self.added_chunks += 1
            else:
                orig_size = str(orig_c.get("size_bytes", ""))
                if orig_size != size:
                    color_hex = "#EAB308" # Yellow for MODIFIED size
                    self.modified_chunks += 1
                elif orig_c.get("value") != stego_c.get("value"):
                    color_hex = "#EAB308" # Yellow for MODIFIED value
                    self.modified_chunks += 1
            
            if color_hex:
                brush = QBrush(QColor(color_hex))
                for col in range(5):
                    item.setForeground(col, brush)
                    
            sub_stego = stego_c.get("sub_chunks", [])
            sub_orig = orig_c.get("sub_chunks", []) if orig_c else []
            
            if isinstance(sub_stego, list) and len(sub_stego) > 0:
                self._populate_tree(sub_stego, sub_orig, item)

    def _populate_binwalk(self, stego_sigs, orig_sigs, list_widget):
        if not stego_sigs:
            item = QListWidgetItem("No embedded signatures found.")
            item.setForeground(QBrush(QColor("#94A3B8")))
            list_widget.addItem(item)
            return
            
        orig_offsets = {s.get("offset", 0) for s in orig_sigs}
        
        for sig in stego_sigs:
            offset = sig.get("offset", 0)
            desc = sig.get("description", "Unknown")
            item = QListWidgetItem(f"Offset 0x{offset:X} : {desc}")
            
            if offset not in orig_offsets:
                item.setForeground(QBrush(QColor("#EF4444"))) # Highlight new signatures in red
                
            list_widget.addItem(item)

    def _build_summary(self, orig_res: dict, stego_res: dict, list_widget: QListWidget):
        has_anomaly = False
        
        # 1. Overlay Comparison
        orig_overlay = orig_res.get("overlay_analysis", {})
        stego_overlay = stego_res.get("overlay_analysis", {})
        
        if stego_overlay.get("has_overlay") and not orig_overlay.get("has_overlay"):
            size = stego_overlay.get("overlay_size_bytes", 0)
            item = QListWidgetItem(f"Found {size} bytes of hidden data appended to the stego file!")
            item.setForeground(QBrush(QColor("#f43f5e"))) 
            list_widget.addItem(item)
            has_anomaly = True
        elif stego_overlay.get("has_overlay") and orig_overlay.get("has_overlay"):
            size_o = orig_overlay.get("overlay_size_bytes", 0)
            size_s = stego_overlay.get("overlay_size_bytes", 0)
            if size_s > size_o:
                item = QListWidgetItem(f"Overlay grew from {size_o} bytes to {size_s} bytes (+{size_s-size_o} bytes)")
                item.setForeground(QBrush(QColor("#f59e0b"))) 
                list_widget.addItem(item)
                has_anomaly = True
                
        # 2. Structural Chunks Diff
        if self.added_chunks > 0:
            item = QListWidgetItem(f"Found {self.added_chunks} new data chunks in stego file.")
            item.setForeground(QBrush(QColor("#f43f5e"))) 
            list_widget.addItem(item)
            has_anomaly = True
            
        if self.modified_chunks > 0:
            item = QListWidgetItem(f"{self.modified_chunks} chunks have different sizes or values.")
            item.setForeground(QBrush(QColor("#f59e0b"))) 
            list_widget.addItem(item)
            has_anomaly = True
            
        # 3. Binwalk Signatures Comparison
        orig_sigs = len(orig_res.get("binwalk_raw", {}).get("signatures", []))
        stego_sigs = len(stego_res.get("binwalk_raw", {}).get("signatures", []))
        
        if stego_sigs > orig_sigs:
            diff = stego_sigs - orig_sigs
            item = QListWidgetItem(f"{diff} new embedded file signatures found in stego file.")
            item.setForeground(QBrush(QColor("#f43f5e"))) 
            list_widget.addItem(item)
            has_anomaly = True
            
        # Clean
        if not has_anomaly:
            item = QListWidgetItem("Structure is identical to original file.")
            item.setForeground(QBrush(QColor("#10B981"))) 
            list_widget.addItem(item)
