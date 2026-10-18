"""Sample Pair Analysis result widgets for the Bit Statistics tab."""

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

from src.gui.features.analyzer.details.common import (
    MetricTile,
    PValueLineChart,
    format_integer,
    format_number,
    format_percent,
)
from src.gui.features.analyzer.widgets.channel_selector import ChannelSelector


from .spa_widgets import (
    SPA_COLORS, SPACountChart, SPAStatusPanel, SPAStatusStrip,
    spa_status_title,
)


from .spa_frames import SPAFramesMixin


class SPADetail(SPAFramesMixin, QFrame):
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
