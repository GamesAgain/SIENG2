from pathlib import Path
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QLayout,
    QFileDialog,
    QMessageBox,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.gui.components.gui_utils import create_icon_state, create_icon_pixmap
from src.gui.features.analyzer.analysis_parameters_dialog import (
    AnalysisParameters,
    AnalysisParametersDialog,
)
from src.gui.features.analyzer.chi_square_detail import (
    ChiSquareDetail,
    format_integer,
    format_p_value,
    format_percent,
)
from src.gui.features.analyzer.rs_detail import RSDetail, RSDistributionChart
from src.gui.features.analyzer.spa_detail import SPACountChart, SPADetail
from src.path import svg_path
from src.gui.features.analyzer.analysis_export import export_analysis


CHI_SQUARE_PREFIX_EVIDENCE_THRESHOLD = 0.50


class DetectorButton(QPushButton):
    """Selectable detector card with an icon, description and badges."""

    def __init__(self, detector_name, description, badges, icon_path, detector_type, parent=None):
        super().__init__(parent)
        self.setObjectName("DetectorBtn")
        self.setProperty("detectorType", detector_type)
        self.setCheckable(True)
        self.setAccessibleName(detector_name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(96)
        self.setMaximumWidth(320)

        colors = {"chi": "#38BDF8", "rs": "#32CA85", "spa": "#B47AFA"}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 13, 12, 13)
        layout.setSpacing(12)

        icon_label = QLabel()
        icon_label.setPixmap(create_icon_pixmap(str(icon_path), colors[detector_type], 28))
        icon_label.setFixedSize(28, 28)
        layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        detector_name_label = QLabel(detector_name)
        detector_name_label.setObjectName("detectorNameLabel")
        description_label = QLabel(description)
        description_label.setObjectName("detectorDescriptionLabel")
        description_label.setWordWrap(True)
        text_layout.addWidget(detector_name_label)
        text_layout.addWidget(description_label)

        badge_layout = QHBoxLayout()
        badge_layout.setSpacing(6)
        for text in badges:
            badge = QLabel(text)
            badge.setObjectName("detectorBadge")
            badge_layout.addWidget(badge)
        badge_layout.addStretch()
        text_layout.addLayout(badge_layout)
        layout.addLayout(text_layout, 1)

        # Clicking text, badges or the icon selects the enclosing button.
        for label in self.findChildren(QLabel):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def sizeHint(self) -> QSize:
        return self.layout().sizeHint().expandedTo(QSize(0, 96))


