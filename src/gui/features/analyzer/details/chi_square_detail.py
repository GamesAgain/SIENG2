"""Chi-square result widgets for the Bit Statistics tab."""

from collections.abc import Mapping
from typing import Any

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
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

from src.gui.features.analyzer.widgets.channel_selector import ChannelSelector
from src.gui.features.analyzer.widgets.avi_frame_selector import (
    AVIFrameSelector,
)


CHANNEL_COLORS = {
    "Whole": "#CBD5E1",
    "R": "#F87171",
    "G": "#34D399",
    "B": "#60A5FA",
    "L": "#CBD5E1",
}
AUDIO_CHANNEL_COLORS = (
    "#38BDF8",
    "#F59E0B",
    "#A78BFA",
    "#2DD4BF",
    "#FB7185",
    "#84CC16",
)


def format_number(value: float | None, decimals: int = 3) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"


def format_p_value(value: float | None) -> str:
    if value is None:
        return "N/A"
    if 0 < value < 0.000005:
        return "<0.00001"
    return f"{value:.5f}"


def format_integer(value: float | int | None) -> str:
    if value is None:
        return "N/A"
    return f"{int(round(value)):,}"


def format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def channel_color(channel: str) -> str:
    """Return the reference colors plus stable colors for WAV channels."""
    if channel in CHANNEL_COLORS:
        return CHANNEL_COLORS[channel]
    if channel.startswith("CH") and channel[2:].isdigit():
        index = max(0, int(channel[2:]) - 1)
        return AUDIO_CHANNEL_COLORS[index % len(AUDIO_CHANNEL_COLORS)]
    return "#38BDF8"


class PValueLineChart(QWidget):
    """Small dependency-free line chart with a configurable y-axis."""

    def __init__(
        self,
        series,
        labels,
        y_min: float = 0.0,
        y_max: float = 1.0,
        parent=None,
    ):
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

        point_count = max(
            (len(values) for _, _, values in self.series),
            default=0,
        )
        if not any(
            value is not None
            for _, _, values in self.series
            for value in values
        ):
            painter.setPen(text_color)
            painter.drawText(
                plot,
                Qt.AlignmentFlag.AlignCenter,
                "N/A - insufficient data",
            )
            return

        x_step = plot.width() / max(1, point_count - 1)
        for _name, color, values in self.series:
            painter.setPen(QPen(QColor(color), 2))
            previous = None
            for index, value in enumerate(values):
                if value is None:
                    previous = None
                    continue
                clamped = min(self.y_max, max(self.y_min, float(value)))
                ratio = (clamped - self.y_min) / (
                    self.y_max - self.y_min
                )
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
            if len(self.labels) > 1:
                label_indexes = sorted({
                    round(
                        index * (len(self.labels) - 1)
                        / min(5, len(self.labels) - 1)
                    )
                    for index in range(
                        min(5, len(self.labels) - 1) + 1
                    )
                })
            else:
                label_indexes = [0]

            painter.setPen(text_color)
            for index in label_indexes:
                x = plot.left() + index * x_step
                painter.drawText(
                    int(x - 34),
                    plot.bottom() + 8,
                    68,
                    20,
                    Qt.AlignmentFlag.AlignHCenter
                    | Qt.AlignmentFlag.AlignTop,
                    str(self.labels[index]),
                )


