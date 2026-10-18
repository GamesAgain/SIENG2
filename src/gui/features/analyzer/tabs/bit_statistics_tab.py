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
    QVBoxLayout,
    QWidget,
)

from src.core.analyzer.models.analysis import AnalysisResult
from src.core.analyzer.parameters import AnalysisParameters
from src.gui.components.gui_utils import create_icon_state
from src.gui.features.analyzer.dialogs.analysis_parameters_dialog import (
    AnalysisParametersDialog,
)
from src.gui.features.analyzer.details.chi_square_detail import (
    ChiSquareDetail,
)
from src.gui.features.analyzer.details.rs_detail import (
    RSDetail,
)
from src.gui.features.analyzer.details.spa_detail import (
    SPADetail,
)
from src.gui.features.analyzer.widgets.detector_button import DetectorButton
from src.path import svg_path


from .assessments import AssessmentMixin
from .summary_cards import SummaryCardsMixin


class BitStatisticsTab(AssessmentMixin, SummaryCardsMixin, QFrame):
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
