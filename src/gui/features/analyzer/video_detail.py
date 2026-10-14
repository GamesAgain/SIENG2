"""Simple video detail workspace sharing the established image widgets."""

from collections import OrderedDict
from dataclasses import asdict, is_dataclass
import json

from PyQt6.QtCore import Qt, pyqtSignal, QAbstractTableModel, QModelIndex
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QButtonGroup,
    QSpinBox, QTableView, QHeaderView, QGridLayout,
)

from src.gui.features.analyzer.chi_square_detail import (
    ChannelSelector, PValueLineChart, MetricTile, ChiSquareDetail,
    format_p_value, format_percent, format_integer,
)
from src.gui.features.analyzer.rs_detail import RSDetail, RSDistributionChart
from src.gui.features.analyzer.spa_detail import SPADetail, SPACountChart
from src.gui.features.analyzer.analysis_runner import fingerprint_file
from src.gui.services.worker import FunctionWorker
from src.core.analyzer.formats.video import analyze_video_frame_details


NAMES = {"chi_square": "Chi-square Analysis", "rs": "RS Analysis", "spa": "Sample Pair Analysis"}
COLORS = {"chi_square": "#38BDF8", "rs": "#32CA85", "spa": "#B47AFA"}


def measurement(value):
    """Unwrap range entries without losing detector status information."""
    for attribute in ("chi_square", "measurement", "estimate"):
        if hasattr(value, attribute):
            return getattr(value, attribute)
    return value


def estimate(value):
    value = measurement(value)
    return value.payload if hasattr(value, "payload") else value


def scalar(detector, value):
    value = estimate(value)
    if detector == "chi_square":
        return value.p_value
    return value.embedding_rate if value.status == "estimated" else None


def flatten(value, prefix=""):
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        rows = []
        for key, child in value.items():
            rows.extend(flatten(child, f"{prefix}.{key}" if prefix else str(key)))
        return rows
    if isinstance(value, (list, tuple)):
        return [(prefix, json.dumps(value, ensure_ascii=False, default=str))]
    return [(prefix, "N/A" if value is None else str(value))]


class RowsModel(QAbstractTableModel):
    """Read-only lazy table: no QWidget allocation for each video frame."""

    def __init__(self, headers, rows, parent=None):
        super().__init__(parent)
        self.headers, self.rows = headers, rows

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return str(self.rows[index.row()][index.column()])
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section]
        return None


class FrameChart(PValueLineChart):
    frame_selected = pyqtSignal(int)

    def mousePressEvent(self, event):
        count = len(self.labels)
        if count:
            ratio = (event.position().x() - 48) / max(1, self.width() - 66)
            self.frame_selected.emit(round(max(0, min(1, ratio)) * (count - 1)))
        super().mousePressEvent(event)


