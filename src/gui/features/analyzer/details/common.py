"""Shared detector formatting and small chart widgets."""

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QLabel, QLayout, QVBoxLayout, QWidget


CHANNEL_COLORS = {
    "Whole": "#CBD5E1",
    "R": "#F87171",
    "G": "#34D399",
    "B": "#60A5FA",
    "L": "#CBD5E1",
}
AUDIO_CHANNEL_COLORS = (
    "#38BDF8",
    "#F59E0B",
    "#A78BFA",
    "#2DD4BF",
    "#FB7185",
    "#84CC16",
)


def format_number(value: float | None, decimals: int = 3) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"


def format_p_value(value: float | None) -> str:
    if value is None:
        return "N/A"
    if 0 < value < 0.000005:
        return "<0.00001"
    return f"{value:.5f}"


def format_integer(value: float | int | None) -> str:
    if value is None:
        return "N/A"
    return f"{int(round(value)):,}"


def format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def channel_color(channel: str) -> str:
    """Return the reference colors plus stable colors for WAV channels."""
    if channel in CHANNEL_COLORS:
        return CHANNEL_COLORS[channel]
    if channel.startswith("CH") and channel[2:].isdigit():
        index = max(0, int(channel[2:]) - 1)
        return AUDIO_CHANNEL_COLORS[index % len(AUDIO_CHANNEL_COLORS)]
    return "#38BDF8"


class PValueLineChart(QWidget):
    """Small dependency-free line chart with a configurable y-axis."""

    def __init__(
        self,
        series,
        labels,
        y_min: float = 0.0,
        y_max: float = 1.0,
        parent=None,
    ):
        super().__init__(parent)
        self.series = series
        self.labels = labels
        self.y_min = y_min
        self.y_max = y_max
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
        for step in range(5):
            ratio = step / 4
            value = self.y_min + ratio * (self.y_max - self.y_min)
            y = plot.bottom() - ratio * plot.height()
            painter.setPen(grid_pen)
            painter.drawLine(plot.left(), int(y), plot.right(), int(y))
            painter.setPen(text_color)
            painter.drawText(4, int(y + 4), f"{value:.2f}")

        painter.setPen(QPen(QColor("#57616C"), 1))
        painter.drawLine(plot.bottomLeft(), plot.bottomRight())
        painter.drawLine(plot.topLeft(), plot.bottomLeft())

        point_count = max(
            (len(values) for _, _, values in self.series),
            default=0,
        )
        if not any(
            value is not None
            for _, _, values in self.series
            for value in values
        ):
            painter.setPen(text_color)
            painter.drawText(
                plot,
                Qt.AlignmentFlag.AlignCenter,
                "N/A - insufficient data",
            )
            return

        x_step = plot.width() / max(1, point_count - 1)
        for _name, color, values in self.series:
            painter.setPen(QPen(QColor(color), 2))
            previous = None
            for index, value in enumerate(values):
                if value is None:
                    previous = None
                    continue
                clamped = min(self.y_max, max(self.y_min, float(value)))
                ratio = (clamped - self.y_min) / (
                    self.y_max - self.y_min
                )
                point = QPointF(
                    plot.left() + index * x_step,
                    plot.bottom() - ratio * plot.height(),
                )
                if previous is not None:
                    painter.drawLine(previous, point)
                painter.setBrush(QColor(color))
                painter.drawEllipse(point, 2.8, 2.8)
                previous = point

        if self.labels:
            if len(self.labels) > 1:
                label_indexes = sorted({
                    round(
                        index * (len(self.labels) - 1)
                        / min(5, len(self.labels) - 1)
                    )
                    for index in range(
                        min(5, len(self.labels) - 1) + 1
                    )
                })
            else:
                label_indexes = [0]

            painter.setPen(text_color)
            for index in label_indexes:
                x = plot.left() + index * x_step
                painter.drawText(
                    int(x - 34),
                    plot.bottom() + 8,
                    68,
                    20,
                    Qt.AlignmentFlag.AlignHCenter
                    | Qt.AlignmentFlag.AlignTop,
                    str(self.labels[index]),
                )


class MetricTile(QFrame):
    """Compact label/value pair used below detector charts."""

    def __init__(
        self,
        label: str,
        value: str,
        accent: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("analysisMetricTile")
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

        name_label = QLabel(label)
        name_label.setObjectName("analysisMetricLabel")
        value_label = QLabel(value)
        value_label.setObjectName("analysisMetricValue")
        value_label.setProperty("accent", accent)
        self.value_label = value_label
        layout.addWidget(name_label)
        layout.addWidget(value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


