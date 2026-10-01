"""Chi-square result widgets for the Bit Statistics tab."""

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
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


CHANNEL_COLORS = {
    "Whole": "#CBD5E1",
    "R": "#F87171",
    "G": "#34D399",
    "B": "#60A5FA",
    "L": "#CBD5E1",
}


def format_number(value, decimals=3) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"


def format_p_value(value) -> str:
    if value is None:
        return "N/A"
    if 0 < value < 0.000005:
        return "<0.00001"
    return f"{value:.5f}"


def format_integer(value) -> str:
    if value is None:
        return "N/A"
    return f"{int(round(value)):,}"


def format_percent(value) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


class ChannelSelector(QWidget):
    """Pill buttons for the channels returned by one detector."""

    channel_changed = pyqtSignal(str)

    def __init__(self, channels, selected_channel, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        label = QLabel("Channel:")
        label.setObjectName("analysisFilterLabel")
        layout.addWidget(label)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.buttons = {}
        for channel in channels:
            button = QPushButton(channel)
            button.setObjectName("analysisChannelButton")
            button.setCheckable(True)
            button.setChecked(channel == selected_channel)
            button.clicked.connect(
                lambda checked, name=channel: checked
                and self.channel_changed.emit(name)
            )
            self.button_group.addButton(button)
            self.buttons[channel] = button
            layout.addWidget(button)
        layout.addStretch()


class PValueLineChart(QWidget):
    """Small dependency-free line chart with a configurable y-axis."""

    def __init__(self, series, labels, y_min=0.0, y_max=1.0, parent=None):
        super().__init__(parent)
        self.series = series
        self.labels = labels
        self.y_min = y_min
        self.y_max = y_max
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
        for step in range(5):
            ratio = step / 4
            value = self.y_min + ratio * (self.y_max - self.y_min)
            y = plot.bottom() - ratio * plot.height()
            painter.setPen(grid_pen)
            painter.drawLine(plot.left(), int(y), plot.right(), int(y))
            painter.setPen(text_color)
            painter.drawText(4, int(y + 4), f"{value:.2f}")

        painter.setPen(QPen(QColor("#57616C"), 1))
        painter.drawLine(plot.bottomLeft(), plot.bottomRight())
        painter.drawLine(plot.topLeft(), plot.bottomLeft())

        point_count = max((len(values) for _, _, values in self.series), default=0)
        if not any(value is not None for _, _, values in self.series for value in values):
            painter.setPen(text_color)
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "N/A - insufficient data")
            return

        x_step = plot.width() / max(1, point_count - 1)
        for _name, color, values in self.series:
            pen = QPen(QColor(color), 2)
            painter.setPen(pen)
            previous = None
            for index, value in enumerate(values):
                if value is None:
                    previous = None
                    continue
                clamped = min(self.y_max, max(self.y_min, float(value)))
                ratio = (clamped - self.y_min) / (self.y_max - self.y_min)
                point = QPointF(
                    plot.left() + index * x_step,
                    plot.bottom() - ratio * plot.height(),
                )
                if previous is not None:
                    painter.drawLine(previous, point)
                painter.setBrush(QColor(color))
                painter.drawEllipse(point, 2.8, 2.8)
                previous = point

        if self.labels:
            label_indexes = sorted({
                round(index * (len(self.labels) - 1) / min(5, len(self.labels) - 1))
                for index in range(min(5, len(self.labels) - 1) + 1)
            }) if len(self.labels) > 1 else [0]
            painter.setPen(text_color)
            for index in label_indexes:
                x = plot.left() + index * x_step
                painter.drawText(
                    int(x - 28), plot.bottom() + 8, 56, 20,
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    str(self.labels[index]),
                )


class MetricTile(QFrame):
    """Compact label/value pair used below detector charts."""

    def __init__(self, label, value, accent=False, parent=None):
        super().__init__(parent)
        self.setObjectName("analysisMetricTile")
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)
        name_label = QLabel(label)
        name_label.setObjectName("analysisMetricLabel")
        value_label = QLabel(value)
        value_label.setObjectName("analysisMetricValue")
        value_label.setProperty("accent", accent)
        layout.addWidget(name_label)
        layout.addWidget(value_label)


