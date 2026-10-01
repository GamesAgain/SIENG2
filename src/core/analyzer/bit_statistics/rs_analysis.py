import argparse
from dataclasses import dataclass
import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from PIL import Image


DEFAULT_MASK = (0, 1, 1, 0)
GROUP_SIZE = 4


@dataclass
class RSResult:
    """Group counts and fractions under mask M and its negative."""

    total_groups: int = 0
    sample_count: int = 0
    RM_count: int = 0
    SM_count: int = 0
    UM_count: int = 0
    R_negM_count: int = 0
    S_negM_count: int = 0
    U_negM_count: int = 0
    RM: Optional[float] = None
    SM: Optional[float] = None
    UM: Optional[float] = None
    R_negM: Optional[float] = None
    S_negM: Optional[float] = None
    U_negM: Optional[float] = None


@dataclass
class RSPayloadEstimate:
    """Estimated LSB replacement rate and payload size."""

    embedding_rate: Optional[float]
    estimated_payload_bits: Optional[float]
    expected_changed_samples: Optional[float]
    capacity_samples: int
    root: Optional[float] = None


@dataclass
class PrefixResult:
    """RS result for the first pixel_count pixels in raster order."""

    percent: int
    pixel_count: int
    rs: RSResult


def result_from_counts(counts: Sequence[int]) -> RSResult:
    """Build one result from R/S/U counts for M and -M."""
    rm, sm, um, r_neg, s_neg, u_neg = (int(count) for count in counts)
    total = rm + sm + um

    if total == 0:
        return RSResult()

    return RSResult(
        total_groups=total,
        sample_count=total * GROUP_SIZE,
        RM_count=rm, SM_count=sm, UM_count=um,
        R_negM_count=r_neg, S_negM_count=s_neg, U_negM_count=u_neg,
        RM=rm / total, SM=sm / total, UM=um / total,
        R_negM=r_neg / total, S_negM=s_neg / total, U_negM=u_neg / total,
    )


