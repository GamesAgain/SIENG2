"""Audio-specific counters with the existing image estimators and result types."""

import numpy as np
from scipy.stats import chi2

from src.core.analyzer.bit_statistics.chi_square import ChiSquareResult
from src.core.analyzer.bit_statistics.rs_analysis import (
    classify_counts, result_from_counts, pool_rs_results, payload_from_results,
)
from src.core.analyzer.bit_statistics.spa import SPAStatistics, pool_spa_statistics, estimate_spa


def chi_counts(values, bits):
    values = np.asarray(values, dtype=np.int32).ravel()
    offset = 0 if bits == 8 else 32768
    return np.bincount(values + offset, minlength=1 << bits)


def chi_result(counts, min_expected):
    if not np.isfinite(min_expected) or min_expected < 5:
        raise ValueError("min_expected must be finite and at least 5.")
    total = int(counts.sum())
    if not total:
        return ChiSquareResult(None, None, sample_count=0, valid_pairs=0,
                               status="empty", reason="No samples were provided.")
    even, odd = counts[::2].astype(float), counts[1::2].astype(float)
    expected = (even + odd) / 2
    usable = expected >= min_expected
    count = int(usable.sum())
    if count < 2:
        return ChiSquareResult(None, None, sample_count=total, valid_pairs=count,
                               status="insufficient_pairs", reason="Fewer than two usable PoV pairs.")
    statistic = float(np.sum((even[usable] - expected[usable]) ** 2 / expected[usable]))
    return ChiSquareResult(statistic, float(chi2.sf(statistic, count - 1)),
                           dof=count - 1, sample_count=total, valid_pairs=count, status="ok")


def rs_result(values):
    values = np.asarray(values, dtype=np.int32).ravel()
    groups = values[:len(values) // 4 * 4].reshape(-1, 4)
    if not len(groups):
        return result_from_counts((0,) * 6)
    mask = (0, 1, 1, 0)
    return result_from_counts((*classify_counts(groups, mask),
                               *classify_counts(groups, tuple(-x for x in mask))))


def rs_measurement(channels):
    observed = pool_rs_results([rs_result(values) for values in channels])
    flipped = pool_rs_results([rs_result(np.asarray(values, dtype=np.int32) ^ 1) for values in channels])
    capacity = sum(len(values) for values in channels)
    return observed, payload_from_results(observed, flipped, capacity)


def spa_statistics(values):
    values = np.asarray(values, dtype=np.int32).ravel()
    pairs = values[:len(values) // 2 * 2].reshape(-1, 2)
    if not len(pairs):
        return SPAStatistics([0] * 128, [0] * 256, [0] * 128, [0] * 128, 0, len(values))
    left, right = pairs[:, 0], pairs[:, 1]
    gap = np.abs(left - right)
    high_gap = np.abs((left >> 1) - (right >> 1))
    odd = gap % 2 == 1
    odd_left, odd_right = left[odd], right[odd]
    even_member = np.where(odd_left % 2 == 0, odd_left, odd_right)
    odd_member = np.where(odd_left % 2 == 0, odd_right, odd_left)
    index = (gap[odd] - 1) // 2
    even_larger = even_member > odd_member
    # SPA j <= 126 only needs C[0:128], D[0:256], X/Y[0:128].
    return SPAStatistics(
        np.bincount(high_gap[high_gap < 128], minlength=128).tolist(),
        np.bincount(gap[gap < 256], minlength=256).tolist(),
        np.bincount(index[even_larger & (index < 128)], minlength=128).tolist(),
        np.bincount(index[~even_larger & (index < 128)], minlength=128).tolist(),
        len(pairs), len(values),
    )


def spa_measurement(channels, j, min_pairs):
    statistics = pool_spa_statistics([spa_statistics(values) for values in channels])
    return statistics, estimate_spa(statistics, j=j, min_pairs=min_pairs)