class VideoDetail(QFrame):
    """Whole-video ranges and exact-frame spatial details with shared selection."""

    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.result = result
        self.detector = "chi_square"
        self.channel = "Whole"
        self.level = "whole"
        self.tabs = {name: "overview" for name in NAMES}
        self.frame_tabs = {"chi_square": "prefix", "rs": "distribution", "spa": "distribution"}
        self.frame_index = result.video_info["start_frame"]
        self.cache = OrderedDict()
        self.workers = {}
        self.request_id = 0
        self.pending_frame = None
        self.frame_error = None
        self.disposed = False
        self.pending_parameters = result.parameters
        self.layout_root = QVBoxLayout(self)
        self.layout_root.setContentsMargins(0, 0, 0, 0)
        self.body = None
        self.render()

    def dispose(self):
        self.disposed = True
        self.request_id += 1
        for worker in self.workers.values():
            worker.requestInterruption()

    def select_detector(self, name):
        self.detector = name
        self.render()

    def select_channel(self, name):
        self.channel = name
        self.render()

    def select_level(self, level):
        self.level = level
        self.frame_error = None
        if level == "frame":
            self.load_frame()
        self.render()

    def select_tab(self, tab):
        self.tabs[self.detector] = tab
        self.render()

    def select_frame_tab(self, tab):
        self.frame_tabs[self.detector] = tab
        self.render()

    def select_frame(self, index):
        self.frame_index = index
        self.frame_error = None
        self.load_frame()
        self.render()

    def load_frame(self):
        if self.disposed:
            return
        if self.frame_index in self.cache:
            self.cache.move_to_end(self.frame_index)
            return
        if self.pending_frame == self.frame_index:
            return
        for worker in self.workers.values():
            worker.requestInterruption()
        self.request_id += 1
        request_id, index = self.request_id, self.frame_index
        self.pending_frame = index
        snapshot = self.result

        def calculate(cancel_check):
            if fingerprint_file(snapshot.file_path) != snapshot.file_fingerprint:
                raise RuntimeError("The video changed. Run Analysis again.")
            details = analyze_video_frame_details(snapshot.file_path, index, snapshot.parameters, cancel_check)
            if fingerprint_file(snapshot.file_path) != snapshot.file_fingerprint:
                raise RuntimeError("The video changed during frame analysis.")
            return details

        worker = FunctionWorker(calculate)
        worker._kwargs["cancel_check"] = worker.isInterruptionRequested
        self.workers[request_id] = worker
        worker.done.connect(lambda value, rid=request_id: self.frame_ready(rid, value))
        worker.finished.connect(lambda rid=request_id: self.workers.pop(rid, None))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def frame_ready(self, request_id, value):
        if self.disposed or request_id != self.request_id:
            return
        self.pending_frame = None
        if value.get("error"):
            self.frame_error = value["error"]
        else:
            self.cache[value["frame_index"]] = value
            while len(self.cache) > 8:
                self.cache.popitem(last=False)
        self.render()

    @staticmethod
    def buttons(options, selected, callback, parent):
        row = QGridLayout() if len(options) > 4 else QHBoxLayout()
        group = QButtonGroup(parent)
        group.setExclusive(True)
        for index, (key, label) in enumerate(options):
            button = QPushButton(label)
            button.setObjectName("analysisDetailTab")
            button.setCheckable(True)
            button.setChecked(key == selected)
            button.clicked.connect(lambda checked, value=key: callback(value) if checked else None)
            group.addButton(button)
            if isinstance(row, QGridLayout):
                row.addWidget(button, index // 3, index % 3)
            else:
                row.addWidget(button)
        if isinstance(row, QHBoxLayout):
            row.addStretch()
        return row

    @staticmethod
    def table(headers, rows, parent):
        table = QTableView(parent)
        table.setObjectName("analysisRawTable")
        table.setModel(RowsModel(headers, rows, table))
        table.setAlternatingRowColors(True)
        table.setStyleSheet(
            "QTableView { background: #222222; alternate-background-color: #282828; "
            "color: #CBD5E1; gridline-color: #39424A; selection-background-color: #16465A; }"
            "QHeaderView::section { background: #292929; color: #94A3B8; padding: 5px; border: 1px solid #39424A; }"
        )
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumHeight(220)
        return table

    def render(self):
        if self.disposed:
            return
        if self.body is not None:
            self.layout_root.removeWidget(self.body)
            self.body.hide()
            self.body.deleteLater()
        self.body = QFrame()
        self.body.setObjectName("analysisDetailPanel")
        self.body.setProperty("detectorType", {"chi_square": "chi", "rs": "rs", "spa": "spa"}[self.detector])
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(14, 13, 14, 14)
        title = QLabel(NAMES[self.detector])
        title.setObjectName("analysisPanelTitle")
        layout.addWidget(title)
        layout.addLayout(self.buttons((("whole", "Whole Video"), ("frame", "Per Frame")),
                                      self.level, self.select_level, self.body))
        channels = ChannelSelector(["Whole", "R", "G", "B"], self.channel)
        channels.channel_changed.connect(self.select_channel)
        layout.addWidget(channels)
        info = self.result.video_info
        duration = f"{info['duration_seconds']:.3f}s" if info['duration_seconds'] is not None else "N/A"
        context = QLabel(f"AVI · {info['codec']} · {info['width']} × {info['height']} · "
                         f"{info['frame_rate']:g} FPS · {info['decoded_frame_count']} decoded frames · {duration}\n"
                         f"Analyzed frames [{info['start_frame']}, {info['end_frame']}) · Channel {self.channel} · "
                         f"SHA-256 {self.result.file_fingerprint.sha256[:12]}…")
        context.setObjectName("analysisContextText")
        context.setWordWrap(True)
        layout.addWidget(context)
        params = self.result.parameters
        settings = QLabel(f"Prefix {params.prefix_step}% · Segments {params.segment_percent}% @ {params.segment_step}% · "
                          f"Chi min expected {params.min_expected:g} · SPA j {params.spa_j}, min pairs {params.spa_min_pairs}")
        settings.setObjectName("analysisNote")
        settings.setWordWrap(True)
        layout.addWidget(settings)
        if self.pending_parameters != params:
            note = QLabel("Parameters changed. Run Analysis to apply. Details and export keep the displayed settings.")
            note.setObjectName("analysisNote")
            note.setWordWrap(True)
            layout.addWidget(note)
        if self.level == "whole":
            self.render_whole(layout)
        else:
            self.render_frame(layout)
        layout.addWidget(self.summary())
        for label in self.body.findChildren(QLabel):
            if not label.objectName():
                label.setObjectName("analysisNote")
                label.setWordWrap(True)
        self.layout_root.addWidget(self.body)

    def data(self, detector=None):
        return getattr(self.result, detector or self.detector)["targets"][self.channel]

    def render_whole(self, layout):
        options = [("overview", "Overview" if self.detector == "chi_square" else
                    "Distribution" if self.detector == "rs" else "Pair Distributions"),
                   ("prefix", "Progressive Prefix"), ("segments", "Sliding Segments")]
        if self.detector == "chi_square":
            options.extend((("spatial_prefix", "Spatial Prefix (All Frames)"),
                            ("spatial_segments", "Spatial Segments (All Frames)")))
        options.append(("raw", "Raw Data"))
        layout.addLayout(self.buttons(options, self.tabs[self.detector], self.select_tab, self.body))
        data = self.data()
        tab = self.tabs[self.detector]
        layout.addLayout(self.metrics(data["whole"]))
        if tab == "overview":
            if self.detector == "rs":
                layout.addWidget(RSDistributionChart(data["whole"].rs))
                layout.addWidget(QLabel("Regular / Singular / Unusable · masks M and −M"))
                layout.addWidget(self.table(("Field", "Value"), flatten(data["whole"]), self.body))
            elif self.detector == "spa":
                layout.addWidget(SPACountChart(data["statistics"], self.result.parameters.spa_j + 1))
                layout.addWidget(QLabel("X / Y counts · odd pixel differences · pooled across all analyzed frames"))
                layout.addWidget(self.table(("Field", "Value"), flatten(data["whole"]), self.body))
            self.timeline(layout)
            return
        if tab == "raw":
            rows = flatten(data["whole"], "whole")
            if self.detector == "spa":
                rows += flatten(data["statistics"], "statistics")
            layout.addWidget(self.table(("Field", "Value"), rows, self.body))
            self.range_table(layout, data["progressive_prefix"], "frames", True)
            self.range_table(layout, data["frame_segments"], "frames", False)
            layout.addWidget(self.table(("Scope", "Field", "Value"),
                [(f"prefix {item.percent}%", field, value) for item in data["progressive_prefix"]
                 for field, value in flatten(measurement(item))] +
                [(f"segment {self.range_label(item, 'frames')}", field, value) for item in data["frame_segments"]
                 for field, value in flatten(measurement(item))], self.body))
            self.timeline(layout)
            return
        key = {"prefix": "progressive_prefix", "segments": "frame_segments",
               "spatial_prefix": "spatial_prefix", "spatial_segments": "spatial_segments"}[tab]
        unit = "pixels" if tab.startswith("spatial") else "frames"
        values = data[key]
        labels = [f"{item.percent}%" if "prefix" in tab else self.range_label(item, unit) for item in values]
        layout.addWidget(QLabel(f"{'Cumulative' if 'prefix' in tab else 'Sliding'} {unit} · "
                                "combined counts, then calculated statistics"))
        layout.addWidget(PValueLineChart(((self.channel, COLORS[self.detector],
                         [scalar(self.detector, item) for item in values]),), labels))
        layout.addWidget(QLabel("Y: p-value" if self.detector == "chi_square" else "Y: embedding rate (0–1)"))
        self.range_table(layout, values, unit, "prefix" in tab)

    def range_label(self, item, unit):
        start = getattr(item, "start", 0)
        offset = self.result.video_info["start_frame"] if unit == "frames" else 0
        return f"[{start + offset}, {item.end + offset})"

    def range_table(self, layout, values, unit, prefix):
        rows = []
        for item in values:
            value = estimate(item)
            rows.append((f"0–{item.percent}%" if prefix else "Segment", self.range_label(item, unit),
                         format_p_value(scalar(self.detector, item)) if self.detector == "chi_square"
                         else format_percent(scalar(self.detector, item)), value.status, value.reason or ""))
        layout.addWidget(self.table(("Scope", f"Range ({unit}, end excluded)",
                                    "p-value" if self.detector == "chi_square" else "Embed rate",
                                    "Status", "Reason"), rows, self.body))

    def timeline(self, layout):
        data = self.data()
        start = self.result.video_info["start_frame"]
        labels = [str(start + i) for i in range(len(data["per_frame"]))]
        caption = QLabel("Per-frame p-value · click to inspect" if self.detector == "chi_square"
                         else "Per-frame embedding rate (0–1) · click to inspect")
        caption.setObjectName("analysisPlotTitle")
        layout.addWidget(caption)
        chart = FrameChart(((self.channel, COLORS[self.detector],
                            [scalar(self.detector, item) for item in data["per_frame"]]),), labels)
        chart.frame_selected.connect(lambda index: self.open_frame(start + index))
        layout.addWidget(chart)
        rows = []
        fps = self.result.video_info["frame_rate"]
        for i, item in enumerate(data["per_frame"]):
            value = estimate(item)
            rows.append((start + i, f"{(start + i) / fps:.3f}" if fps > 0 else "N/A",
                         format_p_value(scalar(self.detector, item)) if self.detector == "chi_square"
                         else format_percent(scalar(self.detector, item)), value.status, value.reason or ""))
        table = self.table(("Frame (0-based)", "Time (s)", "p-value" if self.detector == "chi_square"
                           else "Embed rate", "Status", "Reason"), rows, self.body)
        table.clicked.connect(lambda index: self.open_frame(start + index.row()))
        layout.addWidget(table)

    def open_frame(self, index):
        self.level = "frame"
        self.select_frame(index)

    def render_frame(self, layout):
        info = self.result.video_info
        row = QHBoxLayout()
        previous, following = QPushButton("Previous"), QPushButton("Next")
        previous.setObjectName("SecondaryBtn")
        following.setObjectName("SecondaryBtn")
        previous.setEnabled(self.frame_index > info["start_frame"])
        following.setEnabled(self.frame_index < info["end_frame"] - 1)
        previous.clicked.connect(lambda: self.select_frame(self.frame_index - 1))
        following.clicked.connect(lambda: self.select_frame(self.frame_index + 1))
        spin = QSpinBox()
        spin.setObjectName("analysisParameterInput")
        spin.setStyleSheet("QSpinBox { background: #252525; color: #CBD5E1; "
                          "border: 1px solid #414141; border-radius: 4px; padding: 4px; }")
        spin.setRange(info["start_frame"], info["end_frame"] - 1)
        spin.setValue(self.frame_index)
        spin.setKeyboardTracking(False)
        spin.valueChanged.connect(self.select_frame)
        row.addWidget(QLabel("Frame (0-based):"))
        row.addWidget(previous)
        row.addWidget(spin)
        row.addWidget(following)
        fps = info["frame_rate"]
        row.addWidget(QLabel(f"Time: {self.frame_index / fps:.3f}s" if fps > 0 else "Time: N/A"))
        row.addStretch()
        layout.addLayout(row)
        selected = self.data()["per_frame"][self.frame_index - info["start_frame"]]
        layout.addLayout(self.metrics(selected))
        details = self.cache.get(self.frame_index)
        if details is None:
            layout.addWidget(QLabel(self.frame_error or "Loading exact-frame spatial details…"))
            return
        report = details[self.detector]
        tab = self.frame_tabs[self.detector]
        if self.detector == "chi_square":
            detail = ChiSquareDetail(report, self.channel, tab)
        elif self.detector == "rs":
            detail = RSDetail(report, self.channel, tab)
        else:
            detail = SPADetail(report, self.channel, self.result.parameters, tab)
        detail.channel_changed.connect(self.select_channel)
        detail.tab_changed.connect(self.select_frame_tab)
        layout.addWidget(QLabel("Spatial details of this frame · prefix / segments use pixels"))
        layout.addWidget(detail)
        layout.addWidget(self.table(("Field", "Value"), flatten(selected), self.body))
        self.timeline(layout)

    def metrics(self, item):
        value = estimate(item)
        if self.detector == "chi_square":
            fields = (("p-value", format_p_value(value.p_value)),
                      ("Chi-square", "N/A" if value.chi_square_total is None else f"{value.chi_square_total:.5g}"),
                      ("Samples", format_integer(value.sample_count)),
                      ("Valid PoV pairs", format_integer(value.valid_pairs)))
        else:
            fields = (("Estimated embed rate", format_percent(scalar(self.detector, item))),
                      ("Payload bits", format_integer(value.estimated_payload_bits)),
                      ("Expected changes", format_integer(value.expected_changed_samples)),
                      ("Samples", format_integer(getattr(value, "capacity_samples", getattr(value, "sample_count", None)))))
        grid = QGridLayout()
        for i, (name, display) in enumerate(fields):
            grid.addWidget(MetricTile(name, display, i == 0), 0, i)
        status = QLabel(f"Status: {value.status}" + (f" · {value.reason}" if value.reason else ""))
        status.setWordWrap(True)
        grid.addWidget(status, 1, 0, 1, len(fields))
        return grid

    def summary(self):
        panel = QFrame()
        panel.setObjectName("analysisSummaryCard")
        row = QHBoxLayout(panel)
        offset = self.frame_index - self.result.video_info["start_frame"]
        for name in NAMES:
            data = self.data(name)
            item = data["whole"] if self.level == "whole" else data["per_frame"][offset]
            number = scalar(name, item)
            value = format_p_value(number) if name == "chi_square" else format_percent(number)
            label = QLabel(f"{NAMES[name]}\n{self.channel} · "
                          f"{'Whole Video' if self.level == 'whole' else 'Frame ' + str(self.frame_index)}\n{value}")
            label.setObjectName("analysisSummaryLabel")
            label.setWordWrap(True)
            row.addWidget(label)
        return panel
