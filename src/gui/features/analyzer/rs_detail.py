"""RS Analysis result widgets for the Bit Statistics tab."""

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.gui.features.analyzer.chi_square_detail import (
    ChannelSelector,
    MetricTile,
    PValueLineChart,
    format_integer,
    format_number,
    format_percent,
)


RS_COLORS = {
    "Regular": "#4096F0",
    "Singular": "#35BC79",
    "Unusable": "#E67D47",
}


class RSDistributionChart(QWidget):
    """Grouped bars for Regular, Singular and Unusable fractions."""

    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.result = result
        self.setFixedHeight(230)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = self.rect().adjusted(48, 14, -18, -34)
        if plot.width() <= 0 or plot.height() <= 0:
            return

        grid_pen = QPen(QColor("#39424A"), 1, Qt.PenStyle.DashLine)
        text_color = QColor("#8FA2B5")
        if self.result.total_groups == 0:
            painter.setPen(text_color)
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "N/A - no complete groups")
            return
        for step in range(5):
            value = step / 4
            y = plot.bottom() - value * plot.height()
            painter.setPen(grid_pen)
            painter.drawLine(plot.left(), int(y), plot.right(), int(y))
            painter.setPen(text_color)
            painter.drawText(4, int(y + 4), f"{value:.2f}")

        groups = (
            ("M", (self.result.RM, self.result.SM, self.result.UM)),
            ("−M", (
                self.result.R_negM,
                self.result.S_negM,
                self.result.U_negM,
            )),
        )
        group_width = min(210.0, plot.width() / 2.8)
        bar_gap = 6.0
        bar_width = (group_width - bar_gap * 2) / 3
        group_centers = (
            plot.left() + plot.width() * 0.28,
            plot.left() + plot.width() * 0.72,
        )
        colors = tuple(RS_COLORS.values())
        for (name, values), center in zip(groups, group_centers):
            left = center - group_width / 2
            for index, value in enumerate(values):
                fraction = 0.0 if value is None else min(1.0, max(0.0, value))
                height = fraction * plot.height()
                rect = QRectF(
                    left + index * (bar_width + bar_gap),
                    plot.bottom() - height,
                    bar_width,
                    height,
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(colors[index]))
                painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(text_color)
            painter.drawText(
                int(center - 30), plot.bottom() + 8, 60, 20,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                name,
            )


