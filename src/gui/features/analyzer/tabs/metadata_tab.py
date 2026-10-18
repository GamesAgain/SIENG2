"""Metadata inspection view."""

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.core.analyzer.models.analysis import AnalysisResult


class MetadataTab(QFrame):
    """Own and display the metadata section of an analysis result."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.analysis_result: AnalysisResult | None = None
        self._setup_ui()
        self.clear_analysis_result()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.status_hint = QLabel()
        self.status_hint.setObjectName("hintLabel")
        self.status_hint.setWordWrap(True)
        layout.addWidget(self.status_hint)

        self.metadata_table = self._table(["Property", "Value"])
        self.anomalies_table = self._table(["Location", "Detail"])
        split = QSplitter()
        split.addWidget(self._card("Metadata", self.metadata_table))
        split.addWidget(self._card("Anomalies Detected", self.anomalies_table))
        split.setSizes([550, 450])
        layout.addWidget(split, 1)

    @staticmethod
    def _card(title: str, widget) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)
        label = QLabel(title)
        label.setObjectName("cardTitle")
        layout.addWidget(label)
        layout.addWidget(widget, 1)
        return card

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setObjectName("analysisRawTable")
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        for column in range(len(headers)):
            table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.Stretch
            )
        return table

    def set_analysis_result(self, result: AnalysisResult) -> None:
        """Store the completed result and show metadata availability."""
        if not isinstance(result, AnalysisResult):
            raise TypeError("result must be an AnalysisResult.")

        self.analysis_result = result

    def clear_analysis_result(self) -> None:
        """Forget the old result and restore the waiting state."""
        self.analysis_result = None
        self.metadata_table.setRowCount(0)
        self.anomalies_table.setRowCount(0)
        self.status_hint.setText("Analysis results will appear here.")

    def set_inspection_status(self, message: str) -> None:
        """Show inspection progress before the detailed result UI is installed."""
        self.status_hint.setText(message)

    def load_data(self, data: dict) -> None:
        """Render ExifTool metadata and all inspection anomaly categories."""
        result = data.get("metadata_analysis", {})
        error = result.get("error")
        raw = result.get("raw_data", {})
        self.metadata_table.setRowCount(len(raw))
        for row, (key, value) in enumerate(raw.items()):
            self.metadata_table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.metadata_table.setItem(row, 1, QTableWidgetItem(str(value)))
        anomalies = [
            entry
            for key in ("time_anomalies", "software_anomalies", "text_anomalies")
            for entry in result.get(key, [])
        ]
        if not anomalies and not error:
            anomalies = [{"tag": "", "message": "No anomalies detected."}]
        self.anomalies_table.setRowCount(len(anomalies))
        for row, entry in enumerate(anomalies):
            self.anomalies_table.setItem(
                row, 0, QTableWidgetItem(str(entry.get("tag", "")))
            )
            self.anomalies_table.setItem(
                row, 1, QTableWidgetItem(str(entry.get("message", "")))
            )
        self.metadata_table.resizeColumnToContents(0)
        self.anomalies_table.resizeColumnToContents(0)
        self.set_inspection_status(
            f"Metadata inspection failed: {error}" if error else ""
        )
