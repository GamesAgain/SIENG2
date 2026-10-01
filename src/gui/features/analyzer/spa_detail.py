"""Sample Pair Analysis result widgets for the Bit Statistics tab."""

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.gui.features.analyzer.chi_square_detail import (
    ChannelSelector,
    MetricTile,
    format_integer,
    format_percent,
)


SPA_COLORS = {"X": "#B47AFA", "Y": "#38C681"}


class SPACountChart(QWidget):
    """Grouped X/Y counts labelled by their odd pixel differences."""

    def __init__(self, statistics, bin_count=31, parent=None):
        super().__init__(parent)
        self.statistics = statistics
        self.bin_count = max(1, min(bin_count, len(statistics.x_counts)))
        self.setFixedHeight(230)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = self.rect().adjusted(52, 14, -14, -34)
        if plot.width() <= 0 or plot.height() <= 0:
            return

        arrays = (
            self.statistics.x_counts[:self.bin_count],
            self.statistics.y_counts[:self.bin_count],
        )
        maximum = max((value for values in arrays for value in values), default=0)
        maximum = max(1, maximum)
        grid_pen = QPen(QColor("#39424A"), 1, Qt.PenStyle.DashLine)
        text_color = QColor("#8FA2B5")
        if self.statistics.pair_count == 0:
            painter.setPen(text_color)
            painter.drawText(
                plot, Qt.AlignmentFlag.AlignCenter, "N/A - no complete pairs"
            )
            return

        for step in range(5):
            ratio = step / 4
            y = plot.bottom() - ratio * plot.height()
            painter.setPen(grid_pen)
            painter.drawLine(plot.left(), int(y), plot.right(), int(y))
            painter.setPen(text_color)
            painter.drawText(2, int(y + 4), self._short_count(maximum * ratio))

        group_width = plot.width() / self.bin_count
        bar_width = max(1.0, group_width / 2 - 1.0)
        for series_index, (name, values) in enumerate(zip(SPA_COLORS, arrays)):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(SPA_COLORS[name]))
            for index, value in enumerate(values):
                height = value / maximum * plot.height()
                painter.drawRect(QRectF(
                    plot.left() + index * group_width + series_index * bar_width,
                    plot.bottom() - height,
                    bar_width,
                    height,
                ))

        painter.setPen(text_color)
        indexes = sorted({
            round(step * (self.bin_count - 1) / 8)
            for step in range(9)
        })
        for index in indexes:
            x = plot.left() + (index + 0.5) * group_width
            pixel_difference = 2 * index + 1
            painter.drawText(
                int(x - 16), plot.bottom() + 8, 32, 18,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                str(pixel_difference),
            )

    @staticmethod
    def _short_count(value) -> str:
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        if value >= 1_000:
            return f"{value / 1_000:.1f}K"
        return str(int(round(value)))


