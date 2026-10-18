"""AVI loading and one-pass coordination of video bit-statistics detectors."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np

from src.core.analyzer.formats.avi.detector.chi_square import ChiSquareVideo
from src.core.analyzer.formats.avi.detector.rs_analysis import RSVideo
from src.core.analyzer.formats.avi.detector.spa import SPAVideo
from src.core.analyzer.models.analysis import AnalysisResult
from src.core.analyzer.models.avi import (
    AVIChiSquareResult,
    AVIFrameChiSquareDetailResult,
    AVIFrameRSDetailResult,
    AVIFrameSPADetailResult,
    AVIMediaInfo,
    AVIRSResult,
    AVISPAResult,
)
from src.core.analyzer.models.common import BitStatisticsResult, FileInfo
from src.core.analyzer.models.series import (
    FrameDetailResult,
    FrameResult,
    SpatialPrefix,
    SpatialSegment,
    SpatialSeries,
    TemporalPrefix,
    TemporalSegment,
    TemporalSeries,
)
from src.core.analyzer.parameters import AnalysisParameters

from .profile_evaluator import (
    evaluate_chi_square_profile,
    evaluate_rs_profile,
    evaluate_spa_profile,
)


AVIFrameTargets = tuple[
    int,
    float,
    dict[str, np.ndarray],
    dict[str, np.ndarray],
]


class AVIFormatError(ValueError):
    """Raised when an AVI file is invalid or cannot be decoded."""


class AVIHandler:
    """Decode an AVI once and feed every RGB frame to all detectors."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path).expanduser().resolve()

    def analyze(
        self,
        parameters: AnalysisParameters | None = None,
    ) -> AnalysisResult:
        """Return file information and all enabled AVI analyses."""
        selected = parameters or AnalysisParameters()
        selected.validate()
        media_info = self._load_media_info()

        return AnalysisResult(
            file=FileInfo(
                path=str(self.file_path),
                name=self.file_path.name,
                extension=self.file_path.suffix.lower(),
                size=self.file_path.stat().st_size,
                format="AVI",
            ),
            media_info=media_info,
            parameters=selected,
            structure=self.analyze_structure(),
            metadata=self.analyze_metadata(),
            bit_statistics=self.analyze_bit_statistics(
                self.prepare_bit_statistics_data(media_info),
                media_info,
                selected,
            ),
        )

    def analyze_structure(self) -> dict[str, Any] | None:
        """Reserved for AVI RIFF/container structure analysis."""
        return None

    def analyze_metadata(self) -> dict[str, Any] | None:
        """Reserved for AVI metadata analysis."""
        return None

    def analyze_bit_statistics(
        self,
        frame_targets: Iterator[AVIFrameTargets],
        media_info: AVIMediaInfo,
        parameters: AnalysisParameters,
    ) -> BitStatisticsResult:
        """Feed the same decoded RGB frames to Chi-square, RS and SPA."""
        chi_detector = ChiSquareVideo(
            media_info.height,
            media_info.width,
            min_expected=parameters.min_expected,
            prefix_step=parameters.prefix_step,
            segment_percent=parameters.segment_percent,
            segment_step=parameters.segment_step,
        )
        rs_detector = RSVideo(
            media_info.height,
            media_info.width,
            prefix_step=parameters.prefix_step,
            segment_percent=parameters.segment_percent,
            segment_step=parameters.segment_step,
        )
        spa_detector = SPAVideo(
            media_info.height,
            media_info.width,
            j=parameters.spa_j,
            min_pairs=parameters.spa_min_pairs,
            prefix_step=parameters.prefix_step,
            segment_percent=parameters.segment_percent,
            segment_step=parameters.segment_step,
        )

        decoded_indexes: list[int] = []
        decoded_timestamps: list[float] = []
        for frame_index, timestamp, chi_targets, _channels in frame_targets:
            # Whole is the canonical RGB frame. Each detector splits R/G/B
            # internally, so all three see identical pixels and boundaries.
            rgb_frame = np.ascontiguousarray(chi_targets["Whole"])
            chi_detector.add(rgb_frame)
            rs_detector.add(rgb_frame)
            spa_detector.add(rgb_frame)
            decoded_indexes.append(frame_index)
            decoded_timestamps.append(timestamp)

        if not decoded_indexes:
            raise AVIFormatError("AVI contains no decodable frames.")

        chi_report = chi_detector.finish()
        rs_report = rs_detector.finish()
        spa_report = spa_detector.finish()
        chi_decision = evaluate_chi_square_profile(chi_report, parameters)
        rs_decision = evaluate_rs_profile(rs_report)
        spa_decision = evaluate_spa_profile(spa_report, parameters)

        return BitStatisticsResult(
            chi_square=AVIChiSquareResult(
                video=self._build_temporal_channels(
                    chi_report, media_info.frame_rate
                ),
                frames=self._build_frames(
                    chi_report, decoded_indexes, decoded_timestamps
                ),
                analyzed_frame_count=len(decoded_indexes),
                total_frame_count=media_info.frame_count,
                decision=chi_decision,
            ),
            rs=AVIRSResult(
                video=self._build_temporal_channels(
                    rs_report, media_info.frame_rate
                ),
                frames=self._build_frames(
                    rs_report, decoded_indexes, decoded_timestamps
                ),
                analyzed_frame_count=len(decoded_indexes),
                total_frame_count=media_info.frame_count,
                decision=rs_decision,
            ),
            spa=AVISPAResult(
                video=self._build_temporal_channels(
                    spa_report, media_info.frame_rate
                ),
                frames=self._build_frames(
                    spa_report, decoded_indexes, decoded_timestamps
                ),
                analyzed_frame_count=len(decoded_indexes),
                total_frame_count=media_info.frame_count,
                decision=spa_decision,
            ),
        )

    def analyze_frame_chi_square(
        self,
        frame_index: int,
        parameters: AnalysisParameters | None = None,
    ) -> AVIFrameChiSquareDetailResult:
        """Return spatial Chi-square details for one requested frame."""
        selected = parameters or AnalysisParameters()
        selected.validate()
        rgb_frame, media_info = self._load_selected_frame(frame_index)
        detector = ChiSquareVideo(
            media_info.height,
            media_info.width,
            min_expected=selected.min_expected,
            prefix_step=selected.prefix_step,
            segment_percent=selected.segment_percent,
            segment_step=selected.segment_step,
        )
        detector.add(rgb_frame)
        report = detector.finish()
        channels = {}
        for name, target in report["targets"].items():
            channels[name] = SpatialSeries(
                whole=target["whole"],
                prefix=tuple(
                    SpatialPrefix(item.percent, item.end, item.analysis)
                    for item in target["spatial_prefix"]
                ),
                segments=tuple(
                    SpatialSegment(item.start, item.end, item.analysis)
                    for item in target["spatial_segments"]
                ),
            )
        return FrameDetailResult(
            frame_index=frame_index,
            timestamp_seconds=frame_index / media_info.frame_rate,
            width=media_info.width,
            height=media_info.height,
            channels=channels,
        )

    def analyze_frame_rs(
        self,
        frame_index: int,
        parameters: AnalysisParameters | None = None,
    ) -> AVIFrameRSDetailResult:
        """Return RS details for one requested frame."""
        selected = parameters or AnalysisParameters()
        selected.validate()
        rgb_frame, media_info = self._load_selected_frame(frame_index)
        detector = RSVideo(
            media_info.height,
            media_info.width,
            prefix_step=selected.prefix_step,
            segment_percent=selected.segment_percent,
            segment_step=selected.segment_step,
        )
        detector.add(rgb_frame)
        report = detector.finish()
        return FrameDetailResult(
            frame_index=frame_index,
            timestamp_seconds=frame_index / media_info.frame_rate,
            width=media_info.width,
            height=media_info.height,
            channels={
                name: SpatialSeries(target["whole"], (), ())
                for name, target in report["targets"].items()
            },
        )

    def analyze_frame_spa(
        self,
        frame_index: int,
        parameters: AnalysisParameters | None = None,
    ) -> AVIFrameSPADetailResult:
        """Return SPA statistics and estimate for one requested frame."""
        selected = parameters or AnalysisParameters()
        selected.validate()
        rgb_frame, media_info = self._load_selected_frame(frame_index)
        detector = SPAVideo(
            media_info.height,
            media_info.width,
            j=selected.spa_j,
            min_pairs=selected.spa_min_pairs,
            prefix_step=selected.prefix_step,
            segment_percent=selected.segment_percent,
            segment_step=selected.segment_step,
        )
        detector.add(rgb_frame)
        report = detector.finish()
        return FrameDetailResult(
            frame_index=frame_index,
            timestamp_seconds=frame_index / media_info.frame_rate,
            width=media_info.width,
            height=media_info.height,
            channels={
                name: target["whole"]
                for name, target in report["targets"].items()
            },
        )

    @staticmethod
    def _build_frames(
        report: dict[str, Any],
        indexes: list[int],
        timestamps: list[float],
    ) -> tuple[FrameResult, ...]:
        targets = report["targets"]
        return tuple(
            FrameResult(
                frame_index=frame_index,
                timestamp_seconds=timestamp,
                channels={
                    name: target["per_frame"][position]
                    for name, target in targets.items()
                },
            )
            for position, (frame_index, timestamp) in enumerate(
                zip(indexes, timestamps)
            )
        )

    @staticmethod
    def _build_temporal_channels(
        report: dict[str, Any],
        frame_rate: float,
    ) -> dict[str, TemporalSeries]:
        channels = {}
        for name, target in report["targets"].items():
            channels[name] = TemporalSeries(
                whole=target["whole"],
                prefix=tuple(
                    TemporalPrefix(
                        percent=item.percent,
                        end_frame=item.end,
                        end_seconds=item.end / frame_rate,
                        analysis=item.analysis,
                    )
                    for item in target["temporal_prefix"]
                ),
                segments=tuple(
                    TemporalSegment(
                        start_frame=item.start,
                        end_frame=item.end,
                        start_seconds=item.start / frame_rate,
                        end_seconds=item.end / frame_rate,
                        analysis=item.analysis,
                    )
                    for item in target["temporal_segments"]
                ),
            )
        return channels

    def prepare_bit_statistics_data(
        self,
        media_info: AVIMediaInfo,
    ) -> Iterator[AVIFrameTargets]:
        """Yield each decoded frame as canonical RGB plus channel views."""
        cv2 = self._require_cv2()
        capture = cv2.VideoCapture(str(self.file_path))
        try:
            if not capture.isOpened():
                raise AVIFormatError(
                    f"OpenCV cannot open AVI file: {self.file_path}"
                )
            frame_index = 0
            while True:
                success, bgr_frame = capture.read()
                if not success:
                    break
                if (
                    not isinstance(bgr_frame, np.ndarray)
                    or bgr_frame.dtype != np.uint8
                    or bgr_frame.ndim != 3
                    or bgr_frame.shape[2] != 3
                ):
                    raise AVIFormatError(
                        f"Frame {frame_index} is not an 8-bit BGR image."
                    )

                rgb_frame = np.ascontiguousarray(bgr_frame[:, :, ::-1])
                channels = {
                    "R": rgb_frame[:, :, 0],
                    "G": rgb_frame[:, :, 1],
                    "B": rgb_frame[:, :, 2],
                }
                yield (
                    frame_index,
                    frame_index / media_info.frame_rate,
                    {"Whole": rgb_frame, **channels},
                    channels,
                )
                frame_index += 1
        finally:
            capture.release()

    def _load_selected_frame(
        self,
        frame_index: int,
    ) -> tuple[np.ndarray, AVIMediaInfo]:
        """Decode one validated frame and return contiguous RGB data."""
        media_info = self._load_media_info()
        if isinstance(frame_index, bool) or not isinstance(frame_index, int):
            raise TypeError("frame_index must be an integer.")
        if not 0 <= frame_index < media_info.frame_count:
            raise IndexError(
                "frame_index must be between 0 and "
                f"{media_info.frame_count - 1}."
            )

        cv2 = self._require_cv2()
        capture = cv2.VideoCapture(str(self.file_path))
        try:
            if not capture.isOpened():
                raise AVIFormatError(
                    f"OpenCV cannot open AVI file: {self.file_path}"
                )
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            success, bgr_frame = capture.read()
            if not success or bgr_frame is None:
                raise AVIFormatError(
                    f"OpenCV cannot decode AVI frame {frame_index}."
                )
            if (
                bgr_frame.dtype != np.uint8
                or bgr_frame.ndim != 3
                or bgr_frame.shape[2] != 3
            ):
                raise AVIFormatError(
                    f"Frame {frame_index} is not an 8-bit BGR image."
                )
            return np.ascontiguousarray(bgr_frame[:, :, ::-1]), media_info
        finally:
            capture.release()

    def _load_media_info(self) -> AVIMediaInfo:
        """Validate the AVI and read technical information with OpenCV."""
        if not self.file_path.is_file():
            raise FileNotFoundError(f"AVI file not found: {self.file_path}")
        if self.file_path.suffix.lower() != ".avi":
            raise AVIFormatError(f"Expected an .avi file: {self.file_path}")

        cv2 = self._require_cv2()
        capture = cv2.VideoCapture(str(self.file_path))
        try:
            if not capture.isOpened():
                raise AVIFormatError(
                    f"OpenCV cannot open AVI file: {self.file_path}"
                )
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            frame_rate = float(capture.get(cv2.CAP_PROP_FPS))
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            fourcc_value = int(capture.get(cv2.CAP_PROP_FOURCC))
            success, first_frame = capture.read()

            if width <= 0 or height <= 0:
                raise AVIFormatError("AVI has an invalid resolution.")
            if frame_rate <= 0:
                raise AVIFormatError("AVI has an invalid frame rate.")
            if frame_count <= 0:
                raise AVIFormatError("AVI contains no frames.")
            if not success or first_frame is None:
                raise AVIFormatError(
                    "OpenCV cannot decode the first AVI frame."
                )

            codec = "RGB" if fourcc_value == 0 else "".join(
                chr((fourcc_value >> (8 * index)) & 0xFF)
                for index in range(4)
            ).rstrip("\x00 ").strip()
            channel_count = (
                first_frame.shape[2] if first_frame.ndim == 3 else 1
            )
            return AVIMediaInfo(
                width=width,
                height=height,
                frame_rate=frame_rate,
                frame_count=frame_count,
                duration_seconds=frame_count / frame_rate,
                codec=codec or None,
                decoded_bits_per_pixel=(
                    first_frame.dtype.itemsize * 8 * channel_count
                ),
            )
        finally:
            capture.release()

    @staticmethod
    def _require_cv2():
        try:
            import cv2
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "AVI analysis requires the 'opencv-python' package."
            ) from exc
        return cv2
