"""SPA charts and readable estimate-status widgets."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


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


