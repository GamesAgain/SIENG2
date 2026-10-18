"""RS analysis for a mono PCM16 sample sequence, adapted from ref audio RS.

Groups are four non-overlapping samples in time order.  The mask is
M=(0, 1, 1, 0); both M and -M use the reference discrimination function.
"""

from __future__ import annotations

from math import ceil, isfinite, sqrt

import numpy as np

from src.core.analyzer.models.common import RSMeasurement
from src.core.analyzer.models.wav import WAVRSPayloadEstimate, WAVRSStatistics

MASK = (0, 1, 1, 0)


def _statistics(counts: tuple[int, int, int, int, int, int]) -> WAVRSStatistics:
    rm, sm, um, r_neg, s_neg, u_neg = counts
    total = rm + sm + um
    if not total:
        return WAVRSStatistics()
    return WAVRSStatistics(
        total_groups=total,
        sample_count=total * 4,
        RM_count=rm, SM_count=sm, UM_count=um,
        R_negM_count=r_neg, S_negM_count=s_neg, U_negM_count=u_neg,
        RM=rm / total, SM=sm / total, UM=um / total,
        R_negM=r_neg / total, S_negM=s_neg / total, U_negM=u_neg / total,
    )


def _classify(groups: np.ndarray, mask: tuple[int, ...]) -> tuple[int, int, int]:
    flipped = groups.copy()
    for column, operation in enumerate(mask):
        if operation == 1:
            flipped[:, column] ^= 1
        elif operation == -1:
            values = flipped[:, column]
            flipped[:, column] = values + np.where(values % 2 == 0, -1, 1)
    before = np.abs(np.diff(groups, axis=1)).sum(axis=1)
    after = np.abs(np.diff(flipped, axis=1)).sum(axis=1)
    regular = int(np.count_nonzero(after > before))
    singular = int(np.count_nonzero(after < before))
    return regular, singular, len(groups) - regular - singular


def rs_statistics(samples: np.ndarray) -> WAVRSStatistics:
    """Count R/S/U for M and -M, discarding at most three trailing samples."""
    values = np.asarray(samples)
    if values.ndim != 1 or values.dtype != np.dtype(np.int16):
        raise ValueError("WAV RS requires one int16 PCM channel.")
    group_count = len(values) // 4
    if not group_count:
        return WAVRSStatistics()
    # int32 prevents overflow in F-1 at the signed PCM16 boundaries.
    groups = values[:group_count * 4].astype(np.int32).reshape(-1, 4)
    return _statistics((*_classify(groups, MASK),
                        *_classify(groups, tuple(-value for value in MASK))))


def estimate_rs_payload(
    observed: WAVRSStatistics,
    fully_flipped: WAVRSStatistics,
    capacity_samples: int,
) -> WAVRSPayloadEstimate:
    """Solve the same Fridrich quadratic and root rule used by ref RS."""
    def unavailable(status: str, reason: str) -> WAVRSPayloadEstimate:
        return WAVRSPayloadEstimate(None, None, None, capacity_samples,
                                    status=status, reason=reason)

    values = (
        observed.RM, observed.SM, observed.R_negM, observed.S_negM,
        fully_flipped.RM, fully_flipped.SM,
        fully_flipped.R_negM, fully_flipped.S_negM,
    )
    if any(value is None for value in values):
        return unavailable("insufficient_groups", "No complete 4-sample groups are available.")
    rm, sm, r_neg, s_neg, rm_flip, sm_flip, r_neg_flip, s_neg_flip = values
    d0 = rm - sm
    d1 = rm_flip - sm_flip
    d_neg_0 = r_neg - s_neg
    d_neg_1 = r_neg_flip - s_neg_flip
    a = 2.0 * (d1 + d0)
    b = d_neg_0 - d_neg_1 - d1 - 3.0 * d0
    c = d0 - d_neg_0
    tiny = 1e-12
    if abs(a) < tiny:
        if abs(b) < tiny:
            return unavailable("degenerate_equation", "Both quadratic and linear terms are effectively zero.")
        roots = (-c / b,)
    else:
        discriminant = b * b - 4.0 * a * c
        if discriminant < -tiny:
            return unavailable("no_real_root", "The RS equation has no real root.")
        delta = sqrt(max(0.0, discriminant))
        roots = ((-b + delta) / (2.0 * a), (-b - delta) / (2.0 * a))
    root = min(roots, key=abs)
    if not isfinite(root) or abs(root - 0.5) < tiny:
        return unavailable("non_finite_root", "The selected root makes the rate undefined.")
    rate = root / (root - 0.5)
    if not isfinite(rate):
        return unavailable("non_finite_root", "The embedding rate is not finite.")
    if not 0.0 <= rate <= 1.0:
        return WAVRSPayloadEstimate(rate, None, None, capacity_samples, root,
                                    status="out_of_range",
                                    reason="The estimated rate is outside 0..1.")
    return WAVRSPayloadEstimate(
        embedding_rate=rate,
        estimated_payload_bits=rate * capacity_samples,
        expected_changed_samples=rate * capacity_samples / 2.0,
        capacity_samples=capacity_samples,
        root=root,
        status="estimated",
    )


def analyze_rs(samples: np.ndarray) -> RSMeasurement:
    """Measure one temporal range on a PCM16 channel."""
    values = np.asarray(samples)
    observed = rs_statistics(values)
    flipped = rs_statistics(np.bitwise_xor(values, 1))
    return RSMeasurement(
        observed,
        estimate_rs_payload(observed, flipped, len(values)),
    )


def analyze_rs_prefixes(
    samples: np.ndarray, sample_rate: int, step_percent: int,
) -> tuple[tuple[int, int, float, RSMeasurement], ...]:
    """Cumulative ranges at the same percentages as WAV Chi-square."""
    values = np.asarray(samples)
    result = []
    for percent in (*range(step_percent, 100, step_percent), 100):
        end = ceil(len(values) * percent / 100)
        result.append((percent, end, end / sample_rate, analyze_rs(values[:end])))
    return tuple(result)


def analyze_rs_segments(
    samples: np.ndarray, sample_rate: int,
    segment_percent: int, step_percent: int,
) -> tuple[tuple[int, int, float, float, RSMeasurement], ...]:
    """Sliding ranges matching WAV Chi-square's segment boundaries."""
    values = np.asarray(samples)
    if not len(values):
        return ()
    length = ceil(len(values) * segment_percent / 100)
    step = max(1, ceil(len(values) * step_percent / 100))
    last = len(values) - length
    starts = list(range(0, last + 1, step))
    if starts[-1] != last:
        starts.append(last)
    return tuple((start, start + length, start / sample_rate,
                  (start + length) / sample_rate,
                  analyze_rs(values[start:start + length])) for start in starts)
