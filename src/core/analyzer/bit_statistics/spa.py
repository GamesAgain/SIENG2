import argparse
from dataclasses import dataclass
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image


DEFAULT_J = 30
DEFAULT_MIN_PAIRS = 100


@dataclass
class SPAStatistics:
    """Raw sample-pair counts used by the pooled SPA equation."""

    c_counts: List[int]
    d_counts: List[int]
    x_counts: List[int]
    y_counts: List[int]
    pair_count: int
    sample_count: int


@dataclass
class SPAEstimate:
    """Estimated LSB embedding rate and the equation that produced it."""

    embedding_rate: Optional[float]
    estimated_payload_bits: Optional[float]
    expected_changed_samples: Optional[float]
    pair_count: int
    sample_count: int
    coefficients: Optional[Tuple[float, float, float]] = None
    roots: Tuple[float, ...] = ()
    status: str = "unavailable"
    reason: Optional[str] = None
    diagnostics: Optional["SPADiagnostics"] = None


@dataclass
class SPADiagnostics:
    """Named inputs and intermediate values for pooled SPA equation 18."""

    j: int
    c0: int
    c_j_plus_1: int
    d0: int
    d_2j_plus_2: int
    sum_x: int
    sum_y: int
    trace_difference: int
    discriminant: Optional[float] = None
    selected_root: Optional[float] = None


