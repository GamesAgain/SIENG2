from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, 
    QTableWidget, QTableWidgetItem, QListWidget, QListWidgetItem, QAbstractItemView
)
from PyQt6.QtGui import QColor, QBrush

class BitStatTab(QFrame):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.main_layout = QHBoxLayout()
        self.main_layout.setSpacing(10)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        card, self.metadata_table = self.create_card("Steganalysis Method", ["METHOD", "ESTIMATE", "THRESHOLD", "VERDICT"])

        self.metadata_table.setObjectName("darkTable")
        self.metadata_table.verticalHeader().setVisible(False)
        self.metadata_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.main_layout.addWidget(card)

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
        self.metadata_table.setRowCount(0)
        
        stat_results = data.get("statistical_analysis", {})
        if not stat_results or "error" in stat_results:
            return
            
        rows = []
        
        if "chi_square" in stat_results:
            chi_data = stat_results["chi_square"]
            chi2 = chi_data.get("chi2", 0)
            p_val = chi_data.get("p_value", 0)
            detected = chi_data.get("detected", False)
            rows.append(("Chi-Square Attack", f"χ² = {chi2:.2f}, p = {p_val:.4f}", "p < 0.05", detected))
            
        if "rs_analysis" in stat_results:
            rs_data = stat_results["rs_analysis"]
            asymmetry = rs_data.get("asymmetry", 0)
            detected = rs_data.get("detected", False)
            rows.append(("RS Analysis", f"Asymmetry = {asymmetry:.4f}", "|Asymmetry| > 0.02", detected))
            
        if "bit_balance" in stat_results:
            bb_data = stat_results["bit_balance"]
            z_ratio = bb_data.get("zero_ratio", 0)
            o_ratio = bb_data.get("one_ratio", 0)
            detected = bb_data.get("detected", False)
            rows.append(("Bit Balance Test", f"0: {z_ratio:.2f}%, 1: {o_ratio:.2f}%", "~50.0%", detected))
            
        if "spa" in stat_results:
            spa_data = stat_results["spa"]
            est_rate = spa_data.get("estimated_embedding_rate", 0)
            detected = spa_data.get("detected", False)
            rows.append(("Sample Pairs Analysis (SPA)", f"Est. Rate = {est_rate:.4f}", "Rate > 0.05", detected))
            
        if "correlation" in stat_results:
            corr_data = stat_results["correlation"]
            corr = corr_data.get("correlation", 0)
            detected = corr_data.get("detected", False)
            rows.append(("Correlation Analysis", f"Corr = {corr:.4f}", "Corr < 0.1", detected))
            
        self.metadata_table.setRowCount(len(rows))
        for row_idx, (method, estimate, threshold, detected) in enumerate(rows):
            method_item = QTableWidgetItem(method)
            estimate_item = QTableWidgetItem(estimate)
            threshold_item = QTableWidgetItem(threshold)
            
            verdict_text = "Suspicious" if detected else "Normal"
            verdict_item = QTableWidgetItem(verdict_text)
            
            if detected:
                verdict_item.setForeground(QBrush(QColor("#EF4444"))) # Red
            else:
                verdict_item.setForeground(QBrush(QColor("#10B981"))) # Green
                
            self.metadata_table.setItem(row_idx, 0, method_item)
            self.metadata_table.setItem(row_idx, 1, estimate_item)
            self.metadata_table.setItem(row_idx, 2, threshold_item)
            self.metadata_table.setItem(row_idx, 3, verdict_item)