def make_groups(channel: np.ndarray, pixel_limit: int) -> np.ndarray:
    """Make disjoint horizontal groups without joining different rows."""
    height, width = channel.shape
    if width < GROUP_SIZE or pixel_limit == 0:
        return np.empty((0, GROUP_SIZE), dtype=channel.dtype)

    full_rows, remainder = divmod(pixel_limit, width)
    usable_width = (width // GROUP_SIZE) * GROUP_SIZE
    groups = channel[:full_rows, :usable_width].reshape(-1, GROUP_SIZE)

    if remainder >= GROUP_SIZE and full_rows < height:
        usable_remainder = (remainder // GROUP_SIZE) * GROUP_SIZE
        last_row = channel[full_rows, :usable_remainder].reshape(-1, GROUP_SIZE)
        groups = np.concatenate((groups, last_row))

    return groups


def discrimination(groups: np.ndarray) -> np.ndarray:
    """Measure local variation: sum of adjacent absolute differences."""
    return np.abs(np.diff(groups, axis=1)).sum(axis=1)


def classify_counts(groups: np.ndarray, mask: Sequence[int]) -> tuple[int, int, int]:
    """Count regular, singular and unusable groups for one mask."""
    flipped = groups.copy()
    for column, operation in enumerate(mask):
        if operation == 1:
            flipped[:, column] ^= 1  # F1: 0<->1, 2<->3, ...
        elif operation == -1:
            values = flipped[:, column]
            flipped[:, column] += np.where(values % 2 == 0, -1, 1)  # F-1

    original = discrimination(groups)
    modified = discrimination(flipped)
    regular = int(np.count_nonzero(modified > original))
    singular = int(np.count_nonzero(modified < original))
    unusable = len(groups) - regular - singular
    return regular, singular, unusable


def rs_core(
    channel: np.ndarray,
    mask: Sequence[int] = DEFAULT_MASK,
    pixel_limit: Optional[int] = None,
) -> RSResult:
    """Classify adjacent pixel groups under M and -M (Fridrich RS)."""
    channel = np.asarray(channel)
    if channel.ndim != 2:
        raise ValueError("channel must be a 2D image array.")
    if not np.issubdtype(channel.dtype, np.integer):
        raise ValueError("channel must contain integers in the range 0..255.")
    if np.any(channel < 0) or np.any(channel > 255):
        raise ValueError("channel must contain integers in the range 0..255.")

    if len(mask) != GROUP_SIZE or any(
        not isinstance(value, (int, np.integer)) or isinstance(value, (bool, np.bool_))
        or value not in (-1, 0, 1)
        for value in mask
    ):
        raise ValueError("mask must contain four integers from {-1, 0, 1}.")
    if all(value == 0 for value in mask):
        raise ValueError("mask must flip at least one pixel.")

    if pixel_limit is None:
        pixel_limit = channel.size
    if (not isinstance(pixel_limit, (int, np.integer))
            or isinstance(pixel_limit, (bool, np.bool_))
            or not 0 <= pixel_limit <= channel.size):
        raise ValueError("pixel_limit must be an integer in the image pixel range.")

    groups = make_groups(channel, int(pixel_limit))
    if len(groups) == 0:
        return RSResult()

    # F-1 may temporarily produce -1 or 256, so do not flip uint8 values.
    signed_groups = groups.astype(np.int32)
    positive = classify_counts(signed_groups, mask)
    negative = classify_counts(signed_groups, tuple(-value for value in mask))
    return result_from_counts((*positive, *negative))


def payload_from_results(
    observed: RSResult,
    fully_flipped: RSResult,
    capacity_samples: int,
) -> RSPayloadEstimate:
    """Solve the closed-form RS payload equation from two measurements."""
    empty = RSPayloadEstimate(None, None, None, capacity_samples)

    values = (
        observed.RM, observed.SM, observed.R_negM, observed.S_negM,
        fully_flipped.RM, fully_flipped.SM,
        fully_flipped.R_negM, fully_flipped.S_negM,
    )
    numeric_values = [float(value) for value in values if value is not None]
    if len(numeric_values) != len(values):
        return empty

    rm, sm, r_neg, s_neg, rm1, sm1, r_neg1, s_neg1 = numeric_values
    d0 = rm - sm
    d1 = rm1 - sm1
    d_neg0 = r_neg - s_neg
    d_neg1 = r_neg1 - s_neg1

    a = 2.0 * (d1 + d0)
    b = d_neg0 - d_neg1 - d1 - 3.0 * d0
    c = d0 - d_neg0
    epsilon = 1e-12

    if abs(a) < epsilon:
        if abs(b) < epsilon:
            return empty
        roots = [-c / b]
    else:
        discriminant = b * b - 4.0 * a * c
        if discriminant < -epsilon:
            return empty
        discriminant = max(0.0, discriminant)
        root_delta = math.sqrt(discriminant)
        roots = [
            (-b + root_delta) / (2.0 * a),
            (-b - root_delta) / (2.0 * a),
        ]

    # The RS paper selects the solution whose absolute x value is smaller.
    root = min(roots, key=abs)
    if not math.isfinite(root) or abs(root - 0.5) < epsilon:
        return empty

    embedding_rate = root / (root - 0.5)
    if not math.isfinite(embedding_rate):
        return empty

    # Keep an out-of-range mathematical estimate visible, but do not turn it
    # into a negative or over-capacity payload size.
    if not 0.0 <= embedding_rate <= 1.0:
        return RSPayloadEstimate(
            embedding_rate=embedding_rate,
            estimated_payload_bits=None,
            expected_changed_samples=None,
            capacity_samples=capacity_samples,
            root=root,
        )

    return RSPayloadEstimate(
        embedding_rate=embedding_rate,
        estimated_payload_bits=embedding_rate * capacity_samples,
        expected_changed_samples=embedding_rate * capacity_samples / 2.0,
        capacity_samples=capacity_samples,
        root=root,
    )


def estimate_rs_payload(
    channel: np.ndarray,
    mask: Sequence[int] = DEFAULT_MASK,
    pixel_limit: Optional[int] = None,
) -> RSPayloadEstimate:
    """Estimate the LSB replacement rate using the classic RS equation."""
    channel = np.asarray(channel)
    observed = rs_core(channel, mask=mask, pixel_limit=pixel_limit)
    fully_flipped = rs_core(
        np.bitwise_xor(channel, 1),
        mask=mask,
        pixel_limit=pixel_limit,
    )
    capacity_samples = int(channel.size) if pixel_limit is None else int(pixel_limit)
    return payload_from_results(observed, fully_flipped, capacity_samples)


def progressive_prefix(
    channel: np.ndarray,
    mask: Sequence[int] = DEFAULT_MASK,
    step: int = 10,
) -> List[PrefixResult]:
    """Analyze growing row-major prefixes, including the full image."""
    if (isinstance(step, bool)
            or not isinstance(step, int)
            or not 1 <= step <= 100):
        raise ValueError("step must be an integer in the range 1..100.")

    channel = np.asarray(channel)
    if channel.ndim != 2:
        raise ValueError("channel must be a 2D image array.")

    results: List[PrefixResult] = []
    for percent in list(range(step, 100, step)) + [100]:
        pixel_count = math.ceil(channel.size * percent / 100)
        result = rs_core(channel, mask=mask, pixel_limit=pixel_count)
        results.append(PrefixResult(percent, pixel_count, result))
    return results


def pool_rs_results(results: Sequence[RSResult]) -> RSResult:
    """Pool channel counts first, then calculate their shared ratios."""
    counts = [0] * 6 # สร้าง List มาเก็บ 6 ค่าของ RS
    for result in results:
        for index, count in enumerate((
            result.RM_count, result.SM_count, result.UM_count,
            result.R_negM_count, result.S_negM_count, result.U_negM_count,
        )):
            counts[index] += count
    return result_from_counts(counts)


def load_image_targets(image_path: str) -> Dict[str, np.ndarray]:
    """Load 8-bit L/RGB channels; ignore alpha in RGBA images."""
    with Image.open(image_path) as image:
        if image.mode not in ("L", "RGB", "RGBA"):
            raise ValueError("RS supports 8-bit L, RGB, or RGBA images only.")
        pixels = np.asarray(image)

    if pixels.ndim == 2:
        return {"L": pixels}
    return {name: pixels[:, :, index] for index, name in enumerate("RGB")}


def analyze_rs(
    image_path: str,
    mask: Sequence[int] = DEFAULT_MASK,
    prefix_step: int = 10,
) -> Dict[str, Dict[str, Any]]:
    """Analyze each channel and pool RGB measurements for a Whole result."""
    targets = load_image_targets(image_path)
    report: Dict[str, Dict[str, Any]] = {}
    flipped_results: Dict[str, RSResult] = {}

    for name, channel in targets.items(): # Name: R|G|B, Channels คือ Array ค่า 0-255 ของ Channel[R, G, B]
        whole = rs_core(channel, mask=mask)
        fully_flipped = rs_core(np.bitwise_xor(channel, 1), mask=mask)
        flipped_results[name] = fully_flipped
        report[name] = {
            "whole": whole,
            "payload": payload_from_results(whole, fully_flipped, channel.size),
            "prefix": progressive_prefix(channel, mask=mask, step=prefix_step),
        }
        
    if len(targets) > 1: # ถ้าเป็นภาพ RGB ให้รวมผล RS Stats แต่ละช่องสี มาสรุปภาพรวม
        names = list(targets)
        whole_result = pool_rs_results([report[name]["whole"] for name in names])
        whole_flipped = pool_rs_results([flipped_results[name] for name in names])
        capacity_samples = sum(targets[name].size for name in names)
        first_prefix = report[names[0]]["prefix"]
        whole_prefix: List[PrefixResult] = []
        for index, item in enumerate(first_prefix):
            pooled = pool_rs_results([report[name]["prefix"][index].rs for name in names])
            whole_prefix.append(PrefixResult(item.percent, item.pixel_count, pooled))
        report = {
            "Whole": {
                "whole": whole_result,
                "payload": payload_from_results(
                    whole_result,
                    whole_flipped,
                    capacity_samples,
                ),
                "prefix": whole_prefix,
            },
            **report,
        }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="RS analysis for LSB image embedding.")
    parser.add_argument("filepath", help="Path to the image to analyze")
    parser.add_argument("--prefix-step", type=int, default=10,
                        help="Cumulative prefix step in percent (default: 10)")
    args = parser.parse_args()

    try:
        report = analyze_rs(args.filepath, prefix_step=args.prefix_step)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    def print_result(label: str, result: RSResult) -> None:
        if result.RM is None:
            print(f"  {label}: insufficient data (groups={result.total_groups})")
            return
        print(
            f"  {label:<10} groups={result.total_groups:<7} samples={result.sample_count:<7} "
            f"M: R={result.RM:.5f} S={result.SM:.5f} U={result.UM:.5f} "
            f"-M: R={result.R_negM:.5f} S={result.S_negM:.5f} U={result.U_negM:.5f}"
        )

    def print_payload(result: RSPayloadEstimate) -> None:
        if result.embedding_rate is None:
            print("  Estimated payload: N/A")
            return

        rate = f"{result.embedding_rate * 100:.2f}%"
        if result.estimated_payload_bits is None:
            print(f"  Estimated payload: rate={rate} (outside physical range 0..100%)")
            return

        print(
            f"  Estimated payload: rate={rate}, "
            f"bits={result.estimated_payload_bits:.0f}, "
            f"expected_changed={result.expected_changed_samples:.0f}"
        )

    print(f"Image: {args.filepath}")
    print(f"mask={DEFAULT_MASK}, prefix_step={args.prefix_step}%")
    for name, analysis in report.items():
        print(f"\n[{name}]")
        print_result("whole", analysis["whole"])
        print_payload(analysis["payload"])
        print("  Prefix (cumulative):")
        for item in analysis["prefix"]:
            print_result(f"0-{item.percent}%", item.rs)


if __name__ == "__main__":
    main()
