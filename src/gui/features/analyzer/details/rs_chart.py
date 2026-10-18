"""RS distribution chart shared by detail and summary views."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget


RS_COLORS = {
    "Regular": "#4096F0",
    "Singular": "#35BC79",
    "Unusable": "#E67D47",
}


class RSDistributionChart(QWidget):
    """Grouped bars for Regular, Singular and Unusable fractions."""

    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.result = result
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
        if self.result.total_groups == 0:
            painter.setPen(text_color)
            painter.drawText(
                plot,
                Qt.AlignmentFlag.AlignCenter,
                "N/A - no complete groups",
            )
            return

        for step in range(5):
            value = step / 4
            y = plot.bottom() - value * plot.height()
            painter.setPen(grid_pen)
            painter.drawLine(plot.left(), int(y), plot.right(), int(y))
            painter.setPen(text_color)
            painter.drawText(4, int(y + 4), f"{value:.2f}")

        groups = (
            ("M", (self.result.RM, self.result.SM, self.result.UM)),
            (
                "−M",
                (
                    self.result.R_negM,
                    self.result.S_negM,
                    self.result.U_negM,
                ),
            ),
        )
        group_width = min(210.0, plot.width() / 2.8)
        bar_gap = 6.0
        bar_width = (group_width - bar_gap * 2) / 3
        group_centers = (
            plot.left() + plot.width() * 0.28,
            plot.left() + plot.width() * 0.72,
        )
        colors = tuple(RS_COLORS.values())
        for (name, values), center in zip(groups, group_centers):
            left = center - group_width / 2
            for index, value in enumerate(values):
                fraction = (
                    0.0 if value is None else min(1.0, max(0.0, value))
                )
                height = fraction * plot.height()
                rect = QRectF(
                    left + index * (bar_width + bar_gap),
                    plot.bottom() - height,
                    bar_width,
                    height,
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(colors[index]))
                painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(text_color)
            painter.drawText(
                int(center - 30),
                plot.bottom() + 8,
                60,
                20,
                Qt.AlignmentFlag.AlignHCenter
                | Qt.AlignmentFlag.AlignTop,
                name,
            )


