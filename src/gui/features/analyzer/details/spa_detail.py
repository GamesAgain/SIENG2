"""Sample Pair Analysis result widgets for the Bit Statistics tab."""

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


SPA_COLORS = {"X": "#B47AFA", "Y": "#38C681"}
SPA_STATUS_COLORS = {
    "estimated": "#32CA85",
    "insufficient": "#64748B",
    "assumption": "#F59E0B",
    "out_of_range": "#F97316",
    "error": "#EF6A6A",
    "unavailable": "#64748B",
}


def spa_status_state(status: str) -> str:
    """Group technical SPA statuses into a small set of UI states."""
    if status == "estimated":
        return "estimated"
    if status == "insufficient_pairs":
        return "insufficient"
    if status in {"assumption_failed_c", "assumption_failed_d"}:
        return "assumption"
    if status == "out_of_range":
        return "out_of_range"
    if status in {
        "degenerate_equation",
        "no_real_root",
        "non_finite_root",
    }:
        return "error"
    return "unavailable"


def spa_status_title(status: str) -> str:
    """Return a readable title without discarding the technical code."""
    state = spa_status_state(status)
    return {
        "estimated": "Estimate available",
        "insufficient": "Insufficient sample pairs",
        "assumption": "SPA assumptions not satisfied",
        "out_of_range": "Estimate outside the 0–100% range",
        "error": "No usable mathematical solution",
        "unavailable": "Estimate unavailable",
    }[state]


def spa_status_reason(estimate) -> str:
    if estimate.reason:
        return estimate.reason
    if estimate.status == "estimated":
        return (
            "SPA produced an embedding-rate estimate within the physical "
            "0–100% range."
        )
    return "The SPA equation did not return a usable estimate."


class SPAStatusPanel(QFrame):
    """Readable SPA estimate state shared by detail and summary cards."""

    def __init__(self, estimate, compact: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("analysisSPAStatusPanel")
        self.compact = compact

        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 7, 9, 7)
        layout.setSpacing(3)

        self.title_label = QLabel()
        self.title_label.setObjectName("analysisSPAStatusTitle")
        self.reason_label = QLabel()
        self.reason_label.setObjectName("analysisSPAStatusReason")
        self.reason_label.setWordWrap(True)
        self.code_label = QLabel()
        self.code_label.setObjectName("analysisSPAStatusCode")

        layout.addWidget(self.title_label)
        layout.addWidget(self.reason_label)
        layout.addWidget(self.code_label)
        self.set_estimate(estimate)

    def set_estimate(self, estimate) -> None:
        self.title_label.setText(spa_status_title(estimate.status))
        self.reason_label.setText(spa_status_reason(estimate))
        self.code_label.setText(f"Status: {estimate.status}")
        self.code_label.setVisible(
            not self.compact or estimate.status != "estimated"
        )


class SPAStatusStrip(QWidget):
    """Show whether every displayed temporal range has a usable estimate."""

    def __init__(self, estimates, labels, parent=None):
        super().__init__(parent)
        self.estimates = tuple(estimates)
        self.labels = tuple(labels)
        self.setFixedHeight(18)
        self.setToolTip("\n".join(
            f"{label}: {estimate.status}"
            for label, estimate in zip(self.labels, self.estimates)
        ))

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.estimates:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = self.rect().adjusted(1, 3, -1, -3)
        gap = 3.0
        width = max(
            2.0,
            (area.width() - gap * (len(self.estimates) - 1))
            / len(self.estimates),
        )
        for index, estimate in enumerate(self.estimates):
            state = spa_status_state(estimate.status)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(SPA_STATUS_COLORS[state]))
            painter.drawRoundedRect(QRectF(
                area.left() + index * (width + gap),
                area.top(),
                width,
                area.height(),
            ), 2, 2)


