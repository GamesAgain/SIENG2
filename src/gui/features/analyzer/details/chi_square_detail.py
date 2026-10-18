"""Chi-square result widgets for the Bit Statistics tab."""

from collections.abc import Mapping
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
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
)

from src.gui.features.analyzer.widgets.channel_selector import ChannelSelector


from .common import (
    MetricTile, PValueLineChart,
    channel_color, format_integer, format_number, format_p_value,
    format_percent,
)


from .chi_square_frames import ChiSquareFramesMixin


class ChiSquareDetail(ChiSquareFramesMixin, QFrame):
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