class MetricTile(QFrame):
    """Compact label/value pair used below detector charts."""

    def __init__(
        self,
        label: str,
        value: str,
        accent: bool = False,
        parent=None,
    ):
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
        self.value_label = value_label
        layout.addWidget(name_label)
        layout.addWidget(value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class ChiSquareDetail(QFrame):
    """Full Chi-square view with channels, charts, metrics and raw rows."""

    channel_changed = pyqtSignal(str)
    tab_changed = pyqtSignal(str)
    frame_changed = pyqtSignal(int)
    frame_detail_requested = pyqtSignal(int)
    frame_view_tab_changed = pyqtSignal(str)

    TABS = (
        ("prefix", "Progressive Prefix"),
        ("segments", "Sliding Segments"),
        ("raw", "Raw Data"),
    )

    def __init__(
        self,
        report: Mapping[str, Any],
        selected_channel: str,
        file_format: str,
        selected_tab: str = "prefix",
        frames=(),
        selected_frame: int | None = None,
        frame_details=None,
        frame_detail_loading=None,
        frame_detail_errors=None,
        parent=None,
        video_scope: str | None = None,
        video_frame_tab: str = "timeline",
    ):
        super().__init__(parent)
        if selected_channel not in report:
            raise ValueError("selected_channel must exist in report.")

        self.setObjectName("analysisDetailPanel")
        self.report = report
        self.selected_channel = selected_channel
        self.file_format = file_format.upper()
        self.video_scope = video_scope
        self.video_frame_tab = video_frame_tab
        self.frames = tuple(frames)
        self.selected_frame = selected_frame
        self.frame_details = frame_details if frame_details is not None else {}
        self.frame_detail_loading = (
            frame_detail_loading
            if frame_detail_loading is not None
            else set()
        )
        self.frame_detail_errors = (
            frame_detail_errors
            if frame_detail_errors is not None
            else {}
        )
        self.tabs = list(self.TABS)
        if video_scope == "frame":
            self.tabs = [("frames", "Per-frame Trend")]
        elif self.frames:
            self.tabs.insert(-1, ("frames", "Frames"))
        valid_tabs = {key for key, _text in self.tabs}
        self.selected_tab = (
            selected_tab if selected_tab in valid_tabs else "prefix"
        )
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

        self.channel_selector = ChannelSelector(self)
        self.channel_selector.set_channels(
            self.report,
            self.selected_channel,
        )
        self.channel_selector.channel_changed.connect(
            self.channel_changed.emit
        )
        layout.addWidget(self.channel_selector)

        tab_row = QFrame()
        tab_row.setObjectName("analysisDetailTabs")
        tab_layout = QHBoxLayout(tab_row)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(2)

        self.tab_buttons = {}
        tab_group = QButtonGroup(self)
        tab_group.setExclusive(True)
        for key, text in self.tabs:
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
        if self.video_scope != "frame":
            layout.addWidget(tab_row)

        if self.selected_tab == "frames":
            self._build_frames_view(layout)
            return

        if self.selected_tab != "raw":
            layout.addWidget(self._build_visual())
            layout.addWidget(self._build_whole_metrics())

        raw_title = QLabel(self._raw_title())
        raw_title.setObjectName("analysisDataTitle")
        layout.addWidget(raw_title)
        self.raw_table = self._build_table()
        layout.addWidget(self.raw_table)

    def _selected_frame_result(self):
        for frame in self.frames:
            if frame.frame_index == self.selected_frame:
                return frame
        return self.frames[0]

    def _build_frames_view(self, layout: QVBoxLayout) -> None:
        selected = self._selected_frame_result()
        self.frame_selector = AVIFrameSelector(
            self.frames,
            selected.frame_index,
            self,
        )
        self.frame_selector.frame_changed.connect(self._request_frame)
        layout.addWidget(self.frame_selector)
        if self.video_scope == "frame":
            layout.addWidget(self._build_avi_frame_tabs())
            if self.video_frame_tab != "timeline":
                self.frame_detail_container = QFrame()
                self.frame_detail_layout = QVBoxLayout(self.frame_detail_container)
                self.frame_detail_layout.setContentsMargins(0, 0, 0, 0)
                layout.addWidget(self.frame_detail_container)
                self._render_frame_detail_section()
                return

        panel = QFrame()
        panel.setObjectName("analysisPlotPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 10, 12, 10)
        panel_layout.setSpacing(4)
        title = QLabel("Frame Timeline • p-value")
        title.setObjectName("analysisPlotTitle")
        subtitle = QLabel(
            "One Chi-square result per decoded frame; high p-values "
            "indicate PoV equality, not detection probability."
        )
        subtitle.setObjectName("analysisPlotSubtitle")
        subtitle.setWordWrap(True)
        panel_layout.addWidget(title)
        panel_layout.addWidget(subtitle)

        channels = (
            tuple(selected.channels)
            if self.selected_channel == "Whole"
            else (self.selected_channel,)
        )
        series = tuple(
            (
                ChannelSelector.display_name(channel),
                channel_color(channel),
                [
                    frame.channels[channel].p_value
                    for frame in self.frames
                    if channel in frame.channels
                ],
            )
            for channel in channels
        )
        labels = [
            self._format_seconds(frame.timestamp_seconds)
            for frame in self.frames
        ]
        panel_layout.addWidget(PValueLineChart(
            series,
            labels,
            parent=panel,
        ))
        panel_layout.addLayout(self._build_legend(series))
        layout.addWidget(panel)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(7)
        metrics.setVerticalSpacing(7)
        self.frame_metric_tiles = []
        for column, item in enumerate(self._frame_metric_values(selected)):
            tile = MetricTile(*item)
            self.frame_metric_tiles.append(tile)
            metrics.addWidget(tile, 0, column)
        layout.addLayout(metrics)

        if self.video_scope != "frame":
            self.frame_detail_container = QFrame()
            self.frame_detail_container.setObjectName(
                "analysisFrameDetailContainer"
            )
            self.frame_detail_layout = QVBoxLayout(
                self.frame_detail_container
            )
            self.frame_detail_layout.setContentsMargins(0, 0, 0, 0)
            self.frame_detail_layout.setSpacing(0)
            layout.addWidget(self.frame_detail_container)
            self._render_frame_detail_section()

        table_title = QLabel("Per-frame Chi-square Data")
        table_title.setObjectName("analysisDataTitle")
        layout.addWidget(table_title)
        self.frame_table = self._build_frames_table()
        layout.addWidget(self.frame_table)

    def _build_avi_frame_tabs(self) -> QFrame:
        row = QFrame()
        row.setObjectName("analysisDetailTabs")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        group = QButtonGroup(row)
        group.setExclusive(True)
        for key, text in (*self.TABS, ("timeline", "Per-frame Trend")):
            button = QPushButton(text)
            button.setObjectName("analysisDetailTab")
            button.setCheckable(True)
            button.setChecked(key == self.video_frame_tab)
            button.clicked.connect(
                lambda checked, value=key: checked and self.frame_view_tab_changed.emit(value)
            )
            group.addButton(button)
            layout.addWidget(button)
        layout.addStretch()
        return row

    def _frame_metric_values(self, frame):
        result = frame.channels[self.selected_channel]
        return (
            ("Frame", format_integer(frame.frame_index), False),
            ("Timestamp", f"{frame.timestamp_seconds:.3f} s", False),
            ("Chi-square", format_number(result.chi_square_total), False),
            ("p-value", format_p_value(result.p_value), True),
            ("Valid pairs", format_integer(result.valid_pairs), False),
        )

    def _request_frame(self, frame_index: int) -> None:
        self.set_selected_frame(frame_index)
        self.frame_changed.emit(frame_index)

    def set_selected_frame(self, frame_index: int) -> None:
        """Update the selected-frame widgets without rebuilding the page."""
        frame = next(
            (
                item
                for item in self.frames
                if item.frame_index == frame_index
            ),
            None,
        )
        if frame is None:
            return
        self.selected_frame = frame_index
        if not hasattr(self, "frame_selector"):
            return
        self.frame_selector.set_selected_frame(frame_index)
        if self.video_scope == "frame" and self.video_frame_tab != "timeline":
            self._render_frame_detail_section()
            return
        for tile, (_label, value, _accent) in zip(
            self.frame_metric_tiles,
            self._frame_metric_values(frame),
        ):
            tile.set_value(value)
        self.frame_table.selectRow(self._frame_row(frame_index))
        self._render_frame_detail_section()

    def set_frame_detail_state(
        self,
        loading: bool,
        error: str | None,
    ) -> None:
        self._render_frame_detail_section()

    def set_frame_detail_result(self, result) -> None:
        self.frame_details[result.frame_index] = result
        self._render_frame_detail_section()

    def _render_frame_detail_section(self) -> None:
        if not hasattr(self, "frame_detail_layout"):
            return
        while self.frame_detail_layout.count():
            item = self.frame_detail_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

        content = QFrame()
        content.setObjectName("analysisFrameDetailPanel")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 11, 12, 12)
        layout.setSpacing(9)
        self.frame_detail_layout.addWidget(content)

        frame_index = self.selected_frame
        detail = self.frame_details.get(frame_index)
        key = ("chi_square", frame_index)
        loading = key in self.frame_detail_loading
        error = self.frame_detail_errors.get(key)

        header = QHBoxLayout()
        title = QLabel(f"Frame {frame_index} Spatial Detail")
        title.setObjectName("analysisDataTitle")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        if detail is None:
            message = QLabel(
                error
                or (
                    "Run an on-demand spatial analysis to inspect "
                    "prefixes and segments inside this frame."
                )
            )
            message.setObjectName(
                "analysisError" if error else "analysisNote"
            )
            message.setWordWrap(True)
            layout.addWidget(message)
            button = QPushButton(
                "Analyzing frame..."
                if loading
                else "Analyze selected frame"
            )
            button.setObjectName("SecondaryBtn")
            button.setEnabled(not loading)
            button.clicked.connect(
                lambda: self.frame_detail_requested.emit(frame_index)
            )
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
            return

        selected_series = detail.channels[self.selected_channel]
        channels = (
            tuple(detail.channels)
            if self.selected_channel == "Whole"
            else (self.selected_channel,)
        )
        if self.video_frame_tab in ("prefix", "timeline"):
            layout.addWidget(self._build_spatial_chart(
                "Progressive Prefix Inside Selected Frame",
                "Cumulative p-value in raster order within this frame.",
                tuple(
                    (
                        ChannelSelector.display_name(channel),
                        channel_color(channel),
                        [item.analysis.p_value for item in detail.channels[channel].prefix],
                    )
                    for channel in channels
                ),
                [f"{item.percent}%" for item in selected_series.prefix],
            ))
        if self.video_frame_tab in ("segments", "timeline"):
            layout.addWidget(self._build_spatial_chart(
                "Sliding Segments Inside Selected Frame",
                "Local non-cumulative p-values in raster order.",
                tuple(
                    (
                        ChannelSelector.display_name(channel),
                        channel_color(channel),
                        [item.analysis.p_value for item in detail.channels[channel].segments],
                    )
                    for channel in channels
                ),
                self._spatial_segment_labels(selected_series.segments),
            ))
        layout.addWidget(self._build_spatial_table(selected_series))

    def _build_spatial_chart(
        self,
        title_text: str,
        description: str,
        series,
        labels,
    ) -> QFrame:
        panel = QFrame()
        panel.setObjectName("analysisPlotPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        title = QLabel(title_text)
        title.setObjectName("analysisPlotTitle")
        subtitle = QLabel(description)
        subtitle.setObjectName("analysisPlotSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(PValueLineChart(series, labels, parent=panel))
        layout.addLayout(self._build_legend(series))
        return panel

    @staticmethod
    def _spatial_segment_labels(segments) -> list[str]:
        total = max((item.end for item in segments), default=1)
        return [
            f"{round(item.start / total * 100)}%"
            for item in segments
        ]

    def _build_spatial_table(self, series) -> QTableWidget:
        rows = []
        if self.video_scope == "frame" and self.video_frame_tab == "raw":
            rows.append(("Whole Frame", "All pixels", series.whole))
        if self.video_frame_tab in ("prefix", "raw", "timeline"):
            rows.extend(
                ("Prefix", f"0–{item.percent}%", item.analysis)
                for item in series.prefix
            )
        if self.video_frame_tab in ("segments", "raw", "timeline"):
            rows.extend(
                ("Segment", f"{item.start:,}–{item.end:,}", item.analysis)
                for item in series.segments
            )
        table = QTableWidget(len(rows), 7)
        table.setObjectName("analysisRawTable")
        table.setHorizontalHeaderLabels((
            "Type",
            "Range",
            "Chi-square",
            "p-value",
            "dof",
            "Samples",
            "Valid pairs",
        ))
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setStretchLastSection(True)
        for row, (kind, scope, result) in enumerate(rows):
            values = (
                kind,
                scope,
                format_number(result.chi_square_total),
                format_p_value(result.p_value),
                format_integer(result.dof),
                format_integer(result.sample_count),
                format_integer(result.valid_pairs),
            )
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        table.setMinimumHeight(36 + min(max(len(rows), 3), 10) * 28)
        return table

    def _frame_row(self, frame_index: int) -> int:
        return next(
            (
                row
                for row, frame in enumerate(self.frames)
                if frame.frame_index == frame_index
            ),
            0,
        )

    def _build_frames_table(self) -> QTableWidget:
        table = QTableWidget(len(self.frames), 7)
        table.setObjectName("analysisRawTable")
        table.setHorizontalHeaderLabels((
            "Frame",
            "Time",
            "Chi-square",
            "p-value",
            "dof",
            "Samples",
            "Valid pairs",
        ))
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setStretchLastSection(True)

        selected_row = 0
        for row, frame in enumerate(self.frames):
            result = frame.channels[self.selected_channel]
            values = (
                format_integer(frame.frame_index),
                f"{frame.timestamp_seconds:.3f} s",
                format_number(result.chi_square_total),
                format_p_value(result.p_value),
                format_integer(result.dof),
                format_integer(result.sample_count),
                format_integer(result.valid_pairs),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column > 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter
                    )
                table.setItem(row, column, item)
            if frame.frame_index == self.selected_frame:
                selected_row = row
        table.selectRow(selected_row)
        table.cellClicked.connect(
            lambda row, _column: self._request_frame(
                self.frames[row].frame_index
            )
        )
        table.setMinimumHeight(
            36 + min(max(len(self.frames), 3), 10) * 28
        )
        return table

    def _build_visual(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("analysisPlotPanel")
        layout = QVBoxLayout(panel)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)

        title_text = (
            "Progressive Prefix"
            if self.selected_tab == "prefix"
            else "Sliding Segments"
        )
        title = QLabel(title_text)
        title.setObjectName("analysisPlotTitle")
        subtitle = QLabel(self._plot_description())
        subtitle.setObjectName("analysisPlotSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        series, labels = self._chart_data()
        self.chart = PValueLineChart(series, labels)
        layout.addWidget(self.chart)
        layout.addLayout(self._build_legend(series))
        return panel

    def _plot_description(self) -> str:
        if self.file_format == "PNG":
            if self.selected_tab == "prefix":
                return (
                    "Cumulative p-value across raster-order image prefixes"
                )
            return (
                "Fixed-length raster-order ranges; values are not cumulative"
            )

        medium = "audio" if self.file_format == "WAV" else "video"
        if self.selected_tab == "prefix":
            return f"Cumulative p-value across the {medium} timeline"
        return (
            f"Fixed-length {medium} time ranges; values are not cumulative"
        )

    def _chart_data(self):
        channels = (
            list(self.report)
            if self.selected_channel == "Whole"
            else [self.selected_channel]
        )
        selected_series = self.report[self.selected_channel]

        if self.selected_tab == "prefix":
            labels = [f"{item.percent}%" for item in selected_series.prefix]
            return [
                (
                    ChannelSelector.display_name(channel),
                    channel_color(channel),
                    [
                        item.analysis.p_value
                        for item in self.report[channel].prefix
                    ],
                )
                for channel in channels
            ], labels

        segments = selected_series.segments
        if self.file_format == "PNG":
            total = max((item.end for item in segments), default=1)
            labels = [
                f"{round(item.start / total * 100)}%"
                for item in segments
            ]
        else:
            labels = [
                self._format_seconds(item.start_seconds)
                for item in segments
            ]

        return [
            (
                ChannelSelector.display_name(channel),
                channel_color(channel),
                [
                    item.analysis.p_value
                    for item in self.report[channel].segments
                ],
            )
            for channel in channels
        ], labels

    @staticmethod
    def _build_legend(series) -> QHBoxLayout:
        legend = QHBoxLayout()
        legend.setSpacing(12)
        legend.addStretch()
        for name, color, _values in series:
            marker = QLabel("●")
            marker.setStyleSheet(
                f"color: {color}; background: transparent;"
            )
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
        title = QLabel(self._whole_title())
        title.setObjectName("analysisWholeMetricsTitle")
        selected_label = ChannelSelector.display_name(
            self.selected_channel
        )
        scope = QLabel(
            f"Channel: {selected_label} · Scope: 0–100%"
        )
        scope.setObjectName("analysisWholeMetricsScope")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(scope)
        layout.addLayout(header)

        result = self.report[self.selected_channel].whole
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
        for column, values_item in enumerate(values):
            metrics.addWidget(MetricTile(*values_item), 0, column)
        layout.addLayout(metrics)
        return section

    def _whole_title(self) -> str:
        return {
            "PNG": "Whole Image Metrics",
            "WAV": "Entire Audio Metrics",
            "AVI": "Entire Video Metrics",
        }.get(self.file_format, "Entire File Metrics")

    def _whole_scope_name(self) -> str:
        return {
            "PNG": "Whole Image",
            "WAV": "Entire Audio",
            "AVI": "Entire Video",
        }.get(self.file_format, "Entire File")

    def _records(self):
        channel_result = self.report[self.selected_channel]
        if self.selected_tab == "prefix":
            return [
                (self._prefix_scope(item), item.analysis)
                for item in channel_result.prefix
            ]
        if self.selected_tab == "segments":
            return [
                (self._segment_scope(item), item.analysis)
                for item in channel_result.segments
            ]
        return [
            (self._whole_scope_name(), channel_result.whole),
            *[
                (
                    f"Prefix {self._prefix_scope(item)}",
                    item.analysis,
                )
                for item in channel_result.prefix
            ],
            *[
                (
                    f"Segment {self._segment_scope(item)}",
                    item.analysis,
                )
                for item in channel_result.segments
            ],
        ]

    def _prefix_scope(self, item) -> str:
        if self.file_format == "PNG":
            return f"0–{item.percent}%"
        return (
            f"0–{self._format_seconds(item.end_seconds)} "
            f"({item.percent}%)"
        )

    def _segment_scope(self, item) -> str:
        if self.file_format == "PNG":
            return f"[{item.start:,}:{item.end:,})"
        return (
            f"{self._format_seconds(item.start_seconds)}–"
            f"{self._format_seconds(item.end_seconds)} "
            f"[frames {item.start_frame:,}:{item.end_frame:,})"
        )

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        if seconds >= 10:
            return f"{seconds:.1f}s"
        return f"{seconds:.2f}s"

    def _build_table(self) -> QTableWidget:
        records = self._records()
        table = QTableWidget(len(records), 6)
        table.setObjectName("analysisRawTable")
        table.setHorizontalHeaderLabels((
            "Scope",
            "Chi-square",
            "p-value",
            "dof",
            "Samples",
            "Valid pairs",
        ))
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        for column in range(1, 6):
            table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
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
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter
                    )
                table.setItem(row, column, item)

        visible_rows = min(max(len(records), 3), 10)
        table.setMinimumHeight(36 + visible_rows * 28)
        return table

    def _raw_title(self) -> str:
        return {
            "prefix": "Progressive Prefix Data",
            "segments": "Sliding Segments Data",
            "raw": "Whole, Prefix, Segments Data",
        }[self.selected_tab]
