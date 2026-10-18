"""AVI frame views for Chi-square details."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from src.gui.features.analyzer.widgets.avi_frame_selector import AVIFrameSelector
from src.gui.features.analyzer.widgets.channel_selector import ChannelSelector

from .common import (
    MetricTile, PValueLineChart, channel_color, format_integer,
    format_number, format_p_value,
)


class ChiSquareFramesMixin:
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