class SPACountChart(QWidget):
    """Grouped X/Y counts labelled by their odd sample differences."""

    def __init__(self, statistics, bin_count: int = 31, parent=None):
        super().__init__(parent)
        self.statistics = statistics
        self.bin_count = max(
            1,
            min(bin_count, len(statistics.x_counts)),
        )
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
        maximum = max(
            (value for values in arrays for value in values),
            default=0,
        )
        maximum = max(1, maximum)
        grid_pen = QPen(QColor("#39424A"), 1, Qt.PenStyle.DashLine)
        text_color = QColor("#8FA2B5")
        if self.statistics.pair_count == 0:
            painter.setPen(text_color)
            painter.drawText(
                plot,
                Qt.AlignmentFlag.AlignCenter,
                "N/A - no complete pairs",
            )
            return

        for step in range(5):
            ratio = step / 4
            y = plot.bottom() - ratio * plot.height()
            painter.setPen(grid_pen)
            painter.drawLine(plot.left(), int(y), plot.right(), int(y))
            painter.setPen(text_color)
            painter.drawText(
                2,
                int(y + 4),
                self._short_count(maximum * ratio),
            )

        group_width = plot.width() / self.bin_count
        bar_width = max(1.0, group_width / 2 - 1.0)
        for series_index, (name, values) in enumerate(
            zip(SPA_COLORS, arrays)
        ):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(SPA_COLORS[name]))
            for index, value in enumerate(values):
                height = value / maximum * plot.height()
                painter.drawRect(QRectF(
                    plot.left()
                    + index * group_width
                    + series_index * bar_width,
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
            difference = 2 * index + 1
            painter.drawText(
                int(x - 16),
                plot.bottom() + 8,
                32,
                18,
                Qt.AlignmentFlag.AlignHCenter
                | Qt.AlignmentFlag.AlignTop,
                str(difference),
            )

    @staticmethod
    def _short_count(value: float) -> str:
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        if value >= 1_000:
            return f"{value / 1_000:.1f}K"
        return str(int(round(value)))


class SPADetail(QFrame):
    """SPA distribution, temporal ranges, estimate and raw vectors."""

    channel_changed = pyqtSignal(str)
    tab_changed = pyqtSignal(str)
    frame_changed = pyqtSignal(int)
    frame_view_tab_changed = pyqtSignal(str)

    def __init__(
        self,
        report: Mapping[str, Any],
        selected_channel: str,
        parameters,
        selected_tab: str = "distribution",
        frames=(),
        selected_frame: int | None = None,
        parent=None,
        video_scope: str | None = None,
        video_frame_tab: str = "timeline",
    ):
        super().__init__(parent)
        if selected_channel not in report:
            raise ValueError("selected_channel must exist in report.")

        self.setObjectName("analysisDetailPanel")
        self.setProperty("detectorType", "spa")
        self.report = report
        self.selected_channel = selected_channel
        self.parameters = parameters
        self.video_scope = video_scope
        self.video_frame_tab = video_frame_tab
        self.frames = tuple(frames)
        self.selected_frame = selected_frame
        self.has_ranges = hasattr(self.channel_result, "prefix")
        self.tabs = [("distribution", "Pair Distributions")]
        if self.has_ranges:
            self.tabs.extend((
                ("prefix", "Progressive Prefix"),
                ("segments", "Sliding Segments"),
            ))
        if video_scope == "frame":
            self.tabs = [("frames", "Per-frame Trend")]
        else:
            if self.frames:
                self.tabs.append(("frames", "Frames"))
            self.tabs.append(("raw", "Raw Data"))
        valid_tabs = {key for key, _text in self.tabs}
        self.selected_tab = (
            selected_tab if selected_tab in valid_tabs else "distribution"
        )
        self._setup_ui()

    @property
    def channel_result(self):
        return self.report[self.selected_channel]

    @property
    def whole_analysis(self):
        return getattr(self.channel_result, "whole", self.channel_result)

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
            diagnostics_title = QLabel("SPA Equation Diagnostics")
            diagnostics_title.setObjectName("analysisDataTitle")
            layout.addWidget(diagnostics_title)
            layout.addWidget(self._build_diagnostics_panel())
            title = QLabel("Complete SPA Count Vectors")
            title.setObjectName("analysisDataTitle")
            layout.addWidget(title)
            layout.addWidget(self._build_raw_table())
            return

        layout.addWidget(self._build_visual())
        layout.addLayout(self._build_metrics())

        if self.selected_tab == "distribution":
            title_text = "Odd-difference Pair Counts"
            table = self._build_distribution_table()
        else:
            title_text = (
                "Progressive Prefix — Estimates"
                if self.selected_tab == "prefix"
                else "Sliding Segments — Estimates"
            )
            table = self._build_range_table()
        title = QLabel(title_text)
        title.setObjectName("analysisDataTitle")
        layout.addWidget(title)
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

    def _build_visual(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("analysisPlotPanel")
        layout = QVBoxLayout(panel)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)

        if self.selected_tab == "distribution":
            title_text = "X / Y Odd-difference Pair Counts"
            description = (
                "Pair count by odd sample difference (1, 3, 5, ...). "
                f"The SPA equation pools differences 1–"
                f"{2 * self.parameters.spa_j + 1}."
            )
        else:
            title_text = (
                "Progressive Prefix • Embedding Rate"
                if self.selected_tab == "prefix"
                else "Sliding Segments • Embedding Rate"
            )
            description = (
                "Estimated LSB replacement rate across cumulative ranges."
                if self.selected_tab == "prefix"
                else "Estimated LSB replacement rate across local ranges."
            )
        title = QLabel(title_text)
        title.setObjectName("analysisPlotTitle")
        subtitle = QLabel(description)
        subtitle.setObjectName("analysisPlotSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        if self.selected_tab == "distribution":
            chart = SPACountChart(
                self.whole_analysis.statistics,
                bin_count=self.parameters.spa_j + 1,
                parent=panel,
            )
            layout.addWidget(chart)
            layout.addLayout(self._distribution_legend())
        else:
            items = self._range_items()
            labels = [self._range_label(item) for item in items]
            estimates = [item.analysis.estimate for item in items]
            values = [
                self._display_rate(estimate)
                for estimate in estimates
            ]
            series = (("Embedding rate", "#B47AFA", values),)
            chart = PValueLineChart(
                series,
                labels,
                y_min=0.0,
                y_max=1.0,
                parent=panel,
            )
            layout.addWidget(chart)
            layout.addWidget(SPAStatusStrip(
                estimates,
                labels,
                parent=panel,
            ))
            summary = QLabel(self._range_status_summary(estimates))
            summary.setObjectName("analysisSPAStatusSummary")
            summary.setWordWrap(True)
            layout.addWidget(summary)
            layout.addLayout(self._line_legend(series))
        return panel

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
        detail = SPADetail(
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

    @staticmethod
    def _distribution_legend() -> QHBoxLayout:
        labels = {
            "X": "X: even sample value is larger",
            "Y": "Y: odd sample value is larger",
        }
        series = tuple(
            (labels[name], color, ())
            for name, color in SPA_COLORS.items()
        )
        return SPADetail._line_legend(series)

    @staticmethod
    def _line_legend(series) -> QHBoxLayout:
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
        statistics = self.whole_analysis.statistics
        estimate = self.whole_analysis.estimate
        displayed_rate = self._display_rate(estimate)
        values = (
            ("Estimated embed rate", format_percent(displayed_rate), True),
            ("Estimated bits", format_integer(estimate.estimated_payload_bits), False),
            ("Expected changes", format_integer(estimate.expected_changed_samples), False),
            ("Pair count", format_integer(statistics.pair_count), False),
        )
        layout = QGridLayout()
        layout.setHorizontalSpacing(7)
        layout.setVerticalSpacing(7)
        for column, item in enumerate(values):
            layout.addWidget(MetricTile(*item), 0, column)
        return layout

    @staticmethod
    def _display_rate(estimate) -> float | None:
        if estimate.status != "estimated":
            return None
        return estimate.embedding_rate

    @staticmethod
    def _range_status_summary(estimates) -> str:
        counts: dict[str, int] = {}
        for estimate in estimates:
            counts[estimate.status] = counts.get(estimate.status, 0) + 1
        estimated = counts.pop("estimated", 0)
        parts = [f"{estimated}/{len(estimates)} ranges estimated"]
        parts.extend(
            f"{spa_status_title(status)}: {count}"
            for status, count in sorted(counts.items())
        )
        return " • ".join(parts)

    def _build_diagnostics_panel(self) -> QFrame:
        estimate = self.whole_analysis.estimate
        diagnostics = estimate.diagnostics
        coefficients = estimate.coefficients or (None, None, None)
        roots = estimate.roots

        panel = QFrame()
        panel.setObjectName("analysisSPADiagnostics")
        layout = QGridLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(5)

        rows = (
            ("Status", estimate.status),
            ("Reason", estimate.reason or "—"),
            ("j", str(diagnostics.j) if diagnostics else "N/A"),
            (
                "C0 / C(j+1)",
                (
                    f"{diagnostics.c0:,} / "
                    f"{diagnostics.c_j_plus_1:,}"
                    if diagnostics else "N/A"
                ),
            ),
            (
                "D0 / D(2j+2)",
                (
                    f"{diagnostics.d0:,} / "
                    f"{diagnostics.d_2j_plus_2:,}"
                    if diagnostics else "N/A"
                ),
            ),
            (
                "Sum X / Sum Y",
                (
                    f"{diagnostics.sum_x:,} / {diagnostics.sum_y:,}"
                    if diagnostics else "N/A"
                ),
            ),
            (
                "Trace difference",
                (
                    f"{diagnostics.trace_difference:,}"
                    if diagnostics else "N/A"
                ),
            ),
            (
                "Coefficients (A, B, T)",
                ", ".join(format_number(value, 6) for value in coefficients),
            ),
            (
                "Roots",
                ", ".join(format_number(value, 6) for value in roots)
                if roots else "N/A",
            ),
            (
                "Discriminant",
                format_number(
                    diagnostics.discriminant if diagnostics else None,
                    6,
                ),
            ),
            (
                "Selected root",
                format_number(
                    diagnostics.selected_root if diagnostics else None,
                    6,
                ),
            ),
        )
        for row, (label_text, value_text) in enumerate(rows):
            label = QLabel(label_text)
            label.setObjectName("analysisSPADiagnosticLabel")
            value = QLabel(value_text)
            value.setObjectName("analysisSPADiagnosticValue")
            value.setWordWrap(True)
            value.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            layout.addWidget(label, row, 0)
            layout.addWidget(value, row, 1)
        layout.setColumnStretch(1, 1)
        return panel

    def _range_items(self):
        return getattr(self.channel_result, self.selected_tab)

    def _range_label(self, item) -> str:
        if self.selected_tab == "prefix":
            return f"{item.percent}%"
        if hasattr(item, "start_seconds"):
            return f"{item.start_seconds:.1f}–{item.end_seconds:.1f}s"
        return f"{item.start}–{item.end}"

    def _range_scope(self, item) -> str:
        if self.selected_tab == "prefix":
            if hasattr(item, "end_seconds"):
                return (
                    f"0–{item.end_seconds:.2f} s "
                    f"(frame {item.end_frame:,})"
                )
            return f"0–{item.percent}%"
        if hasattr(item, "start_seconds"):
            return (
                f"{item.start_seconds:.2f}–{item.end_seconds:.2f} s "
                f"(frames {item.start_frame:,}–{item.end_frame:,})"
            )
        return f"{item.start:,}–{item.end:,}"

    def _build_distribution_table(self) -> QTableWidget:
        statistics = self.whole_analysis.statistics
        row_count = min(
            self.parameters.spa_j + 1,
            len(statistics.x_counts),
        )
        table = self._make_table(
            row_count,
            ("Sample difference", "X count", "Y count", "Y − X"),
        )
        for row in range(row_count):
            x_count = statistics.x_counts[row]
            y_count = statistics.y_counts[row]
            self._set_row(table, row, (
                str(2 * row + 1),
                format_integer(x_count),
                format_integer(y_count),
                format_integer(y_count - x_count),
            ))
        table.setMinimumHeight(36 + min(max(row_count, 3), 10) * 28)
        return table

    def _build_range_table(self) -> QTableWidget:
        items = self._range_items()
        table = self._make_table(
            len(items),
            (
                "Range",
                "Rate",
                "Bits",
                "Changes",
                "Pairs",
                "Status",
                "Reason",
            ),
        )
        for row, item in enumerate(items):
            analysis = item.analysis
            estimate = analysis.estimate
            self._set_row(table, row, (
                self._range_scope(item),
                format_percent(self._display_rate(estimate)),
                format_integer(estimate.estimated_payload_bits),
                format_integer(estimate.expected_changed_samples),
                format_integer(analysis.statistics.pair_count),
                estimate.status,
                estimate.reason or "Estimate available",
            ))
        for column in range(table.columnCount() - 1):
            table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        table.horizontalHeader().setSectionResizeMode(
            table.columnCount() - 1,
            QHeaderView.ResizeMode.Stretch,
        )
        table.setMinimumHeight(36 + min(max(len(items), 3), 10) * 28)
        return table

    def _build_raw_table(self) -> QTableWidget:
        statistics = self.whole_analysis.statistics
        table = self._make_table(
            256,
            ("Index", "C count", "D count", "X count", "Y count"),
        )
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
                    format_integer(counts[row])
                    if row < len(counts)
                    else "—"
                )
            self._set_row(table, row, values)
        table.setMinimumHeight(36 + 10 * 28)
        return table

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
                QHeaderView.ResizeMode.Stretch,
            )
        return table

    @staticmethod
    def _set_row(table, row, values) -> None:
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if column > 0:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter
                )
            table.setItem(row, column, item)
