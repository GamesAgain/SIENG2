"""RS Analysis result widgets for the Bit Statistics tab."""

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


from .rs_chart import RS_COLORS, RSDistributionChart


from .rs_frames import RSFramesMixin


class RSDetail(RSFramesMixin, QFrame):
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
