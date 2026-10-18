"""Sample Pair Analysis for signed 16-bit PCM WAV samples.

This module contains only SPA statistics and rate estimation.  The validated
method-agnostic ``j``, threshold and analysis scope are documented in
``src.core.analyzer.formats.wav.spa_config``.  Keeping the operating decision
outside this equation module keeps the detector reusable and testable.
"""

from math import sqrt

import numpy as np

from src.core.analyzer.models.wav import (
    WAVSPAAnalysis,
    WAVSPAEstimate,
    WAVSPAStatistics,
)


def _validate_settings(j: int, min_pairs: int | None = None) -> None:
    if isinstance(j, bool) or not isinstance(j, int) or not 0 <= j <= 126:
        raise ValueError("SPA j must be an integer between 0 and 126.")
    if min_pairs is not None and (
        isinstance(min_pairs, bool)
        or not isinstance(min_pairs, int)
        or min_pairs < 1
    ):
        raise ValueError("SPA min_pairs must be a positive integer.")


def _count(values: np.ndarray, size: int) -> np.ndarray:
    """Count non-negative values that fit in a fixed SPA vector."""
    selected = values[values < size]
    return np.bincount(selected, minlength=size)[:size]


def collect_spa_statistics(
    samples: np.ndarray,
    j: int = 30,
) -> WAVSPAStatistics:
    """Collect C, D, X and Y from overlapping pairs (s0,s1), (s1,s2), ..."""
    _validate_settings(j)
    values = np.asarray(samples)
    if values.ndim != 1:
        raise ValueError("WAV SPA requires one audio channel.")
    if values.dtype != np.dtype(np.int16):
        raise ValueError("WAV SPA currently supports only int16 PCM samples.")

    first = values[:-1].astype(np.int64, copy=False)
    second = values[1:].astype(np.int64, copy=False)
    difference = np.abs(first - second)
    shifted_difference = np.abs((first >> 1) - (second >> 1))

    odd_mask = (difference & 1) == 1
    odd_index = (difference[odd_mask] - 1) // 2
    in_range = odd_index <= j
    odd_index = odd_index[in_range]
    larger_is_even = (
        np.maximum(first[odd_mask][in_range], second[odd_mask][in_range]) & 1
    ) == 0

    return WAVSPAStatistics(
        j=j,
        c_counts=tuple(int(value) for value in _count(shifted_difference, j + 2)),
        d_counts=tuple(int(value) for value in _count(difference, 2 * j + 3)),
        x_counts=tuple(
            int(value) for value in _count(odd_index[larger_is_even], j + 1)
        ),
        y_counts=tuple(
            int(value) for value in _count(odd_index[~larger_is_even], j + 1)
        ),
        pair_count=int(first.size),
        sample_count=int(values.size),
    )


def usable_pair_ratio(statistics: WAVSPAStatistics) -> float | None:
    """Return the share of pairs with |s0 - s1| <= 2j + 2.

    ``d_counts`` only holds differences 0..2j+2, so its sum is exactly the
    number of pairs that can contribute to the SPA equation.
    """
    if statistics.pair_count < 1:
        return None
    return sum(statistics.d_counts) / statistics.pair_count


def _result(
    statistics: WAVSPAStatistics,
    status: str,
    *,
    rate: float | None = None,
    coefficients: tuple[float, float, float] | None = None,
    roots: tuple[float, ...] = (),
    discriminant: float | None = None,
    reason: str | None = None,
) -> WAVSPAEstimate:
    estimated_bits = (
        rate * statistics.sample_count if status == "estimated" else None
    )
    return WAVSPAEstimate(
        usable_pair_ratio=usable_pair_ratio(statistics),
        embedding_rate=rate,
        estimated_payload_bits=estimated_bits,
        expected_changed_samples=(
            estimated_bits / 2.0 if estimated_bits is not None else None
        ),
        pair_count=statistics.pair_count,
        sample_count=statistics.sample_count,
        coefficients=coefficients,
        roots=roots,
        discriminant=discriminant,
        status=status,
        reason=reason,
    )


def estimate_spa(
    statistics: WAVSPAStatistics,
    min_pairs: int = 100,
) -> WAVSPAEstimate:
    """Estimate the used LSB capacity from collected WAV SPA counts."""
    j = statistics.j
    _validate_settings(j, min_pairs)
    if statistics.pair_count < min_pairs:
        return _result(
            statistics,
            "insufficient_pairs",
            reason=f"Fewer than {min_pairs} adjacent sample pairs are available.",
        )

    c = statistics.c_counts
    d = statistics.d_counts
    sum_x = sum(statistics.x_counts)
    sum_y = sum(statistics.y_counts)
    trace = sum_y - sum_x
    coefficients = (
        (2 * c[0] - c[j + 1]) / 4.0,
        -(2 * d[0] - d[2 * j + 2] + 2 * trace) / 2.0,
        float(trace),
    )
    if 2 * c[0] <= c[j + 1]:
        return _result(
            statistics,
            "assumption_failed_c",
            coefficients=coefficients,
            reason="The required relation 2*C0 > C(j+1) is not satisfied.",
        )
    if 2 * d[0] < d[2 * j + 2]:
        return _result(
            statistics,
            "assumption_failed_d",
            coefficients=coefficients,
            reason="The required relation 2*D0 >= D(2j+2) is not satisfied.",
        )

    coefficient_a, coefficient_b, coefficient_c = coefficients
    if abs(coefficient_a) < 1e-12:
        if abs(coefficient_b) < 1e-12:
            return _result(
                statistics,
                "degenerate_equation",
                coefficients=coefficients,
                reason="Both quadratic and linear terms are effectively zero.",
            )
        roots = (-coefficient_c / coefficient_b,)
        discriminant = None
    else:
        discriminant = coefficient_b**2 - 4 * coefficient_a * coefficient_c
        if discriminant < -1e-12:
            return _result(
                statistics,
                "no_real_root",
                coefficients=coefficients,
                discriminant=discriminant,
                reason="The SPA equation has no real root.",
            )
        root_delta = sqrt(max(0.0, discriminant))
        roots = (
            (-coefficient_b + root_delta) / (2 * coefficient_a),
            (-coefficient_b - root_delta) / (2 * coefficient_a),
        )

    embedding_rate = min(roots)
    if not 0.0 <= embedding_rate <= 1.0:
        return _result(
            statistics,
            "out_of_range",
            rate=embedding_rate,
            coefficients=coefficients,
            roots=roots,
            discriminant=discriminant,
            reason="The selected root is outside the physical range 0..1.",
        )

    return _result(
        statistics,
        "estimated",
        rate=embedding_rate,
        coefficients=coefficients,
        roots=roots,
        discriminant=discriminant,
    )


def analyze_spa(
    samples: np.ndarray,
    j: int = 30,
    min_pairs: int = 100,
) -> WAVSPAAnalysis:
    """Run full-file SPA on one signed 16-bit PCM channel."""
    statistics = collect_spa_statistics(samples, j)
    return WAVSPAAnalysis(
        statistics=statistics,
        estimate=estimate_spa(statistics, min_pairs),
    )
