from collections.abc import Mapping
from typing import Any

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.core.analyzer.models.analysis import AnalysisResult
from src.core.analyzer.models.png import PNGDetectorDecision
from src.core.analyzer.models.wav import WAVRSDecision, WAVSPADecision
from src.core.analyzer.parameters import AnalysisParameters
from src.gui.components.gui_utils import create_icon_pixmap, create_icon_state
from src.gui.features.analyzer.dialogs.analysis_parameters_dialog import (
    AnalysisParametersDialog,
)
from src.gui.features.analyzer.details.chi_square_detail import (
    ChiSquareDetail,
    format_integer,
    format_p_value,
    format_percent,
)
from src.gui.features.analyzer.details.rs_detail import (
    RSDetail,
    RSDistributionChart,
)
from src.gui.features.analyzer.details.spa_detail import (
    SPACountChart,
    SPADetail,
)
from src.gui.features.analyzer.widgets.channel_selector import ChannelSelector
from src.gui.features.analyzer.widgets.detector_button import DetectorButton
from src.path import svg_path


class BitStatisticsTab(QFrame):
    """Own the bit-statistics result currently displayed by the GUI."""

    parameters_changed = pyqtSignal(object)
    frame_detail_requested = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.analysis_parameters = AnalysisParameters()
        self.analysis_result: AnalysisResult | None = None
        self.active_detector = "chi_square"
        self.active_channel: str | None = None
        self.active_frame_index: int | None = None
        self.avi_scope = "whole"
        self.frame_details: dict[str, dict[int, object]] = {
            "chi_square": {},
            "rs": {},
        }
        self.frame_detail_loading: set[tuple[str, int]] = set()
        self.frame_detail_errors: dict[tuple[str, int], str] = {}
        self.detail_tabs = {
            "chi_square": "prefix",
            "rs": "distribution",
            "spa": "distribution",
        }
        self.avi_frame_tabs = {
            "chi_square": "timeline",
            "rs": "timeline",
            "spa": "timeline",
        }
        self.results_widget: QWidget | None = None
        self.detail_widget: QWidget | None = None
        self.avi_summary_layout: QVBoxLayout | None = None
        self._setup_ui()
        self.clear_analysis_result()

    def _setup_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setObjectName("transparentScroll")

        content = QWidget()
        content.setObjectName("transparentScrollContent")
        layout = QVBoxLayout(content)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        title_row = QHBoxLayout()
        title = QLabel("Statistical Analyzer")
        title.setObjectName("pageTitle")
        title.setProperty("compactTitle", True)

        self.parameter_button = QPushButton("Parameters")
        self.parameter_button.setObjectName("SecondaryBtn")
        self.parameter_button.setIcon(
            create_icon_state(
                str(svg_path("adjustments-horizontal.svg")),
                color_normal="#94A3B8",
            )
        )
        self.parameter_button.setIconSize(QSize(16, 16))
        self.parameter_button.clicked.connect(self.open_parameters_dialog)

        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(self.parameter_button)
        layout.addLayout(title_row)

        layout.addWidget(self._build_detector_selector())

        self.results_container = QFrame()
        self.results_container.setObjectName("bitStatisticsResults")
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setSizeConstraint(
            QLayout.SizeConstraint.SetMinimumSize
        )
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.results_container)
        layout.addStretch()

        scroll_area.setWidget(content)
        outer_layout.addWidget(scroll_area)

    def _build_detector_selector(self) -> QFrame:
        """Build the mutually exclusive Chi-square, RS and SPA cards."""
        section = QFrame()
        layout = QHBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.detector_group = QButtonGroup(self)
        self.detector_group.setExclusive(True)
        self.detector_buttons = {
            "chi_square": DetectorButton(
                "Chi-square",
                "Tests paired-value balance in the analyzed samples",
                ("PoV", "p-value"),
                "chart-histogram.svg",
                "chi",
            ),
            "rs": DetectorButton(
                "RS Analysis",
                "Measures regular and singular group changes",
                ("R / S / U", "Payload"),
                "activity.svg",
                "rs",
            ),
            "spa": DetectorButton(
                "Sample Pair Analysis",
                "Estimates embedding from adjacent sample pairs",
                ("Sample pairs", "Rate"),
                "link.svg",
                "spa",
            ),
        }

        for button_id, (name, button) in enumerate(
            self.detector_buttons.items()
        ):
            self.detector_group.addButton(button, button_id)
            button.clicked.connect(
                lambda checked, detector=name: checked
                and self._select_detector(detector)
            )
            layout.addWidget(button, 1)

        self.detector_buttons[self.active_detector].setChecked(True)
        return section

    def _select_detector(self, detector: str) -> None:
        """Keep the selected available detector for the next result view."""
        button = self.detector_buttons.get(detector)
        if button is None or not button.isEnabled():
            return

        self.active_detector = detector
        button.setChecked(True)
        self._update_channels()
        self._update_frame()
        self._render_results()
        if self.avi_scope == "frame" and self.active_detector in self.frame_details:
            self._request_frame_detail(self.active_detector, self.active_frame_index)

    def _active_channels(self) -> Mapping[str, Any]:
        """Return channel results for the selected detector and format."""
        return self._channels_for_detector(self.active_detector)

    def _channels_for_detector(
        self,
        detector: str,
    ) -> Mapping[str, Any]:
        """Return one detector's channel mapping from the current result."""
        if self.analysis_result is None:
            return {}

        detector_result = getattr(
            self.analysis_result.bit_statistics,
            detector,
        )
        if detector_result is None:
            return {}
        if hasattr(detector_result, "channels"):
            return detector_result.channels
        if hasattr(detector_result, "video"):
            return detector_result.video
        return {}

    def _frames_for_detector(self, detector: str):
        """Return per-frame AVI summaries for one detector."""
        if self.analysis_result is None:
            return ()
        detector_result = getattr(
            self.analysis_result.bit_statistics,
            detector,
        )
        return tuple(getattr(detector_result, "frames", ()))

    def _update_channels(self) -> None:
        """Show the channels produced by the currently selected detector."""
        channels = self._active_channels()
        if self.active_channel not in channels:
            self.active_channel = next(iter(channels), None)

    def _update_frame(self) -> None:
        frames = self._frames_for_detector(self.active_detector)
        frame_indexes = {frame.frame_index for frame in frames}
        if not frames:
            self.active_frame_index = None
        elif self.active_frame_index not in frame_indexes:
            self.active_frame_index = frames[0].frame_index

    def _select_channel(self, channel: str) -> None:
        """Store a channel emitted by the selector if it still exists."""
        if channel not in self._active_channels():
            return
        self.active_channel = channel
        self._render_results()

    def _select_avi_scope(self, scope: str) -> None:
        """Switch between the two video workspaces used by the reference UI."""
        if scope not in ("whole", "frame") or scope == self.avi_scope:
            return
        self.avi_scope = scope
        self._render_results()
        if scope == "frame" and self.active_detector in self.frame_details:
            self._request_frame_detail(self.active_detector, self.active_frame_index)

    def _select_avi_frame_tab(self, tab_name: str) -> None:
        self.avi_frame_tabs[self.active_detector] = tab_name
        self._render_results()

    def _select_frame(self, frame_index: int) -> None:
        frames = self._frames_for_detector(self.active_detector)
        if frame_index not in {frame.frame_index for frame in frames}:
            return
        self.active_frame_index = frame_index
        # Keep the detail widget alive so spin-box mouse events finish normally.
        if (
            self.detail_widget is not None
            and hasattr(self.detail_widget, "set_selected_frame")
            and getattr(
                self.detail_widget,
                "selected_frame",
                None,
            ) != frame_index
        ):
            self.detail_widget.set_selected_frame(frame_index)
        if self.avi_scope == "frame" and self.avi_summary_layout is not None:
            self._populate_avi_summary(self.avi_summary_layout)
        if self.avi_scope == "frame" and self.active_detector in self.frame_details:
            self._request_frame_detail(self.active_detector, frame_index)

    def _request_frame_detail(
        self,
        detector: str,
        frame_index: int,
    ) -> None:
        """Request one uncached AVI frame detail from the page worker."""
        if frame_index is None:
            return
        if detector not in self.frame_details:
            return
        if frame_index in self.frame_details[detector]:
            return
        key = (detector, frame_index)
        if key in self.frame_detail_loading:
            return
        self.frame_detail_loading.add(key)
        self.frame_detail_errors.pop(key, None)
        if self.detail_widget is not None and hasattr(
            self.detail_widget,
            "set_frame_detail_state",
        ):
            self.detail_widget.set_frame_detail_state(
                loading=True,
                error=None,
            )
        self.frame_detail_requested.emit(detector, frame_index)

    def set_frame_detail(self, detector: str, result: object) -> None:
        """Cache a completed on-demand frame detail and update its panel."""
        if detector not in self.frame_details:
            return
        frame_index = getattr(result, "frame_index", None)
        if not isinstance(frame_index, int):
            raise TypeError("Frame detail must contain an integer frame_index.")
        key = (detector, frame_index)
        self.frame_details[detector][frame_index] = result
        self.frame_detail_loading.discard(key)
        self.frame_detail_errors.pop(key, None)
        if (
            detector == self.active_detector
            and frame_index == self.active_frame_index
            and self.detail_widget is not None
            and hasattr(self.detail_widget, "set_frame_detail_result")
        ):
            self.detail_widget.set_frame_detail_result(result)

    def set_frame_detail_error(
        self,
        detector: str,
        frame_index: int,
        message: str,
    ) -> None:
        """Finish a failed frame request without discarding video results."""
        key = (detector, frame_index)
        self.frame_detail_loading.discard(key)
        self.frame_detail_errors[key] = message
        if (
            detector == self.active_detector
            and frame_index == self.active_frame_index
            and self.detail_widget is not None
            and hasattr(self.detail_widget, "set_frame_detail_state")
        ):
            self.detail_widget.set_frame_detail_state(
                loading=False,
                error=message,
            )

    def _select_detail_tab(self, tab_name: str) -> None:
        """Remember the selected Chi-square tab while rebuilding its view."""
        self.detail_tabs[self.active_detector] = tab_name
        self._render_results()

    def _update_detector_availability(self) -> None:
        """Enable only detectors that returned data for the current file."""
        available = []
        for name, button in self.detector_buttons.items():
            if self.analysis_result is None:
                has_result = True
            else:
                has_result = getattr(
                    self.analysis_result.bit_statistics,
                    name,
                ) is not None
            button.setEnabled(has_result)
            button.setToolTip(
                "" if has_result else "Not available for the selected file."
            )
            if has_result:
                available.append(name)

        if available and self.active_detector not in available:
            self.active_detector = available[0]
        if self.active_detector in self.detector_buttons:
            self.detector_buttons[self.active_detector].setChecked(True)

    def _render_results(self) -> None:
        """Replace the empty state or selected detector detail view."""
        if self.results_widget is not None:
            self.results_layout.removeWidget(self.results_widget)
            self.results_widget.hide()
            self.results_widget.deleteLater()
        self.detail_widget = None
        self.avi_summary_layout = None

        if self.analysis_result is None:
            self.results_widget = self._build_empty_state()
        else:
            self.results_widget = self._build_results_layout()

        self.results_layout.addWidget(self.results_widget)

    def _build_results_layout(self) -> QWidget:
        """Build the reference two-column detail and summary layout."""
        results = QWidget()
        layout = QHBoxLayout(results)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        channels = self._active_channels()
        frames = self._frames_for_detector(self.active_detector)
        is_avi = self.analysis_result.file.format == "AVI"
        if self.active_channel not in channels:
            self.active_channel = next(iter(channels), None)
        self._update_frame()

        if self.active_channel is None:
            detail = self._build_ready_state()
        elif self.active_detector == "chi_square":
            detail = ChiSquareDetail(
                report=channels,
                selected_channel=self.active_channel,
                file_format=self.analysis_result.file.format,
                selected_tab=("frames" if is_avi and self.avi_scope == "frame"
                              else self.detail_tabs.get("chi_square", "prefix")),
                frames=frames if is_avi and self.avi_scope == "frame" else (),
                video_scope=self.avi_scope if is_avi else None,
                video_frame_tab=self.avi_frame_tabs["chi_square"],
                selected_frame=self.active_frame_index,
                frame_details=self.frame_details["chi_square"],
                frame_detail_loading=self.frame_detail_loading,
                frame_detail_errors=self.frame_detail_errors,
                parent=results,
            )
            detail.channel_changed.connect(self._select_channel)
            detail.tab_changed.connect(self._select_detail_tab)
            detail.frame_changed.connect(self._select_frame)
            detail.frame_detail_requested.connect(
                lambda frame_index: self._request_frame_detail(
                    "chi_square",
                    frame_index,
                )
            )
            detail.frame_view_tab_changed.connect(self._select_avi_frame_tab)
        elif self.active_detector == "rs":
            detail = RSDetail(
                report=channels,
                selected_channel=self.active_channel,
                selected_tab=("frames" if is_avi and self.avi_scope == "frame"
                              else self.detail_tabs.get("rs", "distribution")),
                frames=frames if is_avi and self.avi_scope == "frame" else (),
                video_scope=self.avi_scope if is_avi else None,
                video_frame_tab=self.avi_frame_tabs["rs"],
                selected_frame=self.active_frame_index,
                frame_details=self.frame_details["rs"],
                frame_detail_loading=self.frame_detail_loading,
                frame_detail_errors=self.frame_detail_errors,
                parent=results,
            )
            detail.channel_changed.connect(self._select_channel)
            detail.tab_changed.connect(self._select_detail_tab)
            detail.frame_changed.connect(self._select_frame)
            detail.frame_detail_requested.connect(
                lambda frame_index: self._request_frame_detail(
                    "rs",
                    frame_index,
                )
            )
            detail.frame_view_tab_changed.connect(self._select_avi_frame_tab)
        else:
            detail = SPADetail(
                report=channels,
                selected_channel=self.active_channel,
                parameters=self.analysis_result.parameters,
                selected_tab=("frames" if is_avi and self.avi_scope == "frame"
                              else self.detail_tabs.get("spa", "distribution")),
                frames=frames if is_avi and self.avi_scope == "frame" else (),
                video_scope=self.avi_scope if is_avi else None,
                video_frame_tab=self.avi_frame_tabs["spa"],
                selected_frame=self.active_frame_index,
                parent=results,
            )
            detail.channel_changed.connect(self._select_channel)
            detail.tab_changed.connect(self._select_detail_tab)
            detail.frame_changed.connect(self._select_frame)
            detail.frame_view_tab_changed.connect(self._select_avi_frame_tab)
        self.detail_widget = detail
        detail_column = QWidget(results)
        detail_layout = QVBoxLayout(detail_column)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(10)
        if is_avi:
            detail_layout.addWidget(self._build_avi_scope_selector())
        detail_layout.addWidget(detail)
        layout.addWidget(detail_column, 7)

        summary_column = QFrame(results)
        summary_column.setObjectName("analysisSummaryColumn")
        summary_column.setMinimumWidth(330)
        summary_layout = QVBoxLayout(summary_column)
        summary_layout.setSizeConstraint(
            QLayout.SizeConstraint.SetMinimumSize
        )
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(10)

        if is_avi:
            self.avi_summary_layout = summary_layout
            self._populate_avi_summary(summary_layout)
        else:
            summary_layout.addWidget(
                self._build_summary_card(
                    self.active_detector,
                    expanded=True,
                )
            )
            for detector in ("chi_square", "rs", "spa"):
                if detector != self.active_detector and self._channels_for_detector(detector):
                    summary_layout.addWidget(self._build_summary_card(detector))
            summary_layout.addWidget(self._build_context_card())
            summary_layout.addStretch()
        layout.addWidget(summary_column, 3)
        return results

    def _populate_avi_summary(self, layout: QVBoxLayout) -> None:
        """Keep other-detector summaries on the selected AVI frame."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        layout.addWidget(
            self._build_summary_card(
                self.active_detector,
                expanded=True,
            )
        )
        for detector in ("chi_square", "rs", "spa"):
            if detector != self.active_detector and self._channels_for_detector(detector):
                layout.addWidget(self._build_summary_card(detector))
        layout.addWidget(self._build_context_card())
        layout.addStretch()

    def _build_avi_scope_selector(self) -> QFrame:
        """Match the reference video's Whole Video / Per Frame control."""
        row = QFrame()
        row.setObjectName("analysisDetailPanel")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(5)
        label = QLabel("Scope:")
        label.setObjectName("analysisFilterLabel")
        layout.addWidget(label)
        group = QButtonGroup(row)
        group.setExclusive(True)
        for scope, title in (("whole", "Whole Video"), ("frame", "Per Frame")):
            button = QPushButton(title)
            button.setObjectName("analysisChannelButton")
            button.setCheckable(True)
            button.setChecked(scope == self.avi_scope)
            button.clicked.connect(
                lambda checked, value=scope: checked and self._select_avi_scope(value)
            )
            group.addButton(button)
            layout.addWidget(button)
        layout.addStretch()
        return row

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

    def _build_assessment_section(
        self,
        detector: str,
        decision,
        *,
        frame_scope: bool,
    ) -> QFrame:
        """Append the calibrated interpretation below the raw card summary."""
        section = QFrame()
        section.setObjectName("analysisAssessmentSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(7)

        if frame_scope:
            title = QLabel("Analysis Summary")
            title.setObjectName("analysisSummaryTitle")
            layout.addWidget(title)
            note = QLabel(
                "This frame is shown as a descriptive measurement. The "
                "calibrated assessment applies to the whole video, so an "
                "individual frame is not classified."
            )
            note.setObjectName("analysisChiSquareEvidence")
            note.setWordWrap(True)
            layout.addWidget(note)
            return section

        if detector == "chi_square":
            message, state = self._chi_square_summary(decision)
            note = QLabel(message)
            note.setObjectName("analysisChiSummaryText")
            note.setProperty("assessmentState", state)
            note.setWordWrap(True)
            layout.addWidget(note)
            return section

        title = QLabel("Analysis Summary")
        title.setObjectName("analysisSummaryTitle")
        layout.addWidget(title)

        if isinstance(decision, WAVSPADecision):
            outcome = {
                "Stego": "Evidence",
                "Clean": "No evidence",
                "Unknown": "Unavailable",
            }[decision.classification]
            values = (
                ("Assessment", outcome),
                (
                    "Evaluated rate",
                    format_percent(decision.evaluated_rate),
                ),
                ("Detected range", "Whole audio"),
            )
            note = self._build_wav_spa_decision_note(decision)
        elif isinstance(decision, WAVRSDecision):
            outcome = {
                "Stego": "Evidence",
                "Clean": "No evidence",
                "Unknown": "Unavailable",
            }[decision.classification]
            values = (
                ("Assessment", outcome),
                (
                    "Evaluated rate",
                    format_percent(decision.evaluated_rate),
                ),
                ("Detected range", "Whole audio"),
            )
            note = self._build_wav_rs_decision_note(decision)
        elif decision is not None:
            values = (
                ("Assessment", self._decision_outcome(decision)),
                ("Measured value", self._decision_score_text(decision)),
                (
                    "Detected range",
                    self._decision_range_text(detector, decision),
                ),
            )
            note = self._build_decision_note(
                decision,
                include_values=False,
            )
        else:
            values = (
                ("Assessment", "Unavailable"),
                ("Measured value", "N/A"),
                ("Detected range", "N/A"),
            )
            message = (
                "The available WAV Chi-square experiment did not produce a "
                "usable decision rule. Raw measurements remain available."
                if self.analysis_result.file.format == "WAV"
                and detector == "chi_square"
                else "No calibrated assessment is available for this result."
            )
            note = QLabel(message)
            note.setObjectName("analysisChiSquareEvidence")
            note.setWordWrap(True)

        layout.addWidget(self._build_summary_metrics(values, detector))
        layout.addWidget(note)
        return section

    def _chi_square_summary(self, decision) -> tuple[str, str]:
        """Return one concise sentence and its visual state."""
        if decision is None:
            return (
                "Unable to assess: no validated Chi-square rule is available "
                "for this audio.",
                "unavailable",
            )
        if decision.status not in {"evidence_found", "no_evidence"}:
            return (
                "Unable to assess: "
                + (decision.reason or "the measurement could not be assessed."),
                "unavailable",
            )

        if decision.status == "no_evidence":
            return "No matching traces of LSB replacement were found.", "clear"

        if isinstance(decision, PNGDetectorDecision):
            end = decision.observed_end_percent
            if end is not None:
                return (
                    "Possible traces of sequential LSB replacement were found "
                    f"in the first 0–{end:g}% of the image.",
                    "evidence",
                )
        if getattr(decision, "score_prefix_percent", None) is not None:
            return (
                "Possible LSB replacement traces were found. The cumulative "
                "result alone cannot identify the embedding order or range.",
                "evidence",
            )
        return (
            "Possible traces of LSB replacement were found; the affected "
            "range could not be estimated.",
            "evidence",
        )

    def _decision_for_detector(self, detector: str):
        """Return a calibrated decision when the format provides one."""
        if self.analysis_result is None:
            return None
        result = getattr(
            self.analysis_result.bit_statistics,
            detector,
            None,
        )
        return getattr(result, "decision", None)

    def _build_active_assessment_card(self) -> QFrame:
        """Build the top-right interpretation for the selected detector."""
        decision = self._decision_for_detector(self.active_detector)
        if isinstance(decision, WAVSPADecision):
            return self._build_wav_spa_decision_banner(decision)
        if isinstance(decision, WAVRSDecision):
            return self._build_wav_rs_decision_banner(decision)
        if decision is not None:
            return self._build_decision_banner(decision)
        if self.analysis_result.file.format == "WAV":
            return self._build_wav_threshold_placeholder(
                self.active_detector
            )
        return self._build_unavailable_assessment_card(
            self.active_detector
        )

    def _build_decision_banner(self, decision) -> QFrame:
        """Show an interpreted assessment at the top of the summary column."""
        panel = QFrame()
        panel.setObjectName("analysisSummaryCard")
        panel.setProperty("detectorType", decision.detector)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        is_png = isinstance(decision, PNGDetectorDecision)
        detector_name = {
            "chi_square": "Chi-square",
            "rs": "RS Analysis",
            "spa": "Sample Pair Analysis",
        }.get(decision.detector, decision.detector)
        title = QLabel(f"{detector_name} Assessment")
        title.setObjectName("analysisSummaryTitle")
        layout.addWidget(title)
        layout.addWidget(self._build_summary_metrics(
            (
                ("Assessment", self._decision_outcome(decision)),
                ("Measured value", self._decision_score_text(decision)),
                (
                    "Detected range",
                    self._decision_range_text(decision.detector, decision),
                ),
            ),
            decision.detector,
        ))
        layout.addWidget(
            self._build_decision_note(decision, include_values=False)
        )
        scope_note = QLabel(
            "The assessment profile was selected on 50 original images and evaluated on "
            "50 independent holdout images. Accuracy on other image sources "
            "has not been measured."
            if is_png else
            "The assessment profile was tested on 30-frame, 160x120 uncompressed RGB AVI files. "
            "Accuracy on other AVI files has not been measured."
        )
        scope_note.setObjectName("analysisChiSquareEvidence")
        scope_note.setWordWrap(True)
        layout.addWidget(scope_note)
        return panel

    def _build_wav_spa_decision_banner(self, decision: WAVSPADecision) -> QFrame:
        """Show the interpreted WAV SPA result without exposing the cutoff."""
        panel = QFrame()
        panel.setObjectName("analysisSummaryCard")
        panel.setProperty("detectorType", "spa")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        title = QLabel("Sample Pair Analysis Assessment")
        title.setObjectName("analysisSummaryTitle")
        layout.addWidget(title)
        outcome = {
            "Stego": "Evidence",
            "Clean": "No evidence",
            "Unknown": "Unavailable",
        }[decision.classification]
        layout.addWidget(self._build_summary_metrics(
            (
                ("Assessment", outcome),
                ("Estimated embed rate", format_percent(decision.evaluated_rate)),
                ("Detected range", "Whole audio"),
            ),
            "spa",
        ))
        layout.addWidget(self._build_wav_spa_decision_note(decision))
        return panel

    def _build_wav_rs_decision_banner(self, decision: WAVRSDecision) -> QFrame:
        """Show the interpreted WAV RS result without exposing the cutoff."""
        panel = QFrame()
        panel.setObjectName("analysisSummaryCard")
        panel.setProperty("detectorType", "rs")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        title = QLabel("RS Analysis Assessment")
        title.setObjectName("analysisSummaryTitle")
        layout.addWidget(title)
        outcome = {
            "Stego": "Evidence",
            "Clean": "No evidence",
            "Unknown": "Unavailable",
        }[decision.classification]
        layout.addWidget(self._build_summary_metrics(
            (
                ("Assessment", outcome),
                ("Estimated embed rate", format_percent(decision.evaluated_rate)),
                ("Detected range", "Whole audio"),
            ),
            "rs",
        ))
        layout.addWidget(self._build_wav_rs_decision_note(decision))
        return panel

    @staticmethod
    def _build_wav_rs_decision_note(decision: WAVRSDecision) -> QLabel:
        if decision.classification == "Stego":
            message = (
                "The measured RS embedding rate is consistent with traces of "
                "LSB replacement in the analyzed audio."
            )
        elif decision.classification == "Clean":
            message = (
                "The measured RS embedding rate did not indicate traces of "
                "LSB replacement. This result does not prove that the audio "
                "contains no hidden data."
            )
        else:
            message = "Unable to assess: " + decision.reason
        if decision.classification != "Unknown":
            message += " Original 44.1 kHz, 5-second Test set: 2/30 cover files were flagged, and 10/30 had no valid RS score."
        note = QLabel(message)
        note.setObjectName("analysisChiSquareEvidence")
        note.setWordWrap(True)
        return note

    @staticmethod
    def _build_wav_spa_decision_note(decision: WAVSPADecision) -> QLabel:
        if decision.classification == "Stego":
            message = (
                "The SPA estimate is consistent with traces of random LSB "
                "replacement across the analyzed audio."
            )
        elif decision.classification == "Clean":
            message = (
                "The SPA estimate did not indicate traces of random LSB "
                "replacement. This result does not prove that the audio "
                "contains no hidden data."
            )
        else:
            message = "Unable to assess: " + decision.reason
        if decision.classification != "Unknown":
            message += " Original 44.1 kHz, 5-second Test set: 2/30 cover files were flagged, and 13/30 had no valid SPA score."
        note = QLabel(message)
        note.setObjectName("analysisChiSquareEvidence")
        note.setWordWrap(True)
        return note

    def _build_wav_threshold_placeholder(self, detector: str) -> QFrame:
        """Explain when WAV has no usable calibrated assessment."""
        names = {
            "chi_square": "Chi-square",
            "spa": "Sample Pair Analysis",
        }
        panel = QFrame()
        panel.setObjectName("analysisSummaryCard")
        panel.setProperty("detectorType", detector)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        title = QLabel("WAV Chi-square Assessment")
        title.setObjectName("analysisSummaryTitle")
        layout.addWidget(title)
        layout.addWidget(self._build_summary_metrics(
            (
                ("Detector", names.get(detector, detector)),
                ("Assessment", "Unable to assess"),
                ("Detected range", "N/A"),
            ),
            detector,
        ))

        note = QLabel(
            "The available WAV Chi-square experiment did not produce a usable "
            "decision rule. Raw measurements and progressive-prefix results "
            "remain available for inspection."
        )
        note.setObjectName("analysisChiSquareEvidence")
        note.setWordWrap(True)
        layout.addWidget(note)
        return panel

    def _build_unavailable_assessment_card(self, detector: str) -> QFrame:
        """Keep the active detector represented when no profile is present."""
        names = {
            "chi_square": "Chi-square",
            "rs": "RS Analysis",
            "spa": "Sample Pair Analysis",
        }
        panel = QFrame()
        panel.setObjectName("analysisSummaryCard")
        panel.setProperty("detectorType", detector)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        title = QLabel(f"{names[detector]} Assessment")
        title.setObjectName("analysisSummaryTitle")
        layout.addWidget(title)
        layout.addWidget(self._build_summary_metrics(
            (
                ("Assessment", "Unavailable"),
                ("Measured value", "N/A"),
                ("Detected range", "N/A"),
            ),
            detector,
        ))
        note = QLabel(
            "No calibrated assessment is available for this result. Raw "
            "detector measurements remain available for inspection."
        )
        note.setObjectName("analysisChiSquareEvidence")
        note.setWordWrap(True)
        layout.addWidget(note)
        return panel

    @classmethod
    def _build_decision_note(
        cls,
        decision,
        include_values: bool = True,
    ) -> QLabel:
        """Describe evidence without claiming that the file is clean/stego."""
        method = cls._method_text(decision.expected_method)
        scope = cls._scope_text(decision.scope)
        channel = (
            ChannelSelector.display_name(decision.selected_channel)
            if decision.selected_channel
            else "N/A"
        )
        score = cls._decision_score_text(decision)
        values_text = (
            f" Measured value: {score}."
            if include_values
            else ""
        )

        if decision.status == "evidence_found":
            text = (
                f"Evidence consistent with {method} was found. "
                f"Channel {channel}; {scope}.{values_text}"
            )
            if decision.reason:
                text += f" {decision.reason}"
        elif decision.status == "no_evidence":
            text = (
                f"The measured result did not indicate evidence matching "
                f"{method}. Channel {channel}; {scope}."
                f"{values_text}"
            )
        else:
            reason = decision.reason or "No usable score is available."
            text = f"Assessment unavailable: {reason}"

        note = QLabel(text)
        note.setObjectName("analysisChiSquareEvidence")
        note.setWordWrap(True)
        return note

    @staticmethod
    def _method_text(method: str) -> str:
        return {
            "lsb_replacement": "LSB replacement",
            "sequential_lsb_replacement": "sequential LSB replacement",
            "shuffled_lsb_replacement": "shuffled LSB replacement",
            "random_lsb_replacement": "random LSB replacement",
        }.get(method, method.replace("_", " "))

    @staticmethod
    def _scope_text(scope: str) -> str:
        if scope == "whole_image":
            return "whole image"
        if scope == "initial_segment_run":
            return "initial run of 5% image segments at 1% steps"
        if scope == "whole":
            return "whole video"
        if scope == "max_temporal_prefix":
            return "maximum p-value across cumulative video prefixes"
        if scope.startswith("prefix_"):
            try:
                percent = int(scope.removeprefix("prefix_"))
            except ValueError:
                return scope
            return f"first {percent}% of video"
        return scope

    @staticmethod
    def _decision_outcome(decision) -> str:
        if decision.status == "evidence_found":
            return "Evidence"
        if decision.status == "no_evidence":
            return "No evidence"
        return "Unavailable"

    def _decision_range_text(self, detector: str, decision) -> str:
        """Describe where the decision score was observed, when known."""
        if decision.status != "evidence_found":
            return "N/A"
        if decision.scope == "whole_image":
            return "Whole image"
        if decision.scope == "whole":
            return "Whole video"
        if decision.scope == "initial_segment_run":
            end = getattr(decision, "observed_end_percent", None)
            if end is not None:
                return f"Initial 0–{end:g}%"
            return "Initial image region"
        if decision.scope == "max_temporal_prefix":
            percent = getattr(decision, "score_prefix_percent", None)
            if percent is not None:
                return f"First {percent}% of video"
            return "Video prefix"
        return self._scope_text(decision.scope).capitalize()

    def _build_frame_assessment_card(self) -> QFrame:
        """Explain that the selected AVI frame is descriptive only."""
        names = {
            "chi_square": "Chi-square",
            "rs": "RS Analysis",
            "spa": "Sample Pair Analysis",
        }
        panel = QFrame()
        panel.setObjectName("analysisSummaryCard")
        panel.setProperty("detectorType", self.active_detector)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        title = QLabel(f"{names[self.active_detector]} Frame Summary")
        title.setObjectName("analysisSummaryTitle")
        layout.addWidget(title)
        layout.addWidget(self._build_summary_metrics(
            (
                ("Frame", str(self.active_frame_index)),
                ("Assessment", "Descriptive only"),
                ("Detected range", "N/A"),
            ),
            self.active_detector,
        ))
        note = QLabel(
            "This frame shows its raw detector measurement. The calibrated "
            "assessment applies to the whole video, so this frame is not "
            "classified on its own."
        )
        note.setObjectName("analysisChiSquareEvidence")
        note.setWordWrap(True)
        layout.addWidget(note)
        return panel

    @staticmethod
    def _decision_score_text(decision) -> str:
        if decision.score is None:
            return "N/A"
        if decision.detector == "chi_square":
            return BitStatisticsTab._assessment_p_value_text(
                decision.score
            )
        return format_percent(decision.score)

    @staticmethod
    def _assessment_p_value_text(value: float) -> str:
        """Keep tiny calibrated p-values distinguishable from zero."""
        numeric = float(value)
        if numeric == 0.0:
            return "0"
        if abs(numeric) < 0.00001:
            return f"{numeric:.6e}"
        return f"{numeric:.6f}"

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
        details = QLabel(
            f"File  {self.analysis_result.file.name}\n"
            f"Format  {self.analysis_result.file.format}\n"
            f"Chi min expected  {parameters.min_expected:g}\n"
            f"Prefix / segment  {parameters.prefix_step}% / "
            f"{parameters.segment_percent}% @ "
            f"{parameters.segment_step}%\n"
            f"SPA j / min pairs  {parameters.spa_j} / "
            f"{parameters.spa_min_pairs}"
        )
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

    @staticmethod
    def _build_empty_state() -> QFrame:
        """Build the same waiting panel used by the reference GUI."""
        empty = QFrame()
        empty.setObjectName("analysisEmptyState")
        layout = QVBoxLayout(empty)
        layout.setContentsMargins(20, 55, 20, 55)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Waiting for analysis")
        title.setObjectName("analysisEmptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel(
            "Select a PNG, WAV or AVI file and click Run Analysis."
        )
        hint.setObjectName("analysisEmptyHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(hint)
        return empty

    def _build_ready_state(self) -> QFrame:
        """Keep results available until detector detail views are added."""
        state = QFrame()
        state.setObjectName("analysisEmptyState")
        layout = QVBoxLayout(state)
        layout.setContentsMargins(20, 55, 20, 55)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Analysis complete")
        title.setObjectName("analysisEmptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel(
            f"{self.analysis_result.file.format} bit-statistics results "
            "are ready."
        )
        hint.setObjectName("analysisEmptyHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(hint)
        return state

    def set_analysis_result(self, result: AnalysisResult) -> None:
        """Store and display a completed result from the analyzer core."""
        if not isinstance(result, AnalysisResult):
            raise TypeError("result must be an AnalysisResult.")

        self.analysis_result = result
        self.avi_scope = "whole"
        self.active_frame_index = None
        self.frame_details = {"chi_square": {}, "rs": {}}
        self.frame_detail_loading.clear()
        self.frame_detail_errors.clear()
        self._update_detector_availability()
        self._update_channels()
        self._update_frame()
        self._render_results()

    def clear_analysis_result(self) -> None:
        """Forget the old file result and restore the waiting state."""
        self.analysis_result = None
        self.avi_scope = "whole"
        self.active_detector = "chi_square"
        self.active_channel = None
        self.active_frame_index = None
        self.frame_details = {"chi_square": {}, "rs": {}}
        self.frame_detail_loading.clear()
        self.frame_detail_errors.clear()
        self._update_detector_availability()
        self._update_channels()
        self._render_results()

    def open_parameters_dialog(self) -> None:
        """Keep edited parameters only when the user saves valid values."""
        dialog = AnalysisParametersDialog(self.analysis_parameters, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.analysis_parameters = dialog.parameters
            self.parameters_changed.emit(self.analysis_parameters)
