from PyQt6.QtWidgets import QAbstractItemView
from PyQt6.QtWidgets import (QWidget, 
                             QHBoxLayout, QVBoxLayout, QFrame, 
                             QLabel, QTableWidget, QTableWidgetItem)

class MetadataTab(QFrame):
    def __init__(self):
        super().__init__() 
        self.init_ui()

    def init_ui(self):
        self.main_layout = QHBoxLayout()
        self.main_layout.setSpacing(10)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        left_card, self.metadata_table = self.create_card("Metadata", ["Property", "Value"])
        right_card, self.anomalies_table = self.create_card("Anomalies Detected", ["Location", "Detail"])

        self.metadata_table.setObjectName("darkTable")
        self.metadata_table.verticalHeader().setVisible(False)
        self.metadata_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.anomalies_table.setObjectName("darkTable")
        self.anomalies_table.verticalHeader().setVisible(False)
        self.anomalies_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.main_layout.addWidget(left_card)
        self.main_layout.addWidget(right_card)

        self.setLayout(self.main_layout)
        
    def create_card(self, title_text, headers):
        card = QFrame()
        card.setObjectName("card") 
        
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(15, 15, 15, 15)
        
        title_label = QLabel(title_text)
        title_label.setObjectName("cardTitle")
        
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)

        card_layout.addWidget(title_label)
        card_layout.addWidget(table)
        card.setLayout(card_layout)
        
        return card, table

    def load_data(self, data: dict):
        metadata = data.get("metadata_analysis", {})
        
        # 1. Load Metadata raw data
        raw_data = metadata.get("raw_data", {})
        self.metadata_table.setRowCount(len(raw_data))
        for row, (key, value) in enumerate(raw_data.items()):
            self.metadata_table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.metadata_table.setItem(row, 1, QTableWidgetItem(str(value)))
            
        # 2. Load Anomalies
        anomalies = []
        anomalies.extend(metadata.get("time_anomalies", []))
        anomalies.extend(metadata.get("software_anomalies", []))
        anomalies.extend(metadata.get("text_anomalies", []))
        
        self.anomalies_table.setRowCount(len(anomalies))
        for row, anomaly in enumerate(anomalies):
            tag = anomaly.get("tag", "Unknown")
            message = anomaly.get("message", "")
            self.anomalies_table.setItem(row, 0, QTableWidgetItem(str(tag)))
            self.anomalies_table.setItem(row, 1, QTableWidgetItem(str(message)))
            
        # Auto resize the first column (Property/Location) to fit content
        self.metadata_table.resizeColumnToContents(0)
        self.anomalies_table.resizeColumnToContents(0)