class BitStatisticsTab(QFrame):
    """Bit-statistics content for the Analyzer page."""

    parameters_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.analysis_parameters = AnalysisParameters()
        self.analysis_result = None
        self.active_detector = "chi_square"
        self.active_channel = None
        self.detail_tabs = {
            "chi_square": "prefix",
            "rs": "distribution",
            "spa": "distribution",
        }
        self.results_widget = None
        self.setup_ui()

    def setup_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setObjectName("transparentScroll")

        content = QWidget()
        content.setObjectName("transparentScrollContent")
        content_layout = QVBoxLayout(content)
        content_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(12)

        content_layout.addWidget(self.build_title())
        content_layout.addWidget(self.build_detector_selector())
        self.results_container = QFrame()
        self.results_container.setObjectName("bitStatisticsResults")
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self.results_container)
        content_layout.addStretch()

        scroll_area.setWidget(content)
        outer_layout.addWidget(scroll_area)
        self._render_results()

    def build_title(self) -> QFrame:
        title = QFrame()
        layout = QHBoxLayout(title)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title_label = QLabel("Statistical Analyzer")
        title_label.setObjectName("pageTitle")
        title_label.setProperty("compactTitle", True)

        self.parameter_button = QPushButton("Parameters")
        self.parameter_button.setObjectName("SecondaryBtn")
        self.parameter_button.setIcon(create_icon_state(
            str(svg_path("adjustments-horizontal.svg")),
            color_normal="#94A3B8",
        ))
        self.parameter_button.clicked.connect(self.open_parameters_dialog)

        self.export_json_button = QPushButton("Export JSON")
        self.export_json_button.setObjectName("SecondaryBtn")
        self.export_json_button.setProperty("accent", "green")
        self.export_json_button.setEnabled(False)
        self.export_json_button.clicked.connect(self.export_json)
        self.export_json_button.setIcon(create_icon_state(
            str(svg_path("download.svg")),
            color_normal="#34D399",
            color_hover="#6EE7B7",
        ))

        for button in (self.parameter_button, self.export_json_button):
            button.setIconSize(QSize(16, 16))

        layout.addWidget(title_label)
        layout.addStretch()
        layout.addWidget(self.parameter_button)
        layout.addWidget(self.export_json_button)

        return title

    def open_parameters_dialog(self) -> None:
        """Open the parameter editor and keep values only after Save."""
        dialog = AnalysisParametersDialog(self.analysis_parameters, self)
        if dialog.exec() == AnalysisParametersDialog.DialogCode.Accepted:
            self.analysis_parameters = dialog.parameters
            self.parameters_changed.emit(self.analysis_parameters)
            self._render_results()

    def export_json(self) -> None:
        """Export the completed snapshot, independent of pending settings."""
        result = self.analysis_result
        if result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export analysis", Path(result.file_path).stem + "_sieng2_results.json",
            "JSON files (*.json)",
        )
        if not path:
            return
        if Path(path).resolve() == Path(result.file_path).resolve():
            QMessageBox.warning(self, "Export JSON", "Choose a different path from the source image.")
            return
        try:
            export_analysis(result, path)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Export JSON", str(exc))

    def set_analysis_result(self, result) -> None:
        """Store one complete result bundle for the detail UI added next."""
        self.analysis_result = result
        self.export_json_button.setEnabled(True)
        report = self._active_report()
        self.active_channel = next(iter(report), None)
        self._render_results()

    def clear_analysis_result(self) -> None:
        """Remove results when the selected input file changes."""
        self.analysis_result = None
        self.export_json_button.setEnabled(False)
        self.active_channel = None
        self._render_results()

    def build_detector_selector(self) -> QFrame:
        """Build three mutually exclusive detector buttons."""
        detector_section = QFrame()
        layout = QHBoxLayout(detector_section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.detector_group = QButtonGroup(self)
        self.detector_group.setExclusive(True)
        self.detector_buttons = {
            "chi_square": DetectorButton(
                "Chi-square", "PoV equalization across image regions",
                ["Sequential LSB", "PoV / p-value", "Regions"],
                svg_path("chart-histogram.svg"), "chi",
            ),
            "rs": DetectorButton(
                "RS Analysis", "R/S group shifts under LSB randomization",
                ["Random LSB", "R / S / U", "Payload estimate"],
                svg_path("activity.svg"), "rs",
            ),
            "spa": DetectorButton(
                "Sample Pair Analysis", "Adjacent-pair shifts estimate embedding rate",
                ["Random LSB", "Sample pairs", "Rate estimate"],
                svg_path("link.svg"), "spa",
            ),
        }
        for button_id, button in enumerate(self.detector_buttons.values()):
            self.detector_group.addButton(button, button_id)
            layout.addWidget(button, 1)
        for detector_name, button in self.detector_buttons.items():
            button.clicked.connect(
                lambda checked, name=detector_name: checked
                and self.select_detector(name)
            )
        # Keep cards compact on wide pages; use the available width on smaller pages.
        layout.addStretch()
        self.detector_buttons["chi_square"].setChecked(True)
        return detector_section

    def select_detector(self, detector_name: str) -> None:
        """Switch the detail panel while keeping a compatible channel."""
        if detector_name not in self.detector_buttons:
            return
        self.active_detector = detector_name
        self.detector_buttons[detector_name].setChecked(True)
        report = self._active_report()
        if self.active_channel not in report:
            self.active_channel = next(iter(report), None)
        self._render_results()

    def _select_channel(self, channel: str) -> None:
        if channel in self._active_report():
            self.active_channel = channel
            self._render_results()

    def _select_detail_tab(self, tab_name: str) -> None:
        self.detail_tabs[self.active_detector] = tab_name
        self._render_results()

    def _active_report(self):
        if self.analysis_result is None:
            return {}
        return getattr(self.analysis_result, self.active_detector)

    def _render_results(self) -> None:
        if not hasattr(self, "results_layout"):
            return
        if self.results_widget is not None:
            self.results_layout.removeWidget(self.results_widget)
            self.results_widget.hide()
            self.results_widget.deleteLater()

        if self.analysis_result is None:
            self.results_widget = self._build_empty_state()
        else:
            self.results_widget = self._build_results_layout()
        self.results_layout.addWidget(self.results_widget)

    @staticmethod
    def _build_empty_state() -> QFrame:
        empty = QFrame()
        empty.setObjectName("analysisEmptyState")
        layout = QVBoxLayout(empty)
        layout.setContentsMargins(20, 55, 20, 55)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Waiting for analysis")
        title.setObjectName("analysisEmptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("Select a PNG image and click Run Analysis.")
        hint.setObjectName("analysisEmptyHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(hint)
        return empty

    def _build_results_layout(self) -> QWidget:
        results = QWidget()
        layout = QHBoxLayout(results)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        report = self._active_report()
        if self.active_channel not in report:
            self.active_channel = next(iter(report), None)

        if self.active_detector == "chi_square":
            detail = ChiSquareDetail(
                report,
                self.active_channel,
                self.detail_tabs.get("chi_square", "prefix"),
            )
            detail.channel_changed.connect(self._select_channel)
            detail.tab_changed.connect(self._select_detail_tab)
            self.chi_square_detail = detail
        elif self.active_detector == "rs":
            detail = RSDetail(
                report,
                self.active_channel,
                self.detail_tabs.get("rs", "distribution"),
            )
            detail.channel_changed.connect(self._select_channel)
            detail.tab_changed.connect(self._select_detail_tab)
            self.rs_detail = detail
        else:
            detail = SPADetail(
                report,
                self.active_channel,
                self.analysis_result.parameters,
                self.detail_tabs.get("spa", "distribution"),
            )
            detail.channel_changed.connect(self._select_channel)
            detail.tab_changed.connect(self._select_detail_tab)
            self.spa_detail = detail
        layout.addWidget(detail, 7)

        summary_column = QFrame()
        summary_column.setObjectName("analysisSummaryColumn")
        # Keep summaries beside the detail; narrow windows scroll horizontally.
        summary_column.setMinimumWidth(330)
        summary_layout = QVBoxLayout(summary_column)
        summary_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(10)
        for detector in ("chi_square", "rs", "spa"):
            if detector != self.active_detector:
                summary_layout.addWidget(self._build_summary_card(detector))
        summary_layout.addWidget(self._build_context_card())
        summary_layout.addStretch()
        layout.addWidget(summary_column, 3)
        return results

    def _build_summary_card(self, detector: str) -> QFrame:
        names = {
            "chi_square": "Chi-square",
            "rs": "RS Analysis",
            "spa": "Sample Pair Analysis",
        }
        report = getattr(self.analysis_result, detector)
        channel = self.active_channel if self.active_channel in report else next(iter(report))
        data = report[channel]

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
                str(svg_path("activity.svg" if detector == "rs" else "link.svg")),
                "#32CA85" if detector == "rs" else "#B47AFA", 20,
            ))
            header.addWidget(icon)
        title = QLabel(names[detector])
        title.setObjectName("analysisSummaryTitle")
        open_button = QPushButton("Open ›")
        open_button.setObjectName("analysisOpenDetector")
        open_button.clicked.connect(lambda: self.select_detector(detector))
        header.addWidget(title)
        header.addStretch()
        if detector == "rs":
            badge = QLabel("Regular / Singular")
            badge.setObjectName("analysisPanelBadge")
            header.addWidget(badge)
        header.addWidget(open_button)
        layout.addLayout(header)
        channel_label = QLabel(f"Channel: {channel}")
        channel_label.setObjectName("analysisSummaryLabel")
        layout.addWidget(channel_label)

        if detector == "rs":
            compact_chart = RSDistributionChart(data["whole"])
            compact_chart.setFixedHeight(150)
            layout.addWidget(compact_chart)
            legend = QLabel(
                '<span style="color:#4096F0">●</span> Regular&nbsp;&nbsp;'
                '<span style="color:#35BC79">●</span> Singular&nbsp;&nbsp;'
                '<span style="color:#E67D47">●</span> Unusable'
            )
            legend.setObjectName("analysisRSSummaryLegend")
            legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(legend)
        elif detector == "spa":
            compact_chart = SPACountChart(data["statistics"], bin_count=16)
            compact_chart.setFixedHeight(120)
            layout.addWidget(compact_chart)
            range_hint = QLabel("Odd differences 1-31 (first 16 bins)")
            range_hint.setObjectName("analysisSummaryHint")
            range_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(range_hint)
            legend = QLabel(
                '<span style="color:#B47AFA">●</span> X: even member larger&nbsp;&nbsp;'
                '<span style="color:#38C681">●</span> Y: odd member larger'
            )
            legend.setObjectName("analysisSPASummaryLegend")
            legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(legend)

        if detector == "chi_square":
            whole = data["whole"]
            peak = self._peak_prefix(data["prefix"])
            peak_p_value = peak.chi_square.p_value if peak else None
            has_clear_prefix = (
                peak_p_value is not None
                and peak_p_value >= CHI_SQUARE_PREFIX_EVIDENCE_THRESHOLD
            )
            values = (
                (
                    "Peak p-value",
                    format_p_value(peak_p_value),
                ),
                ("Peak range", f"0–{peak.percent}%" if has_clear_prefix else "N/A"),
                ("Whole p-value", format_p_value(whole.p_value)),
            )
        elif detector == "rs":
            payload = data["payload"]
            whole = data["whole"]
            m_difference = self._format_percentage_point_difference(
                whole.RM, whole.SM
            )
            negative_m_difference = self._format_percentage_point_difference(
                whole.R_negM, whole.S_negM
            )
            values = (
                ("Estimated \nembed rate", format_percent(payload.embedding_rate)),
                (
                    "Estimated \nchanged samples",
                    format_integer(payload.expected_changed_samples),
                )
            )
        else:
            estimate = data["estimate"]
            statistics = data["statistics"]
            displayed_rate = (
                estimate.embedding_rate
                if estimate.status == "estimated"
                else None
            )
            values = (
                ("Estimated embed rate", format_percent(displayed_rate)),
                ("Estimated bits", format_integer(estimate.estimated_payload_bits)),
                ("Changed samples", format_integer(estimate.expected_changed_samples)),
            )
        layout.addWidget(self._build_summary_metrics(values, detector))
        if detector == "chi_square":
            if peak_p_value is None:
                evidence_text = "Insufficient valid PoV pairs."
                evidence_state = "unavailable"
            elif has_clear_prefix:
                evidence_text = "Clear PoV-equality prefix in the selected channel."
                evidence_state = "clear"
            else:
                evidence_text = (
                    "No clear PoV-equality prefix at the calibrated threshold."
                )
                evidence_state = "low"
            evidence_note = QLabel(evidence_text)
            evidence_note.setObjectName("analysisChiSquareEvidence")
            evidence_note.setProperty("evidenceState", evidence_state)
            evidence_note.setWordWrap(True)
            layout.addWidget(evidence_note)
        elif detector == "rs":
            snapshot_widget = QWidget()
            snapshot_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed
            )

            snapshot_layout = QHBoxLayout(snapshot_widget)
            snapshot_layout.setContentsMargins(0, 0, 0, 0)
            snapshot_layout.setSpacing(8)

            m_snapshot = QLabel(
                f"M: R {format_percent(whole.RM)}, S {format_percent(whole.SM)}"
            )
            mNeg_snapshot = QLabel(
                f"−M: R {format_percent(whole.R_negM)}, S {format_percent(whole.S_negM)}"
            )

            m_snapshot.setObjectName("analysisRSSnapshot")
            mNeg_snapshot.setObjectName("analysisRSSnapshot")

            # ให้ tile ขยายเต็มพื้นที่
            m_snapshot.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed
            )
            mNeg_snapshot.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed
            )

            # แบ่งพื้นที่ 50 / 50
            snapshot_layout.addWidget(m_snapshot, 1)
            snapshot_layout.addWidget(mNeg_snapshot, 1)

            layout.addWidget(snapshot_widget)
        elif detector == "spa":
            pair_row = QHBoxLayout()
            pair_label = QLabel("Pair count")
            pair_label.setObjectName("analysisSummaryMetricLabel")
            pair_value = QLabel(format_integer(statistics.pair_count))
            pair_value.setObjectName("analysisSummaryPairValue")
            pair_row.addWidget(pair_label)
            pair_row.addWidget(pair_value)
            layout.addLayout(pair_row)
        if detector in ("rs", "spa"):
            estimate = data["payload"] if detector == "rs" else data["estimate"]
            if estimate.embedding_rate is None:
                message = "Estimate unavailable; inspect counts and model assumptions."
            elif estimate.estimated_payload_bits is None:
                message = "Out-of-range mathematical rate; payload unavailable."
            elif detector == "rs":
                message = (
                    "Estimated percentage of carrier samples used for random "
                    "LSB replacement."
                )
            else:
                message = (
                    "Estimated percentage of carrier samples used for random "
                    "LSB replacement; not a detection probability."
                )
            estimate_note = QLabel(message)
            estimate_note.setObjectName("analysisSummaryLabel")
            estimate_note.setWordWrap(True)
            layout.addWidget(estimate_note)
        return card

    @staticmethod
    def _build_summary_metrics(values, detector: str) -> QFrame:
        """Show three summary values side by side with one accented value."""
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
            column_layout.setContentsMargins(0 if index == 0 else 8, 0, 8, 0)
            column_layout.setSpacing(4)
            label = QLabel(label_text)
            label.setObjectName("analysisSummaryMetricLabel")
            label.setWordWrap(True)
            value = QLabel(value_text)
            value.setObjectName("analysisSummaryMetricValue")
            if index == 0:
                accents = {"chi_square": "cyan", "rs": "green", "spa": "purple"}
                value.setProperty("accent", accents[detector])
            column_layout.addWidget(label)
            column_layout.addWidget(value)
            row.addWidget(column, 1)
        return metrics

    @staticmethod
    def _format_percentage_point_difference(regular, singular) -> str:
        if regular is None or singular is None:
            return "N/A"
        return f"{(regular - singular) * 100:+.1f} pp"

    @staticmethod
    def _peak_prefix(prefix_results):
        """Return the end of the strongest p-value plateau shown at 5 decimals."""
        available = [
            item for item in prefix_results
            if item.chi_square.p_value is not None
        ]
        if not available:
            return None
        raw_peak = max(item.chi_square.p_value for item in available)
        if raw_peak < 0.000005:
            return max(
                available,
                key=lambda item: (item.chi_square.p_value, item.percent),
            )
        displayed_peak = round(raw_peak, 5)
        return max(
            (item for item in available
             if round(item.chi_square.p_value, 5) == displayed_peak),
            key=lambda item: item.percent,
        )

    def _build_context_card(self) -> QFrame:
        parameters = self.analysis_result.parameters
        card = QFrame()
        card.setObjectName("analysisContextCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(5)
        title = QLabel("Analysis Context")
        title.setObjectName("analysisSummaryTitle")
        details = QLabel(
            f"SHA-256  {self.analysis_result.file_fingerprint.sha256[:12]}…\n"
            f"Chi min expected  {parameters.min_expected:g}\n"
            f"Prefix / segment  {parameters.prefix_step}% / "
            f"{parameters.segment_percent}% @ {parameters.segment_step}%\n"
            f"SPA j / min pairs  {parameters.spa_j} / {parameters.spa_min_pairs}"
        )
        details.setObjectName("analysisContextText")
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(title)
        layout.addWidget(details)
        details.setWordWrap(True)
        if parameters != self.analysis_parameters:
            pending = QLabel("Parameters changed. Run Analysis to apply. Export keeps the displayed results' settings.")
            pending.setObjectName("analysisNote")
            pending.setWordWrap(True)
            layout.addWidget(pending)
        return card
