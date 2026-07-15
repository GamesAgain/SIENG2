from PyQt6.QtWidgets import QFrame, QVBoxLayout, QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView
from PyQt6.QtGui import QColor, QBrush

class CompareDiffTab(QFrame):
    def __init__(self, headers):
        super().__init__()
        self.headers = headers
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        self.table = QTableWidget(0, len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setObjectName("darkTable")
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        layout.addWidget(self.table)

    def add_row(self, items, color_hex=None):
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)
        for col_idx, item_text in enumerate(items):
            item = QTableWidgetItem(str(item_text))
            if color_hex:
                item.setForeground(QBrush(QColor(color_hex)))
            self.table.setItem(row_idx, col_idx, item)
