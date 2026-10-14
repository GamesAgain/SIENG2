"""Audio detector detail, composed from the existing image widgets and styles."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QTableWidget

from src.core.analyzer.bit_statistics.rs_analysis import PrefixResult as RSPrefix
from src.gui.features.analyzer.chi_square_detail import (
    ChannelSelector, ChiSquareDetail, PValueLineChart, format_p_value, format_percent,
)
from src.gui.features.analyzer.rs_detail import RSDetail
from src.gui.features.analyzer.spa_detail import SPADetail
from src.gui.features.analyzer.video_detail import VideoDetail, scalar, estimate, COLORS


class AudioDetail(QFrame):
    channel_changed = pyqtSignal(str)
    tab_changed = pyqtSignal(str)

    def __init__(self, result, detector, channel, tab, parent=None):
        super().__init__(parent)
        self.setObjectName("analysisDetailPanel")
        self.setProperty("detectorType", detector)
        self.result, self.detector, self.channel = result, detector, channel
        self.source = getattr(result, detector)[channel]
        options = ([ ("distribution", "Distribution") ] if detector == "rs" else
                   [ ("distribution", "Pair Distributions") ] if detector == "spa" else [])
        options += [("prefix", "Progressive Prefix"), ("segments", "Sliding Segments"), ("raw", "Raw Data")]
        self.tab = tab if tab in dict(options) else options[0][0]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 13, 14, 14)
        layout.setSpacing(11)
        header = QHBoxLayout()
        title = QLabel({"chi_square": "Chi-square Analysis", "rs": "RS Analysis",
                        "spa": "Sample Pair Analysis"}[detector])
        title.setObjectName("analysisPanelTitle")
        badge = QLabel({"chi_square": "PoV", "rs": "M / −M", "spa": "SPA"}[detector])
        badge.setObjectName("analysisPanelBadge")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(badge)
        layout.addLayout(header)
        selector = ChannelSelector(list(getattr(result, detector)), channel)
        selector.channel_changed.connect(self.channel_changed)
        layout.addWidget(selector)
        tabs = QFrame()
        tabs.setObjectName("analysisDetailTabs")
        row = QHBoxLayout(tabs)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, caption in options:
            button = QPushButton(caption)
            button.setObjectName("analysisDetailTab")
            button.setCheckable(True)
            button.setChecked(key == self.tab)
            button.clicked.connect(lambda checked, value=key: checked and self.tab_changed.emit(value))
            group.addButton(button)
            row.addWidget(button)
        row.addStretch()
        layout.addWidget(tabs)
        if detector == "chi_square" or self.tab in ("distribution", "raw"):
            self._image_content(layout)
        else:
            self._range_content(layout)

    def _image_content(self, layout):
        report = getattr(self.result, self.detector)
        if self.detector == "chi_square":
            detail = ChiSquareDetail(report, self.channel, self.tab)
            for row in range(detail.raw_table.rowCount()):
                cell = detail.raw_table.item(row, 0)
                if cell:
                    cell.setText(self._audio_scope(cell.text()))
        elif self.detector == "rs":
            data = self.source
            adapted = {self.channel: {"whole": data["whole"], "payload": data["payload"],
                        "prefix": [RSPrefix(item.percent, item.end, item.measurement.rs)
                                   for item in data["progressive_prefix"]]}}
            detail = RSDetail(adapted, self.channel, "distribution" if self.tab == "distribution" else "raw")
        else:
            detail = SPADetail({self.channel: self.source}, self.channel,
                               self.result.parameters, "distribution" if self.tab == "distribution" else "raw")
        detail.setObjectName("analysisVideoContent")
        content = detail.layout()
        for _ in range(3):  # image header, selector, tabs are supplied above
            item = content.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout() is not None:
                child_layout = item.layout()
                while child_layout.count():
                    child = child_layout.takeAt(0)
                    if child.widget() is not None:
                        child.widget().hide()
                        child.widget().deleteLater()
        content.setContentsMargins(0, 0, 0, 0)
        for label in detail.findChildren(QLabel):
            label.setText(label.text().replace("Whole Image", "Whole Audio")
                          .replace("Whole-image", "Whole-audio")
                          .replace("raster-order image", "time-ordered audio")
                          .replace("pixel", "sample").replace("Pixel", "Sample"))
        for table in detail.findChildren(QTableWidget):
            for column in range(table.columnCount()):
                header = table.horizontalHeaderItem(column)
                if header is not None:
                    header.setText(header.text().replace("Pixels", "Samples")
                                   .replace("Pixel", "Sample"))
        layout.addWidget(detail)
        if self.tab == "raw" and self.detector in ("rs", "spa"):
            self._range_table(layout, self.source["progressive_prefix"], "Prefixes")
            self._range_table(layout, self.source["segments"], "Segments")

    def _audio_scope(self, text):
        rate = self.result.audio_info["sample_rate"]
        if text == "Whole Image":
            return "Whole Audio"
        if "%" in text:
            try:
                percent = int(text.split("–")[1].split("%")[0])
                end = next(item.end for item in self.source["progressive_prefix"]
                           if item.percent == percent)
                return f"{text} · 0–{end / rate:.3f} s"
            except (ValueError, IndexError, StopIteration):
                pass
        if "[" in text and ":" in text:
            try:
                start, end = text.split("[")[1].split(")")[0].split(":")
                return f"{int(start.replace(',', '')) / rate:.3f}–{int(end.replace(',', '')) / rate:.3f} s"
            except (ValueError, IndexError):
                pass
        return text

    def _range_content(self, layout):
        ranges = self.source["progressive_prefix" if self.tab == "prefix" else "segments"]
        rate = self.result.audio_info["sample_rate"]
        panel = QFrame()
        panel.setObjectName("analysisPlotPanel")
        plot = QVBoxLayout(panel)
        plot.setContentsMargins(12, 10, 12, 10)
        title = QLabel("Progressive Prefix" if self.tab == "prefix" else "Sliding Segments")
        title.setObjectName("analysisPlotTitle")
        plot.addWidget(title)
        labels = ([f"{item.percent}%" for item in ranges] if self.tab == "prefix" else
                  [f"{item.start / rate:.1f}s" for item in ranges])
        plot.addWidget(PValueLineChart(((self.channel, COLORS[self.detector],
                                         [scalar(self.detector, item) for item in ranges]),), labels))
        layout.addWidget(panel)
        self._range_table(layout, ranges, None)

    def _range_table(self, layout, ranges, title):
        rate = self.result.audio_info["sample_rate"]
        if title:
            caption = QLabel(title)
            caption.setObjectName("analysisDataTitle")
            layout.addWidget(caption)
        rows = []
        for item in ranges:
            value = estimate(item)
            display = (format_p_value if self.detector == "chi_square" else format_percent)(scalar(self.detector, item))
            rows.append((f"0–{item.percent}%" if item.percent is not None else "Segment",
                         f"{item.start:,}–{item.end:,}",
                         f"{item.start / rate:.3f}–{item.end / rate:.3f}",
                         display, value.status, value.reason or ""))
        layout.addWidget(VideoDetail.table(("Scope", "Samples [start:end)", "Time (s)",
                                             "p-value" if self.detector == "chi_square" else "Embed rate",
                                             "Status", "Reason"), rows, self))