class SPADetail(QFrame):
    """SPA pair distribution, estimate and complete raw vectors."""

    channel_changed = pyqtSignal(str)
    tab_changed = pyqtSignal(str)

    TABS = (
        ("distribution", "Pair Distributions"),
        ("raw", "Raw Data"),
    )

    def __init__(
        self,
        report,
        selected_channel,
        parameters,
        selected_tab="distribution",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("analysisDetailPanel")
        self.setProperty("detectorType", "spa")
        self.report = report
        self.selected_channel = selected_channel
        self.parameters = parameters
        valid_tabs = {key for key, _text in self.TABS}
        self.selected_tab = (
            selected_tab if selected_tab in valid_tabs else "distribution"
        )
        self._setup_ui()

    @property
    def channel_result(self):
        return self.report[self.selected_channel]

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(14, 13, 14, 14)
        layout.setSpacing(11)

        header = QHBoxLayout()
        title = QLabel("Sample Pair Analysis")
        title.setObjectName("analysisPanelTitle")
        badge = QLabel("SPA")
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
        layout.addWidget(self._build_tabs())

        if self.selected_tab == "raw":
            raw_title = QLabel("Complete SPA Count Vectors")
            raw_title.setObjectName("analysisDataTitle")
            layout.addWidget(raw_title)
            self.raw_table = self._build_raw_table()
            layout.addWidget(self.raw_table)
            return

        layout.addWidget(self._build_visual())
        layout.addLayout(self._build_metrics())

        note = QLabel(self._estimate_note())
        note.setObjectName("analysisNote")
        note.setWordWrap(True)
        layout.addWidget(note)

        data_title = QLabel("Odd-difference Pair Counts")
        data_title.setObjectName("analysisDataTitle")
        layout.addWidget(data_title)
        self.raw_table = self._build_distribution_table()
        layout.addWidget(self.raw_table)

    def _build_tabs(self) -> QFrame:
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
        return tab_row

    def _build_visual(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("analysisPlotPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        panel_layout.setContentsMargins(12, 10, 12, 10)
        panel_layout.setSpacing(7)

        title = QLabel("X / Y Odd-difference Pair Counts")
        title.setObjectName("analysisPlotTitle")
        subtitle = QLabel(
            "Pair count by odd pixel difference (1, 3, 5, ...). "
            f"The SPA equation pools differences 1-{2 * self.parameters.spa_j + 1}."
        )
        subtitle.setObjectName("analysisPlotSubtitle")
        subtitle.setWordWrap(True)
        panel_layout.addWidget(title)
        panel_layout.addWidget(subtitle)

        self.chart = SPACountChart(
            self.channel_result["statistics"],
            bin_count=self.parameters.spa_j + 1,
        )
        panel_layout.addWidget(self.chart)
        panel_layout.addLayout(self._build_legend())
        return panel

    @staticmethod
    def _build_legend() -> QHBoxLayout:
        legend = QHBoxLayout()
        legend.setSpacing(12)
        legend.addStretch()
        labels = {
            "X": "X: even sample value > odd sample value",
            "Y": "Y: odd sample value > even sample value",
        }
        for name, color in SPA_COLORS.items():
            marker = QLabel("\u25cf")
            marker.setStyleSheet(f"color: {color}; background: transparent;")
            label = QLabel(labels[name])
            label.setObjectName("analysisLegendLabel")
            legend.addWidget(marker)
            legend.addWidget(label)
        return legend

    def _build_metrics(self) -> QGridLayout:
        statistics = self.channel_result["statistics"]
        estimate = self.channel_result["estimate"]
        displayed_rate = (
            estimate.embedding_rate if estimate.status == "estimated" else None
        )
        values = (
            ("Estimated embed rate", format_percent(displayed_rate), True),
            ("Estimated bits", format_integer(estimate.estimated_payload_bits), False),
            ("Expected changes", format_integer(estimate.expected_changed_samples), False),
            ("Pair count", format_integer(statistics.pair_count), False),
        )
        metrics = QGridLayout()
        metrics.setHorizontalSpacing(7)
        metrics.setVerticalSpacing(7)
        for column, item in enumerate(values):
            metrics.addWidget(MetricTile(*item), 0, column)
        return metrics

    def _estimate_note(self) -> str:
        estimate = self.channel_result["estimate"]
        if estimate.status == "estimated":
            return (
                "Estimated percentage of carrier samples used for random LSB "
                "replacement. Expected changes are modeled, not directly counted."
            )
        if estimate.status == "out_of_range":
            return "Estimate outside the physical 0-100% range."
        return f"Estimate unavailable: {estimate.reason or estimate.status}."

    def _build_distribution_table(self) -> QTableWidget:
        statistics = self.channel_result["statistics"]
        row_count = min(self.parameters.spa_j + 1, len(statistics.x_counts))
        table = self._make_table(
            row_count,
            ("Pixel difference", "X count", "Y count", "Y - X"),
        )
        for row in range(row_count):
            x_count = statistics.x_counts[row]
            y_count = statistics.y_counts[row]
            values = (
                str(2 * row + 1),
                format_integer(x_count),
                format_integer(y_count),
                format_integer(y_count - x_count),
            )
            self._set_row(table, row, values)
        table.setMinimumHeight(36 + min(max(row_count, 3), 10) * 28)
        return table

    def _build_raw_table(self) -> QTableWidget:
        statistics = self.channel_result["statistics"]
        table = self._make_table(
            256,
            ("Index", "C count", "D count", "X count", "Y count"),
        )
        header_tips = (
            "Raw vector index",
            "C[index]: pairs with upper-seven-bit difference equal to index",
            "D[index]: pairs with pixel difference equal to index",
            "X[index]: X trace for odd difference 2 * index + 1",
            "Y[index]: Y trace for odd difference 2 * index + 1",
        )
        for column, tooltip in enumerate(header_tips):
            table.horizontalHeaderItem(column).setToolTip(tooltip)

        arrays = (
            statistics.c_counts,
            statistics.d_counts,
            statistics.x_counts,
            statistics.y_counts,
        )
        for row in range(256):
            values = [str(row)]
            for counts in arrays:
                values.append(
                    format_integer(counts[row]) if row < len(counts) else "\u2014"
                )
            self._set_row(table, row, values)
            table.item(row, 0).setToolTip(f"Raw vector index {row}")
            if row < 128:
                odd_difference = 2 * row + 1
                table.item(row, 1).setToolTip(
                    f"C[{row}]: upper-seven-bit difference {row}"
                )
                table.item(row, 3).setToolTip(
                    f"X[{row}] = X{odd_difference}: odd pixel difference "
                    f"{odd_difference}"
                )
                table.item(row, 4).setToolTip(
                    f"Y[{row}] = Y{odd_difference}: odd pixel difference "
                    f"{odd_difference}"
                )
            table.item(row, 2).setToolTip(
                f"D[{row}]: pixel difference {row}"
            )
        table.setMinimumHeight(36 + 10 * 28)
        return table

    @staticmethod
    def _make_table(rows, headers) -> QTableWidget:
        table = QTableWidget(rows, len(headers))
        table.setObjectName("analysisRawTable")
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        for column in range(len(headers)):
            table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.Stretch
            )
        return table

    @staticmethod
    def _set_row(table, row, values) -> None:
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column > 0:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            table.setItem(row, column, item)
