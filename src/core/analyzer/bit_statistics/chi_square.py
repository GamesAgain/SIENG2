import argparse
from dataclasses import dataclass
import math
from typing import Any, Dict, List, Optional
import numpy as np
from scipy.stats import chi2
from PIL import Image


@dataclass
class ChiSquareResult:
    chi_square_total: Optional[float]
    p_value: Optional[float]
    dof: Optional[int] = None
    sample_count: Optional[int] = None
    valid_pairs: Optional[int] = None


@dataclass
class PrefixResult:
    percent: int
    sample_count: int
    chi_square: ChiSquareResult


@dataclass
class SegmentResult:
    start: int
    end: int
    sample_count: int
    chi_square: ChiSquareResult


def chi_square_pov(samples: np.ndarray, min_expected: float = 5) -> ChiSquareResult:
    """
    Chi-square Pairs-of-Values test over a flat array of 8-bit pixel values.
    """

    # 0. Prepare & validation
    samples = np.asarray(samples).ravel()

    try:
        min_expected = float(min_expected)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_expected must be a finite number greater than or equal to 5.") from exc

    if not np.isfinite(min_expected) or min_expected < 5:
        raise ValueError("min_expected must be a finite number greater than or equal to 5.")

    if samples.size == 0:
        return ChiSquareResult(
            chi_square_total=None,
            p_value=None,
            sample_count=0,
            valid_pairs=0,
        )

    if not np.issubdtype(samples.dtype, np.integer):
        raise ValueError("samples must contain integer values in the range 0..255.")
    if np.any(samples < 0) or np.any(samples > 255):
        raise ValueError("samples must contain integer values in the range 0..255.")

    # 1. Histogram of 8-bit pixel values
    hist = np.bincount(samples, minlength=256)
    chi_square_total = 0.0
    valid_pairs = 0

    # 2. Pair values that differ only in the LSB: (2k, 2k+1)
    for value in range(0, 256, 2):
        observed = int(hist[value])
        paired = int(hist[value + 1])
        expected = (observed + paired) / 2.0

        if expected < min_expected:
            continue

        # 3. Pearson chi-square statistic ต่อคู่ PoV ที่ expected >= min_expected
        chi_square_total += ((observed - expected) ** 2) / expected
        valid_pairs += 1

    if valid_pairs < 2:
        return ChiSquareResult(
            chi_square_total=None,
            p_value=None,
            sample_count=int(samples.size),
            valid_pairs=valid_pairs,
        )

    # 4. Survival function (right-tail p-value)
    degrees_of_freedom = valid_pairs - 1
    p_value = float(chi2.sf(chi_square_total, degrees_of_freedom))

    return ChiSquareResult(
        chi_square_total=chi_square_total,
        dof=degrees_of_freedom,
        p_value=p_value,
        sample_count=int(samples.size),
        valid_pairs=valid_pairs,
    )