class ChiSquareDetail(QFrame):
    """Full Chi-square view with channels, charts, metrics and raw rows."""

    channel_changed = pyqtSignal(str)
    tab_changed = pyqtSignal(str)

    TABS = (
        ("prefix", "Progressive Prefix"),
        ("segments", "Sliding Segments"),
        ("raw", "Raw Data"),
    )

    def __init__(self, report, selected_channel, selected_tab="prefix", parent=None):
        super().__init__(parent)
        self.setObjectName("analysisDetailPanel")
        self.report = report
        self.selected_channel = selected_channel
        valid_tabs = {key for key, _text in self.TABS}
        self.selected_tab = selected_tab if selected_tab in valid_tabs else "prefix"
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(14, 13, 14, 14)
        layout.setSpacing(11)

        header = QHBoxLayout()
        title = QLabel("Chi-square Analysis")
        title.setObjectName("analysisPanelTitle")
        badge = QLabel("PoV")
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
        self.tab_buttons = {}
        tab_group = QButtonGroup(self)
        tab_group.setExclusive(True)
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

        if self.selected_tab != "raw":
            layout.addWidget(self._build_visual())
            layout.addWidget(self._build_whole_metrics())
            scope_text = (
                "Metrics and table use pooled Whole; the chart overlays every "
                "available channel. "
                if self.selected_channel == "Whole" else
                f"Chart, metrics and table channel: {self.selected_channel}. "
            )
            note = QLabel(
                scope_text + "High p-values indicate PoV equality, not the probability of hidden data. "
                "N/A means insufficient valid pairs."
            )
            note.setObjectName("analysisNote")
            note.setWordWrap(True)
            layout.addWidget(note)

        raw_title = QLabel(self._raw_title())
        raw_title.setObjectName("analysisDataTitle")
        layout.addWidget(raw_title)
        self.raw_table = self._build_table()
        layout.addWidget(self.raw_table)

    def _build_visual(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("analysisPlotPanel")
        layout = QVBoxLayout(panel)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)

        titles = {
            "prefix": (
                "Progressive Prefix",
                "Cumulative p-value across raster-order image prefixes",
            ),
            "segments": (
                "Sliding Segments",
                "Fixed-length raster-order ranges; values are not cumulative",
            ),
        }
        title_text, description = titles[self.selected_tab]
        title = QLabel(title_text)
        title.setObjectName("analysisPlotTitle")
        subtitle = QLabel(description)
        subtitle.setObjectName("analysisPlotSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        series, labels = self._chart_data()
        self.chart = PValueLineChart(series, labels)
        layout.addWidget(self.chart)
        layout.addLayout(self._build_legend(series))
        return panel

    def _chart_data(self):
        channels = list(self.report) if self.selected_channel == "Whole" else [self.selected_channel]
        if self.selected_tab == "prefix":
            selected_prefix = self.report[self.selected_channel]["prefix"]
            labels = [f"{item.percent}%" for item in selected_prefix]
            series = []
            for channel in channels:
                channel_result = self.report[channel]
                values = [item.chi_square.p_value for item in channel_result["prefix"]]
                color = CHANNEL_COLORS.get(channel, "#38BDF8")
                series.append((channel, color, values))
            return series, labels

        segments = self.report[self.selected_channel]["segments"]
        total_pixels = max((item.end for item in segments), default=1)
        labels = [f"{round(item.start / total_pixels * 100)}%" for item in segments]
        return [(
            channel, CHANNEL_COLORS.get(channel, "#38BDF8"),
            [item.chi_square.p_value for item in self.report[channel]["segments"]],
        ) for channel in channels], labels

    @staticmethod
    def _build_legend(series):
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

    def _build_whole_metrics(self) -> QFrame:
        section = QFrame()
        section.setObjectName("analysisWholeMetrics")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        header = QHBoxLayout()
        title = QLabel("Whole Image Metrics")
        title.setObjectName("analysisWholeMetricsTitle")
        scope = QLabel(f"Channel: {self.selected_channel} · Scope: 0–100%")
        scope.setObjectName("analysisWholeMetricsScope")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(scope)
        layout.addLayout(header)

        result = self.report[self.selected_channel]["whole"]
        metrics = QGridLayout()
        metrics.setHorizontalSpacing(7)
        metrics.setVerticalSpacing(7)
        values = (
            ("Chi-square", format_number(result.chi_square_total), False),
            ("p-value", format_p_value(result.p_value), True),
            ("Degrees of freedom", format_integer(result.dof), False),
            ("Sample count", format_integer(result.sample_count), False),
            ("Valid pairs", format_integer(result.valid_pairs), False),
        )
        for column, (label, value, accent) in enumerate(values):
            metrics.addWidget(MetricTile(label, value, accent), 0, column)
        layout.addLayout(metrics)
        return section

    def _records(self):
        channel_result = self.report[self.selected_channel]
        if self.selected_tab == "prefix":
            return [
                (f"0–{item.percent}%", item.chi_square)
                for item in channel_result["prefix"]
            ]
        if self.selected_tab == "segments":
            return [
                (f"[{item.start:,}:{item.end:,})", item.chi_square)
                for item in channel_result["segments"]
            ]
        return [
            ("Whole Image", channel_result["whole"]),
            *[
                (f"Prefix 0–{item.percent}%", item.chi_square)
                for item in channel_result["prefix"]
            ],
            *[
                (f"Segment [{item.start:,}:{item.end:,})", item.chi_square)
                for item in channel_result["segments"]
            ],
        ]

    def _build_table(self) -> QTableWidget:
        records = self._records()
        table = QTableWidget(len(records), 6)
        table.setObjectName("analysisRawTable")
        table.setHorizontalHeaderLabels((
            "Scope", "Chi-square", "p-value", "dof", "Samples", "Valid pairs"
        ))
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 6):
            table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )

        for row, (scope, result) in enumerate(records):
            values = (
                scope,
                format_number(result.chi_square_total),
                format_p_value(result.p_value),
                format_integer(result.dof),
                format_integer(result.sample_count),
                format_integer(result.valid_pairs),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 2:
                    item.setToolTip(f"Raw p-value: {result.p_value!r}")
                if column > 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                table.setItem(row, column, item)

        visible_rows = min(max(len(records), 3), 10)
        table.setMinimumHeight(36 + visible_rows * 28)
        return table

    def _raw_title(self) -> str:
        labels = {
            "prefix": "Progressive Prefix Data",
            "segments": "Sliding Segments Data",
            "raw": "Whole, Prefix, Segments Data",
        }
        return labels[self.selected_tab]
