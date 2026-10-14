"""Simple video detail workspace sharing the established image widgets."""

from collections import OrderedDict

from PyQt6.QtCore import Qt, pyqtSignal, QAbstractTableModel, QModelIndex
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QButtonGroup,
    QSpinBox, QTableView, QHeaderView, QGridLayout, QAbstractItemView,
)

from src.gui.features.analyzer.chi_square_detail import (
    ChannelSelector, PValueLineChart, MetricTile, ChiSquareDetail,
    format_p_value, format_percent, format_integer,
)
from src.gui.features.analyzer.rs_detail import RSDetail
from src.gui.features.analyzer.spa_detail import SPADetail
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
        if index.isValid() and role == Qt.ItemDataRole.TextAlignmentRole and index.column() > 1:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
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

    def __init__(self, result, parent=None, summary_builder=None):
        super().__init__(parent)
        self.result = result
        self.summary_builder = summary_builder
        self.detector = "chi_square"
        self.channel = "Whole"
        self.level = "whole"
        self.tabs = {"chi_square": "prefix", "rs": "overview", "spa": "overview"}
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
    def buttons(options, selected, callback, parent, channel_style=False):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5 if channel_style else 2)
        group = QButtonGroup(parent)
        group.setExclusive(True)
        for key, label in options:
            button = QPushButton(label)
            button.setObjectName("analysisChannelButton" if channel_style else "analysisDetailTab")
            button.setCheckable(True)
            button.setChecked(key == selected)
            button.clicked.connect(lambda checked, value=key: callback(value) if checked else None)
            group.addButton(button)
            row.addWidget(button)
        row.addStretch()
        return row

    @staticmethod
    def table(headers, rows, parent):
        table = QTableView(parent)
        table.setObjectName("analysisRawTable")
        table.setModel(RowsModel(headers, rows, table))
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumHeight(36 + min(max(len(rows), 3), 10) * 28)
        return table

    def render(self):
        if self.disposed:
            return
        if self.body is not None:
            self.layout_root.removeWidget(self.body)
            self.body.hide()
            self.body.deleteLater()
        self.body = QFrame()
        outer = QHBoxLayout(self.body)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        detail_panel = QFrame()
        detail_panel.setObjectName("analysisDetailPanel")
        detail_panel.setProperty("detectorType", self.detector)
        layout = QVBoxLayout(detail_panel)
        layout.setContentsMargins(14, 13, 14, 14)
        layout.setSpacing(11)
        header = QHBoxLayout()
        title = QLabel(NAMES[self.detector])
        title.setObjectName("analysisPanelTitle")
        badge = QLabel({"chi_square": "PoV", "rs": "M / −M", "spa": "SPA"}[self.detector])
        badge.setObjectName("analysisPanelBadge")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(badge)
        layout.addLayout(header)
        level_row = self.buttons((("whole", "Whole Video"), ("frame", "Per Frame")),
                                 self.level, self.select_level, detail_panel, channel_style=True)
        label = QLabel("Scope:")
        label.setObjectName("analysisFilterLabel")
        level_row.insertWidget(0, label)
        layout.addLayout(level_row)
        channels = ChannelSelector(["Whole", "R", "G", "B"], self.channel)
        channels.channel_changed.connect(self.select_channel)
        layout.addWidget(channels)
        if self.level == "whole":
            self.render_whole(layout)
        else:
            self.render_frame(layout)
        outer.addWidget(detail_panel, 7)
        outer.addWidget(self.summary(), 3)
        for label in detail_panel.findChildren(QLabel):
            if not label.objectName():
                label.setObjectName("analysisPlotSubtitle")
                label.setWordWrap(True)
        self.layout_root.addWidget(self.body)

    def image_report(self, detector):
        """Adapt pooled measurements to the existing image presentation contract."""
        if self.level == "frame" and self.frame_index in self.cache:
            return self.cache[self.frame_index][detector]
        source = getattr(self.result, detector)["targets"]
        report = {}
        offset = self.frame_index - self.result.video_info["start_frame"]
        for channel, data in source.items():
            whole = data["whole"] if self.level == "whole" else data["per_frame"][offset]
            if detector == "chi_square":
                report[channel] = {"whole": whole,
                    "prefix": data["progressive_prefix"] if self.level == "whole" else [],
                    "segments": data["frame_segments"] if self.level == "whole" else []}
            elif detector == "rs":
                report[channel] = {"whole": whole.rs, "payload": whole.payload, "prefix": []}
            elif self.level == "whole":
                report[channel] = {"statistics": data["statistics"], "estimate": whole}
        return report

    def embed_image_detail(self, layout, detail):
        """Reuse image plots, tiles and tables under the shared video controls."""
        content = detail.layout()
        for _ in range(3):
            item = content.takeAt(0)  # image title, channel selector, detail tabs
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout() is not None:
                sublayout = item.layout()
                while sublayout.count():
                    child = sublayout.takeAt(0)
                    if child.widget() is not None:
                        child.widget().hide()
                        child.widget().deleteLater()
                sublayout.deleteLater()
        detail.setObjectName("analysisVideoContent")
        content.setContentsMargins(0, 0, 0, 0)
        scope = "Video" if self.level == "whole" else "Frame"
        for label in detail.findChildren(QLabel):
            text = label.text().replace("Whole Image", f"Whole {scope}").replace("Whole-image", f"Whole-{scope.lower()}")
            if self.level == "whole":
                text = text.replace("Cumulative p-value across raster-order image prefixes",
                                    "Cumulative p-value across frames from the start of the analyzed range")
                text = text.replace("Fixed-length raster-order ranges; values are not cumulative",
                                    "Fixed-length frame ranges; values are not cumulative")
            label.setText(text)
        layout.addWidget(detail)

    def tabs_row(self, layout, options, selected, callback):
        row = QFrame()
        row.setObjectName("analysisDetailTabs")
        row.setLayout(self.buttons(options, selected, callback, row))
        layout.addWidget(row)

    def data(self, detector=None):
        return getattr(self.result, detector or self.detector)["targets"][self.channel]

    def render_whole(self, layout):
        options = []
        if self.detector != "chi_square":
            options.append(("overview", "Distribution" if self.detector == "rs" else "Pair Distributions"))
        options += [("prefix", "Progressive Prefix"), ("segments", "Sliding Segments"), ("raw", "Raw Data")]
        tab = self.tabs[self.detector]
        if tab not in dict(options):
            tab = "prefix"
            self.tabs[self.detector] = tab
        self.tabs_row(layout, options, tab, self.select_tab)
        data = self.data()
        report = self.image_report(self.detector)
        if self.detector == "chi_square":
            detail = ChiSquareDetail(report, self.channel, tab)
            start = self.result.video_info["start_frame"]
            records = (data["frame_segments"] if tab == "segments" else [])
            if tab == "raw":
                detail.raw_table.item(0, 0).setText("Whole Video")
                base = 1 + len(data["progressive_prefix"])
                for i, item in enumerate(data["frame_segments"]):
                    detail.raw_table.item(base + i, 0).setText(f"Frames [{start + item.start}:{start + item.end})")
            else:
                for i, item in enumerate(records):
                    detail.raw_table.item(i, 0).setText(f"Frames [{start + item.start}:{start + item.end})")
            self.embed_image_detail(layout, detail)
            return
        if tab in ("overview", "raw"):
            if self.detector == "rs":
                detail = RSDetail(report, self.channel, "distribution" if tab == "overview" else "raw")
            else:
                detail = SPADetail(report, self.channel, self.result.parameters,
                                   "distribution" if tab == "overview" else "raw")
            self.embed_image_detail(layout, detail)
            if tab == "raw":
                self.range_table(layout, data["progressive_prefix"], "frames", True)
                self.range_table(layout, data["frame_segments"], "frames", False)
            return
        values = data["progressive_prefix" if tab == "prefix" else "frame_segments"]
        labels = [f"{item.percent}%" if tab == "prefix" else self.range_label(item, "frames") for item in values]
        panel = QFrame()
        panel.setObjectName("analysisPlotPanel")
        plot = QVBoxLayout(panel)
        plot.setContentsMargins(12, 10, 12, 10)
        title = QLabel("Progressive Prefix" if tab == "prefix" else "Sliding Segments")
        title.setObjectName("analysisPlotTitle")
        subtitle = QLabel("Estimated embedding rate across cumulative frames" if tab == "prefix"
                          else "Estimated embedding rate within each frame range")
        subtitle.setObjectName("analysisPlotSubtitle")
        plot.addWidget(title)
        plot.addWidget(subtitle)
        series = ((self.channel, COLORS[self.detector], [scalar(self.detector, item) for item in values]),)
        plot.addWidget(PValueLineChart(series, labels))
        plot.addLayout(ChiSquareDetail._build_legend(series))
        layout.addWidget(panel)
        layout.addLayout(self.metrics(data["whole"]))
        self.range_table(layout, values, "frames", tab == "prefix")

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
        spin.setObjectName("analysisVideoFrameInput")
        spin.setRange(info["start_frame"], info["end_frame"] - 1)
        spin.setValue(self.frame_index)
        spin.setKeyboardTracking(False)
        spin.valueChanged.connect(self.select_frame)
        row.addWidget(QLabel("Frame:"))
        row.addWidget(previous)
        row.addWidget(spin)
        row.addWidget(following)
        fps = info["frame_rate"]
        row.addWidget(QLabel(f"Time: {self.frame_index / fps:.3f}s" if fps > 0 else "Time: N/A"))
        row.addStretch()
        layout.addLayout(row)
        options = list({"chi_square": ChiSquareDetail.TABS, "rs": RSDetail.TABS, "spa": SPADetail.TABS}[self.detector])
        options.append(("timeline", "Per-frame Trend"))
        tab = self.frame_tabs[self.detector]
        self.tabs_row(layout, options, tab, self.select_frame_tab)
        if tab == "timeline":
            self.timeline(layout)
            return
        details = self.cache.get(self.frame_index)
        if details is None:
            note = QLabel(self.frame_error or "Loading frame details…")
            note.setObjectName("analysisNote")
            layout.addWidget(note)
            return
        report = details[self.detector]
        if self.detector == "chi_square":
            detail = ChiSquareDetail(report, self.channel, tab)
            if tab == "raw":
                detail.raw_table.item(0, 0).setText("Whole Frame")
        elif self.detector == "rs":
            detail = RSDetail(report, self.channel, tab)
        else:
            detail = SPADetail(report, self.channel, self.result.parameters, tab)
        self.embed_image_detail(layout, detail)

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
        column = QFrame()
        column.setObjectName("analysisSummaryColumn")
        column.setMinimumWidth(330)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for name in NAMES:
            if name == self.detector:
                continue
            report = self.image_report(name)
            if report and self.summary_builder:
                card = self.summary_builder(name, report=report, selected_channel=self.channel)
                scope = QLabel("Whole Video" if self.level == "whole" else f"Frame {self.frame_index}")
                scope.setObjectName("analysisSummaryHint")
                card.layout().insertWidget(1, scope)
                layout.addWidget(card)
            else:
                card = QFrame()
                card.setObjectName("analysisSummaryCard")
                card.setProperty("detectorType", name)
                content = QVBoxLayout(card)
                title = QLabel(NAMES[name])
                title.setObjectName("analysisSummaryTitle")
                content.addWidget(title)
                hint = QLabel(self.frame_error or "Loading frame statistics…")
                hint.setObjectName("analysisSummaryLabel")
                content.addWidget(hint)
                layout.addWidget(card)
        if self.pending_parameters != self.result.parameters:
            note = QLabel("Parameters changed. Run Analysis to apply.")
            note.setObjectName("analysisNote")
            note.setWordWrap(True)
            layout.addWidget(note)
        layout.addStretch()
        return column