def make_pairs(channel: np.ndarray) -> np.ndarray:
    """Make disjoint horizontal pairs without joining different rows."""
    height, width = channel.shape
    usable_width = (width // 2) * 2
    if height == 0 or usable_width == 0:
        return np.empty((0, 2), dtype=channel.dtype)
    return channel[:, :usable_width].reshape(-1, 2)


def collect_spa_statistics(channel: np.ndarray) -> SPAStatistics:
    """Count the C, D, X and Y sample-pair sets from one channel."""
    channel = np.asarray(channel)
    if channel.ndim != 2:
        raise ValueError("channel must be a 2D image array.")
    if not np.issubdtype(channel.dtype, np.integer):
        raise ValueError("channel must contain integers in the range 0..255.")
    if np.any(channel < 0) or np.any(channel > 255):
        raise ValueError("channel must contain integers in the range 0..255.")

    pairs = make_pairs(channel)
    if len(pairs) == 0:
        return SPAStatistics(
            c_counts=[0] * 128,
            d_counts=[0] * 256,
            x_counts=[0] * 128,
            y_counts=[0] * 128,
            pair_count=0,
            sample_count=int(channel.size),
        )

    # Signed values avoid uint8 wraparound while taking differences.
    first = pairs[:, 0].astype(np.int32)
    second = pairs[:, 1].astype(np.int32)
    difference = np.abs(first - second)
    high_bit_difference = np.abs((first >> 1) - (second >> 1))

    c_counts = np.bincount(high_bit_difference, minlength=128)[:128]
    d_counts = np.bincount(difference, minlength=256)[:256]

    # Odd-difference pairs form X_(2m+1) or Y_(2m+1).
    odd_difference = difference % 2 == 1
    odd_index = (difference[odd_difference] - 1) // 2
    first_odd = first[odd_difference]
    second_odd = second[odd_difference]

    even_value = np.where(first_odd % 2 == 0, first_odd, second_odd)
    odd_value = np.where(first_odd % 2 == 0, second_odd, first_odd)
    in_x = even_value > odd_value

    x_counts = np.bincount(odd_index[in_x], minlength=128)[:128]
    y_counts = np.bincount(odd_index[~in_x], minlength=128)[:128]

    return SPAStatistics(
        c_counts=c_counts.astype(int).tolist(),
        d_counts=d_counts.astype(int).tolist(),
        x_counts=x_counts.astype(int).tolist(),
        y_counts=y_counts.astype(int).tolist(),
        pair_count=int(len(pairs)),
        sample_count=int(channel.size),
    )


def pool_spa_statistics(statistics: Sequence[SPAStatistics]) -> SPAStatistics:
    """Pool raw counts across image channels before estimating payload."""
    c_counts = np.zeros(128, dtype=np.int64)
    d_counts = np.zeros(256, dtype=np.int64)
    x_counts = np.zeros(128, dtype=np.int64)
    y_counts = np.zeros(128, dtype=np.int64)
    pair_count = 0
    sample_count = 0

    for item in statistics:
        c_counts += np.asarray(item.c_counts, dtype=np.int64)
        d_counts += np.asarray(item.d_counts, dtype=np.int64)
        x_counts += np.asarray(item.x_counts, dtype=np.int64)
        y_counts += np.asarray(item.y_counts, dtype=np.int64)
        pair_count += item.pair_count
        sample_count += item.sample_count

    return SPAStatistics(
        c_counts=c_counts.tolist(),
        d_counts=d_counts.tolist(),
        x_counts=x_counts.tolist(),
        y_counts=y_counts.tolist(),
        pair_count=pair_count,
        sample_count=sample_count,
    )


def estimate_spa(
    statistics: SPAStatistics,
    j: int = DEFAULT_J,
    min_pairs: int = DEFAULT_MIN_PAIRS,
) -> SPAEstimate:
    """Estimate embedding rate with pooled SPA equation 18 (i=0)."""
    if isinstance(j, bool) or not isinstance(j, int) or not 0 <= j <= 126:
        raise ValueError("j must be an integer in the range 0..126.")
    if (isinstance(min_pairs, bool)
            or not isinstance(min_pairs, int)
            or min_pairs < 1):
        raise ValueError("min_pairs must be a positive integer.")

    c_counts = statistics.c_counts
    d_counts = statistics.d_counts
    x_counts = statistics.x_counts
    y_counts = statistics.y_counts

    trace_difference = sum(
        y_counts[index] - x_counts[index]
        for index in range(j + 1)
    )

    # A*p^2 + B*p + T = 0, where p is the used LSB capacity.
    coefficient_a = (2 * c_counts[0] - c_counts[j + 1]) / 4.0
    coefficient_b = -(
        2 * d_counts[0]
        - d_counts[2 * j + 2]
        + 2 * trace_difference
    ) / 2.0
    coefficient_t = float(trace_difference)
    coefficients = (coefficient_a, coefficient_b, coefficient_t)
    diagnostics = SPADiagnostics(
        j=j,
        c0=c_counts[0],
        c_j_plus_1=c_counts[j + 1],
        d0=d_counts[0],
        d_2j_plus_2=d_counts[2 * j + 2],
        sum_x=sum(x_counts[:j + 1]),
        sum_y=sum(y_counts[:j + 1]),
        trace_difference=trace_difference,
    )

    def unavailable(status: str, reason: str) -> SPAEstimate:
        return SPAEstimate(
            embedding_rate=None,
            estimated_payload_bits=None,
            expected_changed_samples=None,
            pair_count=statistics.pair_count,
            sample_count=statistics.sample_count,
            coefficients=coefficients,
            status=status,
            reason=reason,
            diagnostics=diagnostics,
        )

    if statistics.pair_count < min_pairs:
        return unavailable(
            "insufficient_pairs",
            f"Fewer than {min_pairs} complete sample pairs are available.",
        )

    # These decreasing-frequency assumptions are required by the derivation.
    if 2 * c_counts[0] <= c_counts[j + 1]:
        return unavailable(
            "assumption_failed_c",
            "The required relation 2*C0 > C(j+1) is not satisfied.",
        )
    if 2 * d_counts[0] < d_counts[2 * j + 2]:
        return unavailable(
            "assumption_failed_d",
            "The required relation 2*D0 >= D(2j+2) is not satisfied.",
        )

    epsilon = 1e-12
    if abs(coefficient_a) < epsilon:
        if abs(coefficient_b) < epsilon:
            return unavailable(
                "degenerate_equation",
                "Both quadratic and linear terms are effectively zero.",
            )
        roots = (-coefficient_t / coefficient_b,)
    else:
        discriminant = (
            coefficient_b * coefficient_b
            - 4.0 * coefficient_a * coefficient_t
        )
        diagnostics.discriminant = discriminant
        if discriminant < -epsilon:
            return unavailable(
                "no_real_root",
                "The SPA equation has a negative discriminant and no real root.",
            )
        discriminant = max(0.0, discriminant)
        root_delta = math.sqrt(discriminant)
        roots = (
            (-coefficient_b + root_delta) / (2.0 * coefficient_a),
            (-coefficient_b - root_delta) / (2.0 * coefficient_a),
        )

    # Under the paper's assumptions, the smaller real root estimates p.
    embedding_rate = min(roots)
    diagnostics.selected_root = embedding_rate
    if not math.isfinite(embedding_rate):
        return SPAEstimate(
            embedding_rate=None,
            estimated_payload_bits=None,
            expected_changed_samples=None,
            pair_count=statistics.pair_count,
            sample_count=statistics.sample_count,
            coefficients=coefficients,
            roots=roots,
            status="non_finite_root",
            reason="The selected mathematical root is not finite.",
            diagnostics=diagnostics,
        )

    if not 0.0 <= embedding_rate <= 1.0:
        return SPAEstimate(
            embedding_rate=embedding_rate,
            estimated_payload_bits=None,
            expected_changed_samples=None,
            pair_count=statistics.pair_count,
            sample_count=statistics.sample_count,
            coefficients=coefficients,
            roots=roots,
            status="out_of_range",
            reason="The selected root lies outside the physical 0..100% range.",
            diagnostics=diagnostics,
        )

    return SPAEstimate(
        embedding_rate=embedding_rate,
        estimated_payload_bits=embedding_rate * statistics.sample_count,
        expected_changed_samples=(
            embedding_rate * statistics.sample_count / 2.0
        ),
        pair_count=statistics.pair_count,
        sample_count=statistics.sample_count,
        coefficients=coefficients,
        roots=roots,
        status="estimated",
        reason=None,
        diagnostics=diagnostics,
    )


def load_image_targets(image_path: str) -> Dict[str, np.ndarray]:
    """Load 8-bit L/RGB channels; ignore alpha in RGBA images."""
    with Image.open(image_path) as image:
        if image.mode not in ("L", "RGB", "RGBA"):
            raise ValueError("SPA supports 8-bit L, RGB, or RGBA images only.")
        pixels = np.asarray(image)

    if pixels.ndim == 2:
        return {"L": pixels}
    return {name: pixels[:, :, index] for index, name in enumerate("RGB")}


def analyze_spa(
    image_path: str,
    j: int = DEFAULT_J,
    min_pairs: int = DEFAULT_MIN_PAIRS,
) -> Dict[str, Dict[str, Any]]:
    """Analyze each channel and pool RGB sample-pair counts for Whole."""
    targets = load_image_targets(image_path)
    report: Dict[str, Dict[str, Any]] = {}

    for name, channel in targets.items():
        statistics = collect_spa_statistics(channel)
        report[name] = {
            "statistics": statistics,
            "estimate": estimate_spa(statistics, j=j, min_pairs=min_pairs),
        }

    if len(targets) > 1:
        whole_statistics = pool_spa_statistics([
            report[name]["statistics"] for name in targets
        ])
        report = {
            "Whole": {
                "statistics": whole_statistics,
                "estimate": estimate_spa(
                    whole_statistics,
                    j=j,
                    min_pairs=min_pairs,
                ),
            },
            **report,
        }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sample Pair Analysis for LSB replacement."
    )
    parser.add_argument("filepath", help="Path to the image to analyze")
    parser.add_argument(
        "--j", type=int, default=DEFAULT_J,
        help="Upper pooling index in the SPA equation (default: 30)",
    )
    parser.add_argument(
        "--min-pairs", type=int, default=DEFAULT_MIN_PAIRS,
        help="Minimum number of sample pairs (default: 100)",
    )
    args = parser.parse_args()

    try:
        report = analyze_spa(
            args.filepath,
            j=args.j,
            min_pairs=args.min_pairs,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    def print_result(
        name: str,
        statistics: SPAStatistics,
        estimate: SPAEstimate,
    ) -> None:
        c0 = statistics.c_counts[0]
        cj = statistics.c_counts[args.j + 1]
        d0 = statistics.d_counts[0]
        dj = statistics.d_counts[2 * args.j + 2]
        x_total = sum(statistics.x_counts[:args.j + 1])
        y_total = sum(statistics.y_counts[:args.j + 1])

        print(f"\n[{name}]")
        print(
            f"  pairs={statistics.pair_count}, samples={statistics.sample_count}"
        )
        print(
            f"  raw: C0={c0}, C{args.j + 1}={cj}, "
            f"D0={d0}, D{2 * args.j + 2}={dj}, "
            f"sumX={x_total}, sumY={y_total}"
        )

        if estimate.coefficients is None:
            print("  equation: N/A")
        else:
            a, b, t = estimate.coefficients
            roots = ", ".join(f"{root:.6g}" for root in estimate.roots)
            print(
                f"  equation: A={a:.6g}, B={b:.6g}, T={t:.6g}, "
                f"roots=[{roots}]"
            )

        print(f"  status={estimate.status}")
        if estimate.reason:
            print(f"  reason={estimate.reason}")

        if estimate.embedding_rate is None:
            print("  Estimated embedded bits: N/A")
        elif estimate.estimated_payload_bits is None:
            print(
                f"  Estimated embed rate: {estimate.embedding_rate * 100:.2f}% "
                "(outside physical range 0..100%)"
            )
        else:
            print(
                f"  Estimated embed rate: {estimate.embedding_rate * 100:.2f}%, "
                f"bits={estimate.estimated_payload_bits:.0f}, "
                f"expected_changed={estimate.expected_changed_samples:.0f}"
            )

    print(f"Image: {args.filepath}")
    print(f"j={args.j}, min_pairs={args.min_pairs}")
    for name, analysis in report.items():
        print_result(name, analysis["statistics"], analysis["estimate"])


if __name__ == "__main__":
    main()