class RSDetail(QFrame):
    """RS distribution, prefix trend, payload estimate and raw tables."""

    channel_changed = pyqtSignal(str)
    tab_changed = pyqtSignal(str)

    TABS = (
        ("distribution", "Distribution"),
        ("prefix", "Progressive Prefix"),
        ("raw", "Raw Data"),
    )

    def __init__(self, report, selected_channel, selected_tab="distribution", parent=None):
        super().__init__(parent)
        self.setObjectName("analysisDetailPanel")
        self.setProperty("detectorType", "rs")
        self.report = report
        self.selected_channel = selected_channel
        self.selected_tab = selected_tab
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(14, 13, 14, 14)
        layout.setSpacing(11)

        header = QHBoxLayout()
        title = QLabel("RS Analysis")
        title.setObjectName("analysisPanelTitle")
        badge = QLabel("M / −M")
        badge.setObjectName("analysisPanelBadge")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(badge)
        layout.addLayout(header)

        self.channel_selector = ChannelSelector(
            list(self.report), self.selected_channel
        )
        self.channel_selector.channel_changed.connect(self.channel_changed)
        layout.addWidget(self.channel_selector)

        tab_row = QFrame()
        tab_row.setObjectName("analysisDetailTabs")
        tab_layout = QHBoxLayout(tab_row)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(2)
        tab_group = QButtonGroup(self)
        tab_group.setExclusive(True)
        self.tab_buttons = {}
        for key, text in self.TABS:
            button = QPushButton(text)
            button.setObjectName("analysisDetailTab")
            button.setCheckable(True)
            button.setChecked(key == self.selected_tab)
            button.clicked.connect(
                lambda checked, tab_key=key: checked
                and self.tab_changed.emit(tab_key)
            )
            tab_group.addButton(button)
            self.tab_buttons[key] = button
            tab_layout.addWidget(button)
        tab_layout.addStretch()
        layout.addWidget(tab_row)

        if self.selected_tab == "raw":
            raw_title = QLabel("Whole-image R/S/U counts and fractions")
            raw_title.setObjectName("analysisDataTitle")
            layout.addWidget(raw_title)
            self.raw_table = self._build_whole_table()
            layout.addWidget(self.raw_table)
            return

        layout.addWidget(self._build_visual())
        layout.addLayout(self._build_metrics())

        note = QLabel(self._payload_note())
        note.setObjectName("analysisNote")
        note.setWordWrap(True)
        layout.addWidget(note)

        raw_title = QLabel(
            "Progressive Prefix — Raw Data"
            if self.selected_tab == "prefix"
            else "Whole Image — Raw Data"
        )
        raw_title.setObjectName("analysisDataTitle")
        layout.addWidget(raw_title)
        self.raw_table = self._build_table()
        layout.addWidget(self.raw_table)

    def _build_visual(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("analysisPlotPanel")
        layout = QVBoxLayout(panel)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)

        if self.selected_tab == "distribution":
            title_text = "Regular / Singular / Unusable"
            description = "Fractions for mask M and its negative mask −M"
        else:
            title_text = "Progressive Prefix • R − S"
            description = "Difference between Regular and Singular fractions"

        title = QLabel(title_text)
        title.setObjectName("analysisPlotTitle")
        subtitle = QLabel(description)
        subtitle.setObjectName("analysisPlotSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        if self.selected_tab == "distribution":
            self.chart = RSDistributionChart(
                self.report[self.selected_channel]["whole"]
            )
            layout.addWidget(self.chart)
            layout.addLayout(self._distribution_legend())
        else:
            prefix = self.report[self.selected_channel]["prefix"]
            labels = [f"{item.percent}%" for item in prefix]
            series = (
                (
                    "R−S (M)", "#4096F0",
                    [
                        None if item.rs.RM is None or item.rs.SM is None
                        else item.rs.RM - item.rs.SM
                        for item in prefix
                    ],
                ),
                (
                    "R−S (−M)", "#35BC79",
                    [
                        None
                        if item.rs.R_negM is None or item.rs.S_negM is None
                        else item.rs.R_negM - item.rs.S_negM
                        for item in prefix
                    ],
                ),
            )
            self.chart = PValueLineChart(series, labels, y_min=-1.0, y_max=1.0)
            layout.addWidget(self.chart)
            layout.addLayout(self._line_legend(series))
        return panel

    @staticmethod
    def _distribution_legend():
        series = tuple((name, color, ()) for name, color in RS_COLORS.items())
        return RSDetail._line_legend(series)

    @staticmethod
    def _line_legend(series):
        legend = QHBoxLayout()
        legend.setSpacing(12)
        legend.addStretch()
        for name, color, _values in series:
            marker = QLabel("●")
            marker.setStyleSheet(f"color: {color}; background: transparent;")
            label = QLabel(name)
            label.setObjectName("analysisLegendLabel")
            legend.addWidget(marker)
            legend.addWidget(label)
        return legend

    def _build_metrics(self):
        channel_result = self.report[self.selected_channel]
        whole = channel_result["whole"]
        payload = channel_result["payload"]
        metrics = QGridLayout()
        metrics.setHorizontalSpacing(7)
        metrics.setVerticalSpacing(7)
        values = (
            ("Estimated embed rate", format_percent(payload.embedding_rate), True),
            ("Estimated payload (bits)", format_integer(payload.estimated_payload_bits), False),
            ("Expected changes", format_integer(payload.expected_changed_samples), False),
            ("Group count", format_integer(whole.total_groups), False),
            ("Capacity samples", format_integer(payload.capacity_samples), False),
        )
        for column, values_item in enumerate(values):
            metrics.addWidget(MetricTile(*values_item), 0, column)
        return metrics

    def _payload_note(self) -> str:
        payload = self.report[self.selected_channel]["payload"]
        if payload.embedding_rate is None:
            message = "The RS equation could not produce a usable payload estimate."
        elif payload.estimated_payload_bits is None:
            message = (
                "The equation produced an out-of-range rate, so payload and "
                "changed-sample estimates are unavailable."
            )
        else:
            message = (
                "Estimated percentage of carrier samples used for random "
                "LSB replacement."
            )
        return message

    def _build_table(self) -> QTableWidget:
        if self.selected_tab == "prefix":
            return self._build_prefix_table()
        return self._build_whole_table()

    def _build_whole_table(self) -> QTableWidget:
        result = self.report[self.selected_channel]["whole"]
        rows = (
            ("M", "Regular", result.RM_count, result.RM),
            ("M", "Singular", result.SM_count, result.SM),
            ("M", "Unusable", result.UM_count, result.UM),
            ("−M", "Regular", result.R_negM_count, result.R_negM),
            ("−M", "Singular", result.S_negM_count, result.S_negM),
            ("−M", "Unusable", result.U_negM_count, result.U_negM),
        )
        table = self._make_table(len(rows), ("Mask", "Class", "Count", "Fraction"))
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for row, values in enumerate(rows):
            display = (
                values[0], values[1], format_integer(values[2]),
                format_number(values[3], 5),
            )
            self._set_row(table, row, display)
        table.setMinimumHeight(36 + len(rows) * 28)
        return table

    def _build_prefix_table(self) -> QTableWidget:
        prefix = self.report[self.selected_channel]["prefix"]
        headers = (
            "Prefix", "Pixels", "R(M)", "S(M)", "U(M)",
            "R(−M)", "S(−M)", "U(−M)", "Groups",
        )
        table = self._make_table(len(prefix), headers)
        table.horizontalHeader().setMinimumSectionSize(78)
        table.horizontalHeader().setStretchLastSection(True)
        for row, item in enumerate(prefix):
            result = item.rs
            values = (
                f"0–{item.percent}%",
                format_integer(item.pixel_count),
                format_number(result.RM, 5),
                format_number(result.SM, 5),
                format_number(result.UM, 5),
                format_number(result.R_negM, 5),
                format_number(result.S_negM, 5),
                format_number(result.U_negM, 5),
                format_integer(result.total_groups),
            )
            self._set_row(table, row, values)
        table.setMinimumHeight(36 + min(max(len(prefix), 3), 10) * 28)
        return table

    @staticmethod
    def _make_table(rows, headers):
        table = QTableWidget(rows, len(headers))
        table.setObjectName("analysisRawTable")
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        for column in range(len(headers)):
            table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        return table

    @staticmethod
    def _set_row(table, row, values):
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column > 1:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            table.setItem(row, column, item)
