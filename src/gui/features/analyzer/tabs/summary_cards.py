"""Detector metric cards and the file-context card."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLayout, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from src.core.analyzer.models.wav import WAVRSDecision, WAVSPADecision
from src.gui.components.gui_utils import create_icon_pixmap
from src.gui.features.analyzer.details.common import (
    format_integer, format_p_value, format_percent,
)
from src.gui.features.analyzer.details.rs_chart import RSDistributionChart
from src.gui.features.analyzer.details.spa_widgets import SPACountChart
from src.gui.features.analyzer.widgets.channel_selector import ChannelSelector
from src.path import svg_path


class SummaryCardsMixin:
    def _threshold_context_lines(self) -> list[str]:
        """Describe the frozen rules attached to the displayed analysis."""
        file_format = self.analysis_result.file.format
        heading = "Decision thresholds"
        if file_format == "AVI" and getattr(self, "avi_scope", "whole") == "frame":
            heading += " (whole video)"
        lines = [heading]
        for detector, name in (
            ("chi_square", "Chi-square"),
            ("rs", "RS"),
            ("spa", "SPA"),
        ):
            decision = self._decision_for_detector(detector)
            if decision is None:
                label = (
                    "calibrated p > 1.0 (unusable)"
                    if file_format == "WAV" and detector == "chi_square"
                    else "Unavailable"
                )
                lines.append(f"{name}  {label}")
                continue

            threshold = getattr(decision, "threshold", None)
            if threshold is None:
                threshold = getattr(decision, "threshold_rate", None)
            if threshold is None:
                lines.append(f"{name}  Unavailable")
                continue

            if detector == "chi_square":
                if file_format == "PNG":
                    rule = f"initial segment p >= {threshold:.9g}"
                else:
                    rule = f"max prefix p > {threshold:.9g}"
            else:
                rule = f"whole embed rate > {threshold * 100:.9g}%"

            status = getattr(decision, "status", None)
            if status is None:
                status = getattr(decision, "classification", None)
            if status not in {"evidence_found", "no_evidence", "Stego", "Clean"}:
                rule += " (not applied)"
            lines.append(f"{name}  {rule}")
        return lines

    def _build_summary_card(
        self,
        detector: str,
        *,
        expanded: bool = False,
    ) -> QFrame:
        """Build a detector card, optionally with its assessment below."""
        names = {
            "chi_square": "Chi-square",
            "rs": "RS Analysis",
            "spa": "Sample Pair Analysis",
        }
        report = self._channels_for_detector(detector)
        channel = (
            self.active_channel
            if self.active_channel in report
            else next(iter(report))
        )
        channel_result = report[channel]
        whole = getattr(channel_result, "whole", channel_result)
        decision = self._decision_for_detector(detector)
        frame_scope = (
            self.analysis_result.file.format == "AVI"
            and self.avi_scope == "frame"
        )
        if frame_scope:
            selected_frame = next(
                (frame for frame in self._frames_for_detector(detector)
                 if frame.frame_index == self.active_frame_index),
                None,
            )
            if selected_frame is not None:
                whole = selected_frame.channels[channel]
            decision = None

        card = QFrame()
        card.setObjectName("analysisSummaryCard")
        card.setProperty("detectorType", detector)
        layout = QVBoxLayout(card)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(8)

        header = QHBoxLayout()
        if detector in ("rs", "spa"):
            icon = QLabel()
            icon.setPixmap(create_icon_pixmap(
                str(svg_path(
                    "activity.svg" if detector == "rs" else "link.svg"
                )),
                "#32CA85" if detector == "rs" else "#B47AFA",
                20,
            ))
            header.addWidget(icon)
        title = QLabel(names[detector])
        title.setObjectName("analysisSummaryTitle")
        open_button = QPushButton("Open ›")
        open_button.setObjectName("analysisOpenDetector")
        open_button.clicked.connect(
            lambda: self._select_detector(detector)
        )
        header.addWidget(title)
        header.addStretch()
        if detector == "rs":
            badge = QLabel("Regular / Singular")
            badge.setObjectName("analysisPanelBadge")
            header.addWidget(badge)
        if not expanded:
            header.addWidget(open_button)
        layout.addLayout(header)

        channel_label = QLabel(
            f"Channel: {ChannelSelector.display_name(channel)}"
        )
        channel_label.setObjectName("analysisSummaryLabel")
        layout.addWidget(channel_label)
        if frame_scope:
            scope_label = QLabel(f"Frame {self.active_frame_index}")
            scope_label.setObjectName("analysisSummaryHint")
            layout.addWidget(scope_label)

        if detector == "rs":
            chart = RSDistributionChart(whole.rs)
            chart.setFixedHeight(150)
            layout.addWidget(chart)
            legend = QLabel(
                '<span style="color:#4096F0">●</span> Regular&nbsp;&nbsp;'
                '<span style="color:#35BC79">●</span> Singular&nbsp;&nbsp;'
                '<span style="color:#E67D47">●</span> Unusable'
            )
            legend.setObjectName("analysisRSSummaryLegend")
            legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(legend)
        elif detector == "spa":
            chart = SPACountChart(whole.statistics, bin_count=16)
            chart.setFixedHeight(120)
            layout.addWidget(chart)
            range_hint = QLabel("Odd differences 1–31 (first 16 bins)")
            range_hint.setObjectName("analysisSummaryHint")
            range_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(range_hint)
            legend = QLabel(
                '<span style="color:#B47AFA">●</span> X: even member larger'
                '&nbsp;&nbsp;'
                '<span style="color:#38C681">●</span> Y: odd member larger'
            )
            legend.setObjectName("analysisSPASummaryLegend")
            legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(legend)

        if detector == "chi_square":
            if frame_scope:
                values = (
                    ("Frame p-value", format_p_value(whole.p_value)),
                    ("Valid pairs", format_integer(whole.valid_pairs)),
                    ("Samples", format_integer(whole.sample_count)),
                )
            else:
                peak = self._peak_prefix(channel_result.prefix)
                peak_p_value = peak.analysis.p_value if peak else None
                values = (
                    ("Peak p-value", format_p_value(peak_p_value)),
                    (
                        "Peak range",
                        f"0–{peak.percent}%" if peak else "N/A",
                    ),
                    ("Whole p-value", format_p_value(whole.p_value)),
                )
        elif detector == "rs":
            payload = whole.payload
            values = (
                (
                    "Estimated\nembed rate",
                    format_percent(payload.embedding_rate),
                ),
                (
                    "Estimated\nchanged samples",
                    format_integer(payload.expected_changed_samples),
                ),
            )
        else:
            estimate = whole.estimate
            displayed_rate = (
                estimate.embedding_rate
                if estimate.status == "estimated"
                else None
            )
            values = (
                (
                    "Estimated embed rate",
                    format_percent(displayed_rate),
                ),
                (
                    "Estimated bits",
                    format_integer(estimate.estimated_payload_bits),
                ),
                (
                    "Changed samples",
                    format_integer(estimate.expected_changed_samples),
                ),
            )
        layout.addWidget(self._build_summary_metrics(values, detector))

        if detector == "chi_square":
            if frame_scope:
                note = QLabel(
                    "Per-frame measurement only; the calibrated assessment "
                    "applies to the whole video."
                )
                note.setObjectName("analysisChiSquareEvidence")
                note.setWordWrap(True)
                layout.addWidget(note)
            elif decision is not None and not expanded:
                layout.addWidget(
                    self._build_decision_note(
                        decision,
                        include_values=False,
                    )
                )
            elif decision is None:
                note = QLabel(
                    "Peak prefix is descriptive. The locked WAV Chi-square "
                    "experiment does not provide a usable evidence decision."
                    if self.analysis_result.file.format == "WAV"
                    else "Peak prefix is descriptive; no calibrated decision "
                    "profile is available for this format."
                )
                note.setObjectName("analysisChiSquareEvidence")
                note.setWordWrap(True)
                layout.addWidget(note)
        elif detector == "rs":
            self._add_rs_snapshot(layout, whole)
            if not expanded:
                layout.addWidget(
                    self._build_rs_estimate_note(whole.payload)
                )
            if not expanded and isinstance(decision, WAVRSDecision):
                layout.addWidget(self._build_wav_rs_decision_note(decision))
            elif not expanded and decision is not None:
                layout.addWidget(self._build_decision_note(decision))
        else:
            pair_row = QHBoxLayout()
            pair_label = QLabel("Pair count")
            pair_label.setObjectName("analysisSummaryMetricLabel")
            pair_value = QLabel(format_integer(whole.statistics.pair_count))
            pair_value.setObjectName("analysisSummaryPairValue")
            pair_row.addWidget(pair_label)
            pair_row.addWidget(pair_value)
            layout.addLayout(pair_row)
            if not expanded and isinstance(decision, WAVSPADecision):
                layout.addWidget(self._build_wav_spa_decision_note(decision))
            elif not expanded and decision is not None:
                layout.addWidget(self._build_decision_note(decision))
        if expanded:
            layout.addWidget(
                self._build_assessment_section(
                    detector,
                    decision,
                    frame_scope=frame_scope,
                )
            )
        return card

    @staticmethod
    def _build_summary_metrics(values, detector: str) -> QFrame:
        metrics = QFrame()
        metrics.setObjectName("analysisSummaryMetrics")
        row = QHBoxLayout(metrics)
        row.setContentsMargins(0, 10, 0, 4)
        row.setSpacing(0)
        for index, (label_text, value_text) in enumerate(values):
            column = QFrame()
            column.setObjectName("analysisSummaryMetric")
            column.setProperty("divider", index < len(values) - 1)
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(
                0 if index == 0 else 8,
                0,
                8,
                0,
            )
            column_layout.setSpacing(4)
            label = QLabel(label_text)
            label.setObjectName("analysisSummaryMetricLabel")
            label.setWordWrap(True)
            value = QLabel(value_text)
            value.setObjectName("analysisSummaryMetricValue")
            if index == 0:
                accents = {
                    "chi_square": "cyan",
                    "rs": "green",
                    "spa": "purple",
                }
                value.setProperty("accent", accents[detector])
            column_layout.addWidget(label)
            column_layout.addWidget(value)
            row.addWidget(column, 1)
        return metrics

    @staticmethod
    def _add_rs_snapshot(layout: QVBoxLayout, measurement) -> None:
        snapshot = QWidget()
        snapshot.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        row = QHBoxLayout(snapshot)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        result = measurement.rs
        labels = (
            QLabel(
                f"M: R {format_percent(result.RM)}, "
                f"S {format_percent(result.SM)}"
            ),
            QLabel(
                f"−M: R {format_percent(result.R_negM)}, "
                f"S {format_percent(result.S_negM)}"
            ),
        )
        for label in labels:
            label.setObjectName("analysisRSSnapshot")
            label.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            row.addWidget(label, 1)
        layout.addWidget(snapshot)

    @staticmethod
    def _build_rs_estimate_note(estimate) -> QLabel:
        if estimate.embedding_rate is None:
            message = (
                "Estimate unavailable; inspect counts and model assumptions."
            )
        elif estimate.estimated_payload_bits is None:
            message = "Out-of-range mathematical rate; payload unavailable."
        else:
            message = (
                "Estimated percentage of carrier samples used for random "
                "LSB replacement."
            )
        note = QLabel(message)
        note.setObjectName("analysisSummaryLabel")
        note.setWordWrap(True)
        return note

    @staticmethod
    def _peak_prefix(prefix_results):
        """Return the end of the strongest displayed p-value plateau."""
        available = [
            item
            for item in prefix_results
            if item.analysis.p_value is not None
        ]
        if not available:
            return None
        raw_peak = max(item.analysis.p_value for item in available)
        if raw_peak < 0.000005:
            return max(
                available,
                key=lambda item: (item.analysis.p_value, item.percent),
            )
        displayed_peak = round(raw_peak, 5)
        return max(
            (
                item
                for item in available
                if round(item.analysis.p_value, 5) == displayed_peak
            ),
            key=lambda item: item.percent,
        )

    def _build_context_card(self) -> QFrame:
        """Show the analyzed file and immutable parameter snapshot."""
        parameters = self.analysis_result.parameters
        card = QFrame()
        card.setObjectName("analysisContextCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(5)
        title = QLabel("Analysis Context")
        title.setObjectName("analysisSummaryTitle")
        details = QLabel("\n".join((
            f"File  {self.analysis_result.file.name}",
            f"Format  {self.analysis_result.file.format}",
            f"Chi min expected  {parameters.min_expected:g}",
            f"Prefix / segment  {parameters.prefix_step}% / "
            f"{parameters.segment_percent}% @ {parameters.segment_step}%",
            f"SPA j / min pairs  {parameters.spa_j} / {parameters.spa_min_pairs}",
            "",
            *self._threshold_context_lines(),
        )))
        details.setObjectName("analysisContextText")
        details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        details.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(details)
        if parameters != self.analysis_parameters:
            pending = QLabel(
                "Parameters changed. Run Analysis to apply."
            )
            pending.setObjectName("analysisNote")
            pending.setWordWrap(True)
            layout.addWidget(pending)
        return card

