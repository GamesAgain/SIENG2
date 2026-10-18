"""Calibrated decision text and assessment cards."""

from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from src.core.analyzer.models.avi import AVIDetectorDecision
from src.core.analyzer.models.png import PNGDetectorDecision
from src.core.analyzer.models.wav import WAVRSDecision, WAVSPADecision
from src.gui.features.analyzer.details.common import format_percent
from src.gui.features.analyzer.widgets.channel_selector import ChannelSelector

from .chi_curve_pattern import initial_pattern_end_percent


class AssessmentMixin:
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
            pattern = None
            curve_end = None
            file_format = self.analysis_result.file.format
            chi_result = self.analysis_result.bit_statistics.chi_square
            if file_format == "AVI":
                pattern = getattr(
                    chi_result,
                    "pattern", None,
                )
            elif file_format in {"PNG", "WAV"}:
                channels = chi_result.channels
                channel = next(
                    (name for name in ("Whole", "L", "CH1") if name in channels),
                    None,
                )
                if channel is not None:
                    curve_end = initial_pattern_end_percent(channels[channel])
            message, state = self._chi_square_summary(
                decision, pattern, curve_end=curve_end,
                file_format=file_format,
            )
            note = QLabel(message)
            note.setObjectName("analysisChiSummaryText")
            note.setProperty("assessmentState", state)
            note.setWordWrap(True)
            layout.addWidget(note)
            return section

        if detector in {"rs", "spa"}:
            message, state = self._rs_spa_summary(
                decision, self.analysis_result.file.format
            )
            note = QLabel(message)
            note.setObjectName("analysisChiSummaryText")
            note.setProperty("assessmentState", state)
            note.setWordWrap(True)
            layout.addWidget(note)
            return section

        raise ValueError(f"Unknown detector: {detector}")

    @staticmethod
    def _rs_spa_summary(decision, file_format: str) -> tuple[str, str]:
        """Describe the calibrated whole-file RS/SPA result in one sentence."""
        medium = {"PNG": "image", "AVI": "video", "WAV": "audio"}.get(
            file_format, "file"
        )
        if decision is None:
            return "Unable to assess: no validated decision is available.", "unavailable"
        if isinstance(decision, (WAVRSDecision, WAVSPADecision)):
            status = {
                "Stego": "evidence_found",
                "Clean": "no_evidence",
                "Unknown": "unavailable",
            }[decision.classification]
        else:
            status = decision.status
        if status == "evidence_found":
            return (
                "The pattern is consistent with random LSB replacement.",
                "evidence",
            )
        if status == "no_evidence":
            return (
                f"No matching traces of LSB replacement were found in the {medium}.",
                "clear",
            )
        return (
            "Unable to assess: "
            + (getattr(decision, "reason", None) or "no valid score is available."),
            "unavailable",
        )

    def _chi_square_summary(
        self, decision, pattern=None, *, curve_end=None, file_format=None,
    ) -> tuple[str, str]:
        """Return one concise sentence and its visual state."""
        def sequential_text(end_percent: float, medium: str) -> str:
            return (
                "The pattern is consistent with sequential LSB replacement "
                f"in approximately the first 0–{end_percent:.0f}% "
                f"of the {medium}."
            )

        if decision is None:
            if file_format == "WAV":
                return (
                    "Unable to assess: the WAV Chi-square experiment produced "
                    "a p-value > 1.0 rule, which no p-value can meet. "
                    "The curves are descriptive measurements only.",
                    "unavailable",
                )
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

        if (
            isinstance(decision, AVIDetectorDecision)
            and pattern is not None
            and pattern.status == "sequential_like"
            and pattern.end_percent is not None
        ):
            return sequential_text(pattern.end_percent, "video"), "evidence"

        if isinstance(decision, PNGDetectorDecision):
            end = decision.observed_end_percent
            if end is not None:
                if curve_end is not None:
                    return sequential_text(end, "image"), "evidence"
                if file_format == "PNG":
                    return (
                        "Possible LSB replacement traces were found, but the "
                        "curves do not show a clear sequential range.",
                        "evidence",
                    )
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
            "The locked WAV experiment produced a p-value > 1.0 rule. "
            "Because p-values cannot exceed 1.0, this rule cannot detect "
            "evidence. Review the charts and raw values as measurements only."
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
            return AssessmentMixin._assessment_p_value_text(
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