def progressive_prefix(samples: np.ndarray, min_expected: float = 5, step: int = 10) -> List[PrefixResult]:
    """
    Run Chi-square PoV over growing prefixes of the image like
    0-10%, 0-20%, 0-30% ... 0-100% (whole-image), cumulative จากจุดเริ่มภาพ
    """
    results: List[PrefixResult] = []

    # ถ้ามี channel (H,W,C) -> reshape เป็น (H*W, C) ก่อน เพื่อนับเป็นหน่วย pixel ไม่ใช่หน่วย sample ดิบ
    if samples.ndim == 3:
        flat_pixels = samples.reshape(-1, samples.shape[2])
    else:
        flat_pixels = samples.reshape(-1, 1)

    total_pixels = flat_pixels.shape[0]

    percents = list(range(step, 100, step)) + [100]  # กัน step หาร 100 ไม่ลงตัว ไม่ให้ขาด 100%
    for percent in percents:
        n = math.ceil(total_pixels * percent / 100)
        prefix_values = flat_pixels[:n].ravel()

        result = chi_square_pov(prefix_values, min_expected=min_expected)
        results.append(
            PrefixResult(
                percent=percent,
                sample_count=int(prefix_values.size),
                chi_square=result,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Sliding segments in raster order (non-cumulative)
# ---------------------------------------------------------------------------

def sliding_segment(
    samples: np.ndarray,
    min_expected: float = 5,
    segment_percent: int = 10,
    step_percent: int = 5,
) -> List[SegmentResult]:
    """
    Analyze fixed-length pixel ranges in row-major order.
    start is inclusive and end is exclusive; both count pixel positions.
    For RGB data, all channels of each pixel stay in the same segment.
    """
    if samples.ndim not in (2, 3):
        raise ValueError("samples must be a 2D or 3D image array.")
    if not 0 < segment_percent <= 100:
        raise ValueError("segment_percent must be in the range 1..100.")
    if not 0 < step_percent <= segment_percent:
        raise ValueError("step_percent must be in the range 1..segment_percent.")

    if samples.ndim == 3:
        flat_pixels = samples.reshape(-1, samples.shape[2])
    else:
        flat_pixels = samples.reshape(-1, 1)

    total_pixels = flat_pixels.shape[0]
    if total_pixels == 0:
        return []

    segment_size = math.ceil(total_pixels * segment_percent / 100)
    stride = max(1, math.ceil(total_pixels * step_percent / 100))

    starts = list(range(0, total_pixels - segment_size + 1, stride))
    last_start = total_pixels - segment_size
    if starts[-1] != last_start:
        starts.append(last_start)

    results: List[SegmentResult] = []
    for start in starts:
        end = start + segment_size
        segment_values = flat_pixels[start:end].ravel()
        result = chi_square_pov(segment_values, min_expected=min_expected)

        results.append(
            SegmentResult(
                start=start,
                end=end,
                sample_count=int(segment_values.size),
                chi_square=result,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Image loading & orchestration
# ---------------------------------------------------------------------------

def load_image_targets(image_path: str) -> Dict[str, np.ndarray]:
    """
    Load an image and build the analysis targets dict:
      - ภาพสี (RGB): "Whole" (รวมทุก channel ปนกันในฮิสโตแกรมเดียว), แยก "R", "G", "B"
      - ภาพเกรย์สเกล: "L" เท่านั้น (ไม่ทำ "Whole" ซ้ำ เพราะเป็น array เดียวกันกับ "L" เป๊ะ ๆ)
    """
    img = Image.open(image_path)

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    arr = np.array(img)
    targets: Dict[str, np.ndarray] = {}

    if arr.ndim == 2:
        targets["L"] = arr
    else:
        targets["Whole"] = arr
        channel_names = ["R", "G", "B"]
        for i, name in enumerate(channel_names[: arr.shape[2]]):
            targets[name] = arr[:, :, i]

    return targets


def analyze_chi_square(
    image_path: str,
    min_expected: float = 5,
    prefix_step: int = 10,
    segment_percent: int = 10,
    segment_step: int = 5,
) -> Dict[str, Any]:
    """
    รัน chi-square PoV attack ครบชุดต่อ target (Whole / R / G / B / L):
      - whole: chi-square บนทั้ง target
      - prefix: progressive prefix (cumulative) หา breakpoint หยาบ ๆ
      - segments: ช่วง pixel ตามลำดับ raster scan แบบไม่สะสม
    """
    targets = load_image_targets(image_path)

    report: Dict[str, Any] = {}

    for name, data in targets.items():
        flat_values = np.asarray(data).ravel()

        report[name] = {
            "whole": chi_square_pov(flat_values, min_expected=min_expected),
            "prefix": progressive_prefix(data, min_expected=min_expected, step=prefix_step),
            "segments": sliding_segment(
                data,
                min_expected=min_expected,
                segment_percent=segment_percent,
                step_percent=segment_step,
            ),
        }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chi-square PoV analysis for an image."
    )
    parser.add_argument("filepath", help="Path to the image to analyze")
    parser.add_argument(
        "--min-expected", type=float, default=5,
        help="Minimum expected count per PoV (default: 5)",
    )
    parser.add_argument(
        "--prefix-step", type=int, default=10,
        help="Cumulative prefix step in percent (default: 10)",
    )
    parser.add_argument(
        "--segment-percent", type=int, default=10,
        help="Segment length in percent of pixels (default: 10)",
    )
    parser.add_argument(
        "--segment-step", type=int, default=5,
        help="Distance between segment starts in percent (default: 5)",
    )
    args = parser.parse_args()

    if not 1 <= args.prefix_step <= 100:
        parser.error("--prefix-step must be in the range 1..100.")

    try:
        report = analyze_chi_square(
            args.filepath,
            min_expected=args.min_expected,
            prefix_step=args.prefix_step,
            segment_percent=args.segment_percent,
            segment_step=args.segment_step,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    def print_result(label: str, result: ChiSquareResult) -> None:
        chi_square = (
            f"{result.chi_square_total:.6g}"
            if result.chi_square_total is not None else "N/A"
        )
        p_value = f"{result.p_value:.5f}" if result.p_value is not None else "N/A"
        print(
            f"  {label:<22} chi2={chi_square:<12} p={p_value:<10} "
            f"dof={result.dof!s:<4} pairs={result.valid_pairs!s:<4} "
            f"samples={result.sample_count}"
        )

    print(f"Image: {args.filepath}")
    print(
        f"min_expected={args.min_expected:g}, prefix_step={args.prefix_step}%, "
        f"segment={args.segment_percent}%, segment_step={args.segment_step}%"
    )

    for name, analysis in report.items():
        print(f"\n[{name}]")
        print_result("whole", analysis["whole"])

        print("  Prefix (cumulative):")
        for item in analysis["prefix"]:
            print_result(f"0-{item.percent}%", item.chi_square)

        print("  Segments (pixel positions, end exclusive):")
        for item in analysis["segments"]:
            print_result(f"[{item.start}:{item.end})", item.chi_square)


if __name__ == "__main__":
    main()
