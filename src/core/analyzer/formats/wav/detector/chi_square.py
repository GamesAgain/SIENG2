"""Full-histogram PoV Chi-square detector for 16-bit PCM WAV."""

from math import ceil, isfinite
import numpy as np
from scipy.stats import chi2

from src.core.analyzer.models.wav import (
    WAVChiSquareAnalysis,
    WAVChiSquarePrefixResult,
    WAVChiSquareSegmentResult,
)


def analyze_chi_square(
    samples: np.ndarray,
    min_expected: float = 5.0,
) -> WAVChiSquareAnalysis:
    """Analyze one time-ordered signed 16-bit PCM channel."""
    values = np.asarray(samples)

    if values.dtype != np.dtype(np.int16):
        raise ValueError("WAV Chi-square currently supports only int16 PCM samples.")

    minimum = float(min_expected)
    if not isfinite(minimum) or minimum < 5.0:
        raise ValueError("min_expected must be a finite number of at least 5.0.")

    if values.size == 0:
        return WAVChiSquareAnalysis(
            chi_square_total=None,
            p_value=None,
            sample_count=0,
            valid_pairs=0,
        )

    # Shift signed values into histogram indexes 0..65535. The offset is even,
    # so adjacent indexes remain the correct LSB pairs:
    # (-32768, -32767), ..., (-2, -1), (0, 1), ..., (32766, 32767).
    histogram_indexes = values.astype(np.int32) + 32_768
    histogram = np.bincount(
        histogram_indexes,
        minlength=65_536,
    )
    even_counts = histogram[0::2].astype(np.float64)
    odd_counts = histogram[1::2].astype(np.float64)

    expected = (even_counts + odd_counts) / 2.0
    usable = expected >= minimum
    valid_pairs = int(np.count_nonzero(usable))

    if valid_pairs < 2:
        return WAVChiSquareAnalysis(
            chi_square_total=None,
            p_value=None,
            sample_count=int(values.size),
            valid_pairs=valid_pairs,
        )

    chi_square_total = float(
        np.sum(
            np.square(even_counts[usable] - expected[usable])
            / expected[usable]
        )
    )
    dof = valid_pairs - 1

    return WAVChiSquareAnalysis(
        chi_square_total=chi_square_total,
        p_value=float(chi2.sf(chi_square_total, dof)),
        dof=dof,
        sample_count=int(values.size),
        valid_pairs=valid_pairs,
    )


def analyze_chi_square_prefixes(
    samples: np.ndarray,
    sample_rate: int,
    step_percent: int = 10,
    min_expected: float = 5.0,
) -> tuple[WAVChiSquarePrefixResult, ...]:
    """Analyze cumulative CH1 ranges such as 0-10%, 0-20%, ... 0-100%."""
    values = np.asarray(samples)
    if values.ndim != 1:
        raise ValueError("WAV Chi-square prefixes require one audio channel.")
    if values.dtype != np.dtype(np.int16):
        raise ValueError("WAV Chi-square currently supports only int16 PCM samples.")
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int):
        raise ValueError("sample_rate must be a positive integer.")
    if sample_rate < 1:
        raise ValueError("sample_rate must be a positive integer.")
    if isinstance(step_percent, bool) or not isinstance(step_percent, int):
        raise ValueError("step_percent must be an integer between 1 and 100.")
    if not 1 <= step_percent <= 100:
        raise ValueError("step_percent must be an integer between 1 and 100.")

    results = []
    for percent in (*range(step_percent, 100, step_percent), 100):
        end_sample = ceil(values.size * percent / 100)
        results.append(
            WAVChiSquarePrefixResult(
                percent=percent,
                end_sample=end_sample,
                end_seconds=end_sample / sample_rate,
                analysis=analyze_chi_square(
                    values[:end_sample],
                    min_expected=min_expected,
                ),
            )
        )
    return tuple(results)


def analyze_chi_square_segments(
    samples: np.ndarray,
    sample_rate: int,
    segment_percent: int = 10,
    step_percent: int = 5,
    min_expected: float = 5.0,
) -> tuple[WAVChiSquareSegmentResult, ...]:
    """Analyze fixed-length CH1 windows that slide along the audio timeline."""
    values = np.asarray(samples)
    if values.ndim != 1:
        raise ValueError("WAV Chi-square segments require one audio channel.")
    if values.dtype != np.dtype(np.int16):
        raise ValueError("WAV Chi-square currently supports only int16 PCM samples.")
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int):
        raise ValueError("sample_rate must be a positive integer.")
    if sample_rate < 1:
        raise ValueError("sample_rate must be a positive integer.")

    for name, percent in (
        ("segment_percent", segment_percent),
        ("step_percent", step_percent),
    ):
        if isinstance(percent, bool) or not isinstance(percent, int):
            raise ValueError(f"{name} must be an integer between 1 and 100.")
        if not 1 <= percent <= 100:
            raise ValueError(f"{name} must be an integer between 1 and 100.")
    if step_percent > segment_percent:
        raise ValueError("step_percent must not exceed segment_percent.")
    if values.size == 0:
        return ()

    segment_size = ceil(values.size * segment_percent / 100)
    step_size = max(1, ceil(values.size * step_percent / 100))
    last_start = values.size - segment_size
    starts = list(range(0, last_start + 1, step_size))
    if starts[-1] != last_start:
        starts.append(last_start)

    return tuple(
        WAVChiSquareSegmentResult(
            start_sample=start_sample,
            end_sample=start_sample + segment_size,
            start_seconds=start_sample / sample_rate,
            end_seconds=(start_sample + segment_size) / sample_rate,
            analysis=analyze_chi_square(
                values[start_sample:start_sample + segment_size],
                min_expected=min_expected,
            ),
        )
        for start_sample in starts
    )
