"""WAV file handler for the format-specific analyzers."""

from pathlib import Path
import wave

import numpy as np

from src.core.analyzer.formats.wav.detector.chi_square import (
    analyze_chi_square,
    analyze_chi_square_prefixes,
    analyze_chi_square_segments,
)
from src.core.analyzer.formats.wav.detector.spa import analyze_spa
from src.core.analyzer.formats.wav.detector.rs import (
    analyze_rs,
    analyze_rs_prefixes,
    analyze_rs_segments,
)
from src.core.analyzer.formats.wav.experimental_spa_profile import (
    evaluate_experimental_spa_profile,
)
from src.core.analyzer.formats.wav.rs_profile import evaluate_rs_profile
from src.core.analyzer.models.analysis import AnalysisResult
from src.core.analyzer.models.common import BitStatisticsResult, FileInfo
from src.core.analyzer.models.series import (
    TemporalPrefix,
    TemporalSegment,
    TemporalSeries,
)
from src.core.analyzer.models.wav import (
    WAVChiSquareResult,
    WAVMediaInfo,
    WAVRSResult,
    WAVSPAResult,
)
from src.core.analyzer.parameters import AnalysisParameters


class WAVFormatError(ValueError):
    """Raised when a WAV file is malformed or is not supported."""


class WAVHandler:
    """Read a mono 16-bit PCM WAV file and run its WAV-specific detectors."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path).expanduser().resolve()

    def analyze(
        self,
        parameters: AnalysisParameters | None = None,
    ) -> AnalysisResult:
        """Read the mono WAV once and return CH1 detector results."""
        selected = parameters or AnalysisParameters()
        selected.validate()

        if not self.file_path.is_file():
            raise FileNotFoundError(f"File not found: {self.file_path}")
        if self.file_path.suffix.lower() != ".wav":
            raise WAVFormatError(f"Expected a .wav file: {self.file_path}")

        try:
            with wave.open(str(self.file_path), "rb") as wav_file:
                channel_count = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                sample_rate = wav_file.getframerate()
                frame_count = wav_file.getnframes()
                compression_type = wav_file.getcomptype()
                compression_name = wav_file.getcompname()

                if compression_type != "NONE":
                    raise WAVFormatError(
                        "WAV Chi-square supports only uncompressed PCM audio."
                    )
                if sample_width != 2:
                    raise WAVFormatError(
                        "WAV Chi-square currently supports only 16-bit PCM audio."
                    )
                if channel_count != 1:
                    raise WAVFormatError("WAV analysis currently supports mono audio only.")
                if sample_rate < 1:
                    raise WAVFormatError("Invalid WAV sample rate.")

                raw_pcm = wav_file.readframes(frame_count)
        except (EOFError, wave.Error) as exc:
            raise WAVFormatError(f"Cannot read WAV file: {exc}") from exc

        # A PCM frame stores one signed 16-bit little-endian sample per channel.
        pcm_samples = np.frombuffer(raw_pcm, dtype="<i2")
        expected_sample_count = frame_count * channel_count
        if pcm_samples.size != expected_sample_count:
            raise WAVFormatError(
                "WAV sample data is shorter than the frame information in its header."
            )

        pcm_frames = pcm_samples.reshape(frame_count, channel_count)
        channel_1 = pcm_frames[:, 0]
        media_info = WAVMediaInfo(
            channel_count=channel_count,
            sample_rate=sample_rate,
            frame_count=frame_count,
            sample_count=int(pcm_samples.size),
            duration_seconds=frame_count / sample_rate,
            sample_width_bits=sample_width * 8,
            compression_type=compression_type,
            compression_name=compression_name,
        )

        return AnalysisResult(
            file=FileInfo(
                path=str(self.file_path),
                name=self.file_path.name,
                extension=self.file_path.suffix.lower(),
                size=self.file_path.stat().st_size,
                format="WAV",
            ),
            media_info=media_info,
            parameters=selected,
            structure=self.analyze_structure(),
            metadata=self.analyze_metadata(),
            bit_statistics=self.analyze_bit_statistics(
                channel_1,
                sample_rate,
                selected,
                channel_count=channel_count,
            ),
        )

    def analyze_structure(self) -> dict[str, object] | None:
        """Reserved for the WAV RIFF/chunk structure analyzer."""
        return None

    def analyze_metadata(self) -> dict[str, object] | None:
        """Reserved for the WAV metadata analyzer."""
        return None

    def analyze_bit_statistics(
        self,
        channel_1: np.ndarray,
        sample_rate: int,
        parameters: AnalysisParameters,
        *,
        channel_count: int = 1,
    ) -> BitStatisticsResult:
        """Run CH1 detectors using the parameters selected in the GUI."""
        chi_prefixes = analyze_chi_square_prefixes(
            channel_1,
            sample_rate=sample_rate,
            step_percent=parameters.prefix_step,
            min_expected=parameters.min_expected,
        )
        chi_segments = analyze_chi_square_segments(
            channel_1,
            sample_rate=sample_rate,
            segment_percent=parameters.segment_percent,
            step_percent=parameters.segment_step,
            min_expected=parameters.min_expected,
        )
        chi_series = TemporalSeries(
            whole=analyze_chi_square(
                channel_1,
                min_expected=parameters.min_expected,
            ),
            prefix=tuple(
                TemporalPrefix(
                    percent=item.percent,
                    end_frame=item.end_sample,
                    end_seconds=item.end_seconds,
                    analysis=item.analysis,
                )
                for item in chi_prefixes
            ),
            segments=tuple(
                TemporalSegment(
                    start_frame=item.start_sample,
                    end_frame=item.end_sample,
                    start_seconds=item.start_seconds,
                    end_seconds=item.end_seconds,
                    analysis=item.analysis,
                )
                for item in chi_segments
            ),
        )

        rs_prefixes = analyze_rs_prefixes(
            channel_1, sample_rate, parameters.prefix_step,
        )
        rs_segments = analyze_rs_segments(
            channel_1, sample_rate,
            parameters.segment_percent, parameters.segment_step,
        )
        rs_series = TemporalSeries(
            whole=analyze_rs(channel_1),
            prefix=tuple(
                TemporalPrefix(
                    percent=percent,
                    end_frame=end,
                    end_seconds=seconds,
                    analysis=measurement,
                )
                for percent, end, seconds, measurement in rs_prefixes
            ),
            segments=tuple(
                TemporalSegment(
                    start_frame=start,
                    end_frame=end,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    analysis=measurement,
                )
                for start, end, start_seconds, end_seconds, measurement in rs_segments
            ),
        )

        spa_analysis = analyze_spa(
            channel_1,
            j=parameters.spa_j,
            min_pairs=parameters.spa_min_pairs,
        )
        spa_decision = evaluate_experimental_spa_profile(
            spa_analysis.estimate,
            parameters,
            channel_count=channel_count,
            sample_rate=sample_rate,
            sample_count=len(channel_1),
        )
        return BitStatisticsResult(
            chi_square=WAVChiSquareResult(
                channels={
                    "CH1": chi_series,
                }
            ),
            rs=WAVRSResult(
                channels={"CH1": rs_series},
                decision=evaluate_rs_profile(
                    rs_series.whole.payload,
                    channel_count=channel_count,
                    sample_rate=sample_rate,
                    sample_count=len(channel_1),
                ),
            ),
            spa=WAVSPAResult(
                channels={
                    "CH1": spa_analysis,
                },
                decision=spa_decision,
            ),
        )
