"""AVI frame views for SPA details."""

from PyQt6.QtWidgets import (
    QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QTableWidget, QVBoxLayout,
)

from src.gui.features.analyzer.widgets.avi_frame_selector import AVIFrameSelector

from .common import MetricTile, PValueLineChart, format_integer, format_percent
from .spa_widgets import SPAStatusStrip


class SPAFramesMixin:
    def _selected_frame_result(self):
        """Return the selected frame, falling back to the first result."""
        for frame in self.frames:
            if frame.frame_index == self.selected_frame:
                return frame
        return self.frames[0]

    def _build_frames_view(self, layout: QVBoxLayout) -> None:
        """Show the video timeline and one selected frame's SPA summary."""
        selected = self._selected_frame_result()
        self.frame_selector = AVIFrameSelector(
            self.frames,
            selected.frame_index,
            parent=self,
        )
        self.frame_selector.frame_changed.connect(self._request_frame)
        layout.addWidget(self.frame_selector)
        if self.video_scope == "frame":
            layout.addWidget(self._build_avi_frame_tabs())
            if self.video_frame_tab != "timeline":
                self.spa_frame_container = QFrame()
                self.spa_frame_layout = QVBoxLayout(self.spa_frame_container)
                self.spa_frame_layout.setContentsMargins(0, 0, 0, 0)
                layout.addWidget(self.spa_frame_container)
                self._render_avi_frame_content(selected)
                return

        panel = QFrame()
        panel.setObjectName("analysisPlotPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 10, 12, 10)
        panel_layout.setSpacing(7)

        title = QLabel("Per-frame SPA Timeline")
        title.setObjectName("analysisPlotTitle")
        subtitle = QLabel(
            "Embedding-rate estimates for each decoded AVI frame. "
            "Gaps indicate frames where SPA could not produce a usable "
            "estimate."
        )
        subtitle.setObjectName("analysisPlotSubtitle")
        subtitle.setWordWrap(True)
        panel_layout.addWidget(title)
        panel_layout.addWidget(subtitle)

        estimates = [
            frame.channels[self.selected_channel].estimate
            for frame in self.frames
        ]
        labels = [
            f"{frame.timestamp_seconds:.2f}s"
            for frame in self.frames
        ]
        values = [self._display_rate(estimate) for estimate in estimates]
        series = (("Embedding rate", "#B47AFA", values),)
        panel_layout.addWidget(PValueLineChart(
            series,
            labels,
            y_min=0.0,
            y_max=1.0,
            parent=panel,
        ))
        panel_layout.addWidget(SPAStatusStrip(
            estimates,
            labels,
            parent=panel,
        ))
        summary = QLabel(self._frame_status_summary(estimates))
        summary.setObjectName("analysisSPAStatusSummary")
        summary.setWordWrap(True)
        panel_layout.addWidget(summary)
        panel_layout.addLayout(self._line_legend(series))
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
        table_title = QLabel("Per-frame SPA Results")
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
        for key, title in (("distribution", "Pair Distributions"),
                           ("raw", "Raw Data"),
                           ("timeline", "Per-frame Trend")):
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

    def _render_avi_frame_content(self, frame) -> None:
        while self.spa_frame_layout.count():
            item = self.spa_frame_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        detail = type(self)(
            report={self.selected_channel: frame.channels[self.selected_channel]},
            selected_channel=self.selected_channel,
            parameters=self.parameters,
            selected_tab=self.video_frame_tab,
            parent=self.spa_frame_container,
        )
        # The video panel owns the title, channel selector and tabs.
        content = detail.layout()
        for _ in range(3):
            item = content.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout() is not None:
                header = item.layout()
                while header.count():
                    child = header.takeAt(0)
                    if child.widget() is not None:
                        child.widget().hide()
                        child.widget().deleteLater()
                header.deleteLater()
        content.setContentsMargins(0, 0, 0, 0)
        detail.setObjectName("analysisVideoContent")
        self.spa_frame_layout.addWidget(detail)

    def _frame_metric_values(self, frame):
        analysis = frame.channels[self.selected_channel]
        estimate = analysis.estimate
        return (
            ("Selected frame", format_integer(frame.frame_index), False),
            ("Timestamp", f"{frame.timestamp_seconds:.3f} s", False),
            (
                "Estimated embed rate",
                format_percent(self._display_rate(estimate)),
                True,
            ),
            (
                "Estimated bits",
                format_integer(estimate.estimated_payload_bits),
                False,
            ),
            (
                "Pair count",
                format_integer(analysis.statistics.pair_count),
                False,
            ),
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
            self._render_avi_frame_content(frame)
            return
        for tile, (_label, value, _accent) in zip(
            self.frame_metric_tiles,
            self._frame_metric_values(frame),
        ):
            tile.set_value(value)
        self.frame_table.selectRow(self._frame_row(frame_index))

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
    def _frame_status_summary(estimates) -> str:
        estimated = sum(
            estimate.status == "estimated" for estimate in estimates
        )
        return (
            f"{estimated}/{len(estimates)} frames produced a usable "
            "embedding-rate estimate."
        )

    def _build_frames_table(self) -> QTableWidget:
        table = self._make_table(
            len(self.frames),
            (
                "Frame",
                "Time",
                "Rate",
                "Bits",
                "Changes",
                "Pairs",
                "Status",
                "Reason",
            ),
        )
        selected_row = 0
        for row, frame in enumerate(self.frames):
            analysis = frame.channels[self.selected_channel]
            estimate = analysis.estimate
            self._set_row(table, row, (
                format_integer(frame.frame_index),
                f"{frame.timestamp_seconds:.3f} s",
                format_percent(self._display_rate(estimate)),
                format_integer(estimate.estimated_payload_bits),
                format_integer(estimate.expected_changed_samples),
                format_integer(analysis.statistics.pair_count),
                estimate.status,
                estimate.reason or "Estimate available",
            ))
            if frame.frame_index == self.selected_frame:
                selected_row = row

        for column in range(table.columnCount() - 1):
            table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        table.horizontalHeader().setSectionResizeMode(
            table.columnCount() - 1,
            QHeaderView.ResizeMode.Stretch,
        )
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

