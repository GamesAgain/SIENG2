"""AVI frame views for RS details."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QTableWidget, QVBoxLayout,
)

from src.gui.features.analyzer.widgets.avi_frame_selector import AVIFrameSelector
from src.gui.features.analyzer.widgets.channel_selector import ChannelSelector

from .common import (
    MetricTile, PValueLineChart, format_integer, format_number,
    format_percent,
)
from .rs_chart import RSDistributionChart


class RSFramesMixin:
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

