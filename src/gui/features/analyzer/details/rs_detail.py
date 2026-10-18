"""RS Analysis result widgets for the Bit Statistics tab."""

from collections.abc import Mapping
from typing import Any

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

from src.gui.features.analyzer.details.chi_square_detail import (
    MetricTile,
    PValueLineChart,
    format_integer,
    format_number,
    format_percent,
)
from src.gui.features.analyzer.widgets.channel_selector import ChannelSelector
from src.gui.features.analyzer.widgets.avi_frame_selector import (
    AVIFrameSelector,
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
            painter.drawText(
                plot,
                Qt.AlignmentFlag.AlignCenter,
                "N/A - no complete groups",
            )
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
            (
                "−M",
                (
                    self.result.R_negM,
                    self.result.S_negM,
                    self.result.U_negM,
                ),
            ),
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
                fraction = (
                    0.0 if value is None else min(1.0, max(0.0, value))
                )
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
                int(center - 30),
                plot.bottom() + 8,
                60,
                20,
                Qt.AlignmentFlag.AlignHCenter
                | Qt.AlignmentFlag.AlignTop,
                name,
            )


class RSDetail(QFrame):
    """RS distribution, prefix trend, estimate and raw tables."""

    channel_changed = pyqtSignal(str)
    tab_changed = pyqtSignal(str)
    frame_changed = pyqtSignal(int)
    frame_detail_requested = pyqtSignal(int)
    frame_view_tab_changed = pyqtSignal(str)

    TABS = (
        ("distribution", "Distribution"),
        ("prefix", "Progressive Prefix"),
        ("raw", "Raw Data"),
    )

    def __init__(
        self,
        report: Mapping[str, Any],
        selected_channel: str,
        selected_tab: str = "distribution",
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
        self.setProperty("detectorType", "rs")
        self.report = report
        self.video_scope = video_scope
        self.video_frame_tab = video_frame_tab
        self.selected_channel = selected_channel
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
        elif video_scope == "whole":
            self.tabs.insert(-1, ("segments", "Sliding Segments"))
        elif self.frames:
            self.tabs.insert(-1, ("frames", "Frames"))
        valid_tabs = {key for key, _text in self.tabs}
        self.selected_tab = (
            selected_tab if selected_tab in valid_tabs else "distribution"
        )
        self._setup_ui()

    @property
    def channel_series(self):
        return self.report[self.selected_channel]

    @property
    def whole_measurement(self):
        return self.channel_series.whole

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

        self.channel_selector = ChannelSelector(self)
        self.channel_selector.set_channels(
            self.report,
            self.selected_channel,
        )
        self.channel_selector.channel_changed.connect(
            self.channel_changed.emit
        )
        layout.addWidget(self.channel_selector)
        if self.video_scope != "frame":
            layout.addWidget(self._build_tabs())

        if self.selected_tab == "frames":
            self._build_frames_view(layout)
            return

        if self.selected_tab == "raw":
            title = QLabel("Whole-file R/S/U Counts and Fractions")
            title.setObjectName("analysisDataTitle")
            layout.addWidget(title)
            layout.addWidget(self._build_whole_table())
            if self.video_scope == "whole":
                for tab, heading in (("prefix", "Progressive Prefix"),
                                     ("segments", "Sliding Segments")):
                    range_title = QLabel(heading)
                    range_title.setObjectName("analysisDataTitle")
                    layout.addWidget(range_title)
                    self.selected_tab = tab
                    layout.addWidget(self._build_prefix_table())
                self.selected_tab = "raw"
            return

        layout.addWidget(self._build_visual())
        layout.addLayout(self._build_metrics())

        note = QLabel(self._payload_note())
        note.setObjectName("analysisNote")
        note.setWordWrap(True)
        layout.addWidget(note)

        title = QLabel({
            "prefix": "Progressive Prefix — Raw Data",
            "segments": "Sliding Segments — Raw Data",
        }.get(self.selected_tab, "Whole File — Raw Data"))
        title.setObjectName("analysisDataTitle")
        layout.addWidget(title)
        table = (
            self._build_prefix_table()
            if self.selected_tab in ("prefix", "segments")
            else self._build_whole_table()
        )
        layout.addWidget(table)

    def _build_tabs(self) -> QFrame:
        row = QFrame()
        row.setObjectName("analysisDetailTabs")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        group = QButtonGroup(self)
        group.setExclusive(True)
        self.tab_buttons = {}
        for key, text in self.tabs:
            button = QPushButton(text)
            button.setObjectName("analysisDetailTab")
            button.setCheckable(True)
            button.setChecked(key == self.selected_tab)
            button.clicked.connect(
                lambda checked, tab_key=key: checked
                and self.tab_changed.emit(tab_key)
            )
            group.addButton(button)
            self.tab_buttons[key] = button
            layout.addWidget(button)
        layout.addStretch()
        return row

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
        title = QLabel(
            "Per-frame embedding rate"
            if self.video_scope == "frame" else "Frame Timeline • R − S"
        )
        title.setObjectName("analysisPlotTitle")
        subtitle = QLabel(
            "Estimated embedding rate for each decoded frame."
            if self.video_scope == "frame" else
            "Regular-minus-Singular fraction for each decoded frame; "
            "the vertical axis is fitted to the observed range."
        )
        subtitle.setObjectName("analysisPlotSubtitle")
        panel_layout.addWidget(title)
        panel_layout.addWidget(subtitle)

        measurements = [
            frame.channels[self.selected_channel]
            for frame in self.frames
        ]
        series = (
            (("Estimated embed rate", "#32CA85", [
                item.payload.embedding_rate
                if item.payload.status == "estimated" else None
                for item in measurements
            ]),)
            if self.video_scope == "frame" else (
                ("R−S (M)", "#4096F0", [
                    self._difference(item.rs, False) for item in measurements
                ]),
                ("R−S (−M)", "#35BC79", [
                    self._difference(item.rs, True) for item in measurements
                ]),
            )
        )
        labels = [f"{frame.timestamp_seconds:.2f}s" for frame in self.frames]
        y_min, y_max = (
            (0.0, 1.0) if self.video_scope == "frame"
            else self._timeline_axis(series)
        )
        panel_layout.addWidget(PValueLineChart(
            series,
            labels,
            y_min=y_min,
            y_max=y_max,
            parent=panel,
        ))
        panel_layout.addLayout(self._legend(series))
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

        measurement = selected.channels[self.selected_channel]
        self.frame_note = QLabel(
            self._frame_payload_note(measurement.payload)
        )
        self.frame_note.setObjectName("analysisNote")
        self.frame_note.setWordWrap(True)
        layout.addWidget(self.frame_note)

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

        table_title = QLabel("Per-frame RS Data")
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
        for key, title in (*self.TABS, ("timeline", "Per-frame Trend")):
            button = QPushButton(title)
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

    @staticmethod
    def _timeline_axis(series) -> tuple[float, float]:
        values = [
            float(value)
            for _name, _color, points in series
            for value in points
            if value is not None
        ]
        if not values:
            return -1.0, 1.0
        minimum = min(values)
        maximum = max(values)
        padding = max(0.02, (maximum - minimum) * 0.15)
        return max(-1.0, minimum - padding), min(1.0, maximum + padding)

    def _frame_metric_values(self, frame):
        measurement = frame.channels[self.selected_channel]
        payload = measurement.payload
        return (
            ("Frame", format_integer(frame.frame_index), False),
            ("Timestamp", f"{frame.timestamp_seconds:.3f} s", False),
            ("Estimated rate", format_percent(payload.embedding_rate), True),
            (
                "Expected changes",
                format_integer(payload.expected_changed_samples),
                False,
            ),
            ("Groups", format_integer(measurement.rs.total_groups), False),
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
        measurement = frame.channels[self.selected_channel]
        self.frame_note.setText(
            self._frame_payload_note(measurement.payload)
        )
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

        if self.video_scope == "frame" and self.video_frame_tab == "raw":
            frame = self._selected_frame_result()
            title = QLabel("Whole-frame R/S/U counts and fractions")
            title.setObjectName("analysisDataTitle")
            self.frame_detail_layout.addWidget(title)
            self.frame_detail_layout.addWidget(
                self._build_frame_whole_table(
                    frame.channels[self.selected_channel].rs
                )
            )
            return

        content = QFrame()
        content.setObjectName("analysisFrameDetailPanel")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 11, 12, 12)
        layout.setSpacing(9)
        self.frame_detail_layout.addWidget(content)

        frame_index = self.selected_frame
        detail = self.frame_details.get(frame_index)
        key = ("rs", frame_index)
        loading = key in self.frame_detail_loading
        error = self.frame_detail_errors.get(key)

        title = QLabel(f"Frame {frame_index} Spatial Detail")
        title.setObjectName("analysisDataTitle")
        layout.addWidget(title)

        if detail is None:
            message = QLabel(
                error
                or (
                    "Run an on-demand spatial analysis to inspect the "
                    "RS prefix trend inside this frame."
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
        if self.video_frame_tab == "distribution":
            layout.addWidget(RSDistributionChart(selected_series.whole.rs))
            layout.addWidget(self._build_frame_whole_table(selected_series.whole.rs))
            return
        if self.video_frame_tab == "raw":
            layout.addWidget(self._build_frame_whole_table(selected_series.whole.rs))
            return
        channels = (
            tuple(detail.channels)
            if self.selected_channel == "Whole"
            else (self.selected_channel,)
        )
        series = []
        for channel in channels:
            prefixes = detail.channels[channel].prefix
            if self.video_scope == "frame":
                series.append((
                    ChannelSelector.display_name(channel),
                    self._channel_color(channel, False),
                    [
                        item.analysis.payload.embedding_rate
                        if item.analysis.payload.status == "estimated" else None
                        for item in prefixes
                    ],
                ))
            else:
                series.extend((
                    (
                        f"{ChannelSelector.display_name(channel)} R−S (M)",
                        "#4096F0" if len(channels) == 1 else self._channel_color(channel, False),
                        [self._difference(item.analysis.rs, False) for item in prefixes],
                    ),
                    (
                        f"{ChannelSelector.display_name(channel)} R−S (−M)",
                        "#35BC79" if len(channels) == 1 else self._channel_color(channel, True),
                        [self._difference(item.analysis.rs, True) for item in prefixes],
                    ),
                ))
        y_min, y_max = (
            (0.0, 1.0) if self.video_scope == "frame"
            else self._timeline_axis(series)
        )
        panel = QFrame()
        panel.setObjectName("analysisPlotPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 10, 12, 10)
        panel_layout.setSpacing(4)
        chart_title = QLabel("Progressive Prefix Inside Selected Frame")
        chart_title.setObjectName("analysisPlotTitle")
        subtitle = QLabel(
            "Cumulative embedding-rate estimate in raster order."
            if self.video_scope == "frame" else
            "Cumulative Regular-minus-Singular fractions in raster order."
        )
        subtitle.setObjectName("analysisPlotSubtitle")
        panel_layout.addWidget(chart_title)
        panel_layout.addWidget(subtitle)
        panel_layout.addWidget(PValueLineChart(
            tuple(series),
            [f"{item.percent}%" for item in selected_series.prefix],
            y_min=y_min,
            y_max=y_max,
            parent=panel,
        ))
        panel_layout.addLayout(self._legend(series))
        layout.addWidget(panel)
        layout.addWidget(self._build_spatial_prefix_table(selected_series))

    def _build_frame_whole_table(self, result) -> QTableWidget:
        rows = (
            ("M", "Regular", result.RM_count, result.RM),
            ("M", "Singular", result.SM_count, result.SM),
            ("M", "Unusable", result.UM_count, result.UM),
            ("−M", "Regular", result.R_negM_count, result.R_negM),
            ("−M", "Singular", result.S_negM_count, result.S_negM),
            ("−M", "Unusable", result.U_negM_count, result.U_negM),
        )
        table = self._make_table(len(rows), ("Mask", "Class", "Count", "Fraction"))
        table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        for row, values in enumerate(rows):
            self._set_row(table, row, (
                values[0], values[1], format_integer(values[2]),
                format_number(values[3], 5),
            ))
        table.setMinimumHeight(36 + len(rows) * 28)
        return table

    @staticmethod
    def _channel_color(channel: str, negative: bool) -> str:
        colors = {
            "Whole": ("#38BDF8", "#A78BFA"),
            "R": ("#F87171", "#FB7185"),
            "G": ("#34D399", "#2DD4BF"),
            "B": ("#60A5FA", "#818CF8"),
        }
        pair = colors.get(channel, ("#38BDF8", "#A78BFA"))
        return pair[1 if negative else 0]

    def _build_spatial_prefix_table(self, series) -> QTableWidget:
        table = self._make_table(
            len(series.prefix),
            (
                "Prefix",
                "R(M)",
                "S(M)",
                "R(−M)",
                "S(−M)",
                "Rate",
                "Changes",
                "Groups",
            ),
        )
        for row, item in enumerate(series.prefix):
            result = item.analysis.rs
            payload = item.analysis.payload
            self._set_row(table, row, (
                f"0–{item.percent}%",
                format_number(result.RM, 5),
                format_number(result.SM, 5),
                format_number(result.R_negM, 5),
                format_number(result.S_negM, 5),
                format_percent(payload.embedding_rate),
                format_integer(payload.expected_changed_samples),
                format_integer(result.total_groups),
            ))
        table.setMinimumHeight(
            36 + min(max(len(series.prefix), 3), 10) * 28
        )
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

    @staticmethod
    def _frame_payload_note(payload) -> str:
        if payload.embedding_rate is None:
            return "No usable RS payload estimate for the selected frame."
        if payload.estimated_payload_bits is None:
            return "The selected frame produced an out-of-range RS rate."
        return (
            "Frame estimate for random LSB replacement; it is not a "
            "detection probability."
        )

    def _build_frames_table(self) -> QTableWidget:
        table = self._make_table(
            len(self.frames),
            (
                "Frame",
                "Time",
                "Rate",
                "Changes",
                "R(M)",
                "S(M)",
                "R(−M)",
                "S(−M)",
                "Groups",
            ),
        )
        selected_row = 0
        for row, frame in enumerate(self.frames):
            measurement = frame.channels[self.selected_channel]
            result = measurement.rs
            self._set_row(table, row, (
                format_integer(frame.frame_index),
                f"{frame.timestamp_seconds:.3f} s",
                format_percent(measurement.payload.embedding_rate),
                format_integer(measurement.payload.expected_changed_samples),
                format_number(result.RM, 5),
                format_number(result.SM, 5),
                format_number(result.R_negM, 5),
                format_number(result.S_negM, 5),
                format_integer(result.total_groups),
            ))
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

        if self.selected_tab == "distribution":
            title_text = "Regular / Singular / Unusable"
            description = "Fractions for mask M and its negative mask −M"
        else:
            title_text = (
                "Sliding Segments" if self.selected_tab == "segments"
                else "Progressive Prefix"
            )
            if self.video_scope != "whole":
                title_text += " • R − S"
            description = (
                "Estimated embedding rate across frame ranges"
                if self.video_scope == "whole"
                else "Difference between Regular and Singular fractions"
            )
        title = QLabel(title_text)
        title.setObjectName("analysisPlotTitle")
        subtitle = QLabel(description)
        subtitle.setObjectName("analysisPlotSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        if self.selected_tab == "distribution":
            chart = RSDistributionChart(self.whole_measurement.rs, panel)
            layout.addWidget(chart)
            layout.addLayout(self._legend(
                tuple((name, color, ()) for name, color in RS_COLORS.items())
            ))
        else:
            prefix = (
                self.channel_series.segments
                if self.selected_tab == "segments"
                else self.channel_series.prefix
            )
            series = (
                (("Estimated embed rate", "#32CA85", [
                    item.analysis.payload.embedding_rate
                    if item.analysis.payload.status == "estimated" else None
                    for item in prefix
                ]),)
                if self.video_scope == "whole" else (
                    ("R−S (M)", "#4096F0", [
                        self._difference(item.analysis.rs, False) for item in prefix
                    ]),
                    ("R−S (−M)", "#35BC79", [
                        self._difference(item.analysis.rs, True) for item in prefix
                    ]),
                )
            )
            chart = PValueLineChart(
                series,
                [
                    f"[{item.start_frame}, {item.end_frame})"
                    if self.selected_tab == "segments"
                    else f"{item.percent}%"
                    for item in prefix
                ],
                y_min=0.0 if self.video_scope == "whole" else -1.0,
                y_max=1.0,
                parent=panel,
            )
            layout.addWidget(chart)
            layout.addLayout(self._legend(series))
        return panel

    @staticmethod
    def _difference(result, negative_mask: bool) -> float | None:
        regular = result.R_negM if negative_mask else result.RM
        singular = result.S_negM if negative_mask else result.SM
        if regular is None or singular is None:
            return None
        return regular - singular

    @staticmethod
    def _legend(series) -> QHBoxLayout:
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

    def _build_metrics(self) -> QGridLayout:
        measurement = self.whole_measurement
        payload = measurement.payload
        values = (
            ("Estimated embed rate", format_percent(payload.embedding_rate), True),
            ("Estimated payload (bits)", format_integer(payload.estimated_payload_bits), False),
            ("Expected changes", format_integer(payload.expected_changed_samples), False),
            ("Group count", format_integer(measurement.rs.total_groups), False),
            ("Capacity samples", format_integer(payload.capacity_samples), False),
        )
        layout = QGridLayout()
        layout.setHorizontalSpacing(7)
        layout.setVerticalSpacing(7)
        for column, item in enumerate(values):
            layout.addWidget(MetricTile(*item), 0, column)
        return layout

    def _payload_note(self) -> str:
        payload = self.whole_measurement.payload
        if payload.embedding_rate is None:
            return "The RS equation could not produce a usable payload estimate."
        if payload.estimated_payload_bits is None:
            return (
                "The equation produced an out-of-range rate, so payload and "
                "changed-sample estimates are unavailable."
            )
        return (
            "Estimated percentage of carrier samples used for random LSB "
            "replacement; it is not a detection probability."
        )

    def _build_whole_table(self) -> QTableWidget:
        result = self.whole_measurement.rs
        rows = (
            ("M", "Regular", result.RM_count, result.RM),
            ("M", "Singular", result.SM_count, result.SM),
            ("M", "Unusable", result.UM_count, result.UM),
            ("−M", "Regular", result.R_negM_count, result.R_negM),
            ("−M", "Singular", result.S_negM_count, result.S_negM),
            ("−M", "Unusable", result.U_negM_count, result.U_negM),
        )
        table = self._make_table(
            len(rows),
            ("Mask", "Class", "Count", "Fraction"),
        )
        table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        for row, values in enumerate(rows):
            self._set_row(table, row, (
                values[0],
                values[1],
                format_integer(values[2]),
                format_number(values[3], 5),
            ))
        table.setMinimumHeight(36 + len(rows) * 28)
        return table

    def _build_prefix_table(self) -> QTableWidget:
        prefix = (
            self.channel_series.segments
            if self.selected_tab == "segments"
            else self.channel_series.prefix
        )
        if self.video_scope == "whole":
            table = self._make_table(
                len(prefix),
                ("Scope", "Range (frames, end excluded)", "Embed rate", "Status", "Reason"),
            )
            for row, item in enumerate(prefix):
                payload = item.analysis.payload
                self._set_row(table, row, (
                    f"0–{item.percent}%" if self.selected_tab == "prefix" else "Segment",
                    (f"[0, {item.end_frame})" if self.selected_tab == "prefix"
                     else f"[{item.start_frame}, {item.end_frame})"),
                    format_percent(payload.embedding_rate),
                    payload.status,
                    payload.reason or "",
                ))
            table.horizontalHeader().setStretchLastSection(True)
            table.setMinimumHeight(36 + min(max(len(prefix), 3), 10) * 28)
            return table
        table = self._make_table(
            len(prefix),
            (
                "Prefix",
                "End",
                "R(M)",
                "S(M)",
                "U(M)",
                "R(−M)",
                "S(−M)",
                "U(−M)",
                "Groups",
            ),
        )
        table.horizontalHeader().setMinimumSectionSize(70)
        table.horizontalHeader().setStretchLastSection(True)
        for row, item in enumerate(prefix):
            result = item.analysis.rs
            self._set_row(table, row, (
                (
                    f"[{item.start_frame}, {item.end_frame})"
                    if self.selected_tab == "segments"
                    else f"0–{item.percent}%"
                ),
                (
                    f"{item.start_seconds:.2f}–{item.end_seconds:.2f} s"
                    if self.selected_tab == "segments"
                    else self._prefix_end(item)
                ),
                format_number(result.RM, 5),
                format_number(result.SM, 5),
                format_number(result.UM, 5),
                format_number(result.R_negM, 5),
                format_number(result.S_negM, 5),
                format_number(result.U_negM, 5),
                format_integer(result.total_groups),
            ))
        table.setMinimumHeight(36 + min(max(len(prefix), 3), 10) * 28)
        return table

    def _prefix_end(self, item) -> str:
        if hasattr(item, "end_seconds"):
            return f"{item.end_seconds:.2f} s / frame {item.end_frame:,}"
        return f"sample {item.end:,}"

    @staticmethod
    def _make_table(rows, headers) -> QTableWidget:
        table = QTableWidget(rows, len(headers))
        table.setObjectName("analysisRawTable")
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        for column in range(len(headers)):
            table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        return table

    @staticmethod
    def _set_row(table, row, values) -> None:
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if column > 1:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter
                )
            table.setItem(row, column, item)
