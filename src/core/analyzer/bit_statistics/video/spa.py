"""Sample Pair Analysis (SPA) สำหรับวิดีโอ (Dumitrescu, Wu, Wang 2003) - ต่อยอดจาก image_detector/spa.py

สิ่งที่เหมือนภาพ (ดูคำอธิบายเต็มใน image_detector/spa.py)
    คู่ pixel (u, v) แนวนอนไม่ซ้อน ไม่ข้ามแถว ; นับ C_m (|u>>1 - v>>1| = m), D_n (|u - v| = n),
    X_2m+1 (ค่าคู่ใหญ่กว่า), Y_2m+1 (ค่าคี่ใหญ่กว่า)
    สมการ (18), i = 0, pooling m = 0..j :  a p^2 + b p + c = 0
        a = (2C0 - C_j+1)/4 ,  b = -(2D0 - D_2j+2 + 2T)/2 ,  c = T = sum(Y - X) ; p = รากที่น้อยกว่า

สิ่งที่เพิ่มสำหรับวิดีโอ
    count ต่อเฟรมต่อช่อง = เวกเตอร์ [C(128) | D(256) | X(128) | Y(128) | pairs | samples] (642 ค่า)
    คู่ pixel ไม่ข้ามเฟรม ; รวม count ข้ามเฟรม/ช่องด้วยการบวก แล้วแก้สมการครั้งเดียวต่อช่วง
    ระดับผล: whole / per_frame / temporal_prefix / temporal_segments (เหตุผลเดียวกับ RS: แกน spatial เป็นงานของ chi-square)
"""
import argparse
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .video_io import check_frame, cumulative, iter_frames, prefix_ranges, sliding_ranges, video_info

DEFAULT_J = 30
DEFAULT_MIN_PAIRS = 100
TARGETS = ("Whole", "R", "G", "B")
C_SLICE, D_SLICE, X_SLICE, Y_SLICE = slice(0, 128), slice(128, 384), slice(384, 512), slice(512, 640)
PAIRS, SAMPLES = 640, 641
VECTOR_LENGTH = 642


@dataclass
class SPAStatistics:
    c_counts: List[int]
    d_counts: List[int]
    x_counts: List[int]
    y_counts: List[int]
    pair_count: int
    sample_count: int


@dataclass
class SPADiagnostics:
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


@dataclass
class SPAEstimate:
    """status: estimated / insufficient_pairs / assumption_failed_c / assumption_failed_d /
    degenerate_equation / no_real_root / non_finite_root / out_of_range"""

    embedding_rate: Optional[float]
    estimated_payload_bits: Optional[float]
    expected_changed_samples: Optional[float]
    pair_count: int
    sample_count: int
    coefficients: Optional[Tuple[float, float, float]] = None
    roots: Tuple[float, ...] = ()
    status: str = "unavailable"
    reason: Optional[str] = None
    diagnostics: Optional[SPADiagnostics] = None


@dataclass
class RangeResult:
    start: int                          # เฟรมแรก (รวม)
    end: int                            # ไม่รวม
    percent: Optional[int]              # มีค่าเฉพาะ prefix
    estimate: SPAEstimate


# --------------------------------------------------------------------------------------------
# นับสถิติของคู่ pixel (เหมือน image_detector แต่คืนเป็นเวกเตอร์ เพื่อรวมข้ามเฟรมด้วยการบวก)
# --------------------------------------------------------------------------------------------

def spa_vector(channel: np.ndarray) -> np.ndarray:
    height, width = channel.shape
    vector = np.zeros(VECTOR_LENGTH, dtype=np.int64)
    vector[SAMPLES] = channel.size
    usable_width = (width // 2) * 2
    if height == 0 or usable_width == 0:
        return vector
    pairs = channel[:, :usable_width].reshape(-1, 2)
    left, right = pairs[:, 0].astype(np.int32), pairs[:, 1].astype(np.int32)

    value_gap = np.abs(left - right)                              # |u - v|
    high_bit_gap = np.abs((left >> 1) - (right >> 1))             # |(u>>1) - (v>>1)|
    vector[D_SLICE] = np.bincount(value_gap, minlength=256)[:256]
    vector[C_SLICE] = np.bincount(high_bit_gap, minlength=128)[:128]

    has_odd_gap = value_gap % 2 == 1
    gap_index = (value_gap[has_odd_gap] - 1) // 2                 # m ของคู่ที่ value_gap = 2m+1
    left_odd, right_odd = left[has_odd_gap], right[has_odd_gap]
    even_member = np.where(left_odd % 2 == 0, left_odd, right_odd)
    odd_member = np.where(left_odd % 2 == 0, right_odd, left_odd)
    even_is_larger = even_member > odd_member                     # True -> X ; False -> Y
    vector[X_SLICE] = np.bincount(gap_index[even_is_larger], minlength=128)[:128]
    vector[Y_SLICE] = np.bincount(gap_index[~even_is_larger], minlength=128)[:128]
    vector[PAIRS] = len(pairs)
    return vector


def statistics_from_vector(vector: np.ndarray) -> SPAStatistics:
    return SPAStatistics(vector[C_SLICE].tolist(), vector[D_SLICE].tolist(), vector[X_SLICE].tolist(),
                         vector[Y_SLICE].tolist(), int(vector[PAIRS]), int(vector[SAMPLES]))


def validate_parameters(j: int, min_pairs: int) -> None:
    if isinstance(j, bool) or not isinstance(j, int) or not 0 <= j <= 126:
        raise ValueError("j must be an integer in the range 0..126.")
    if isinstance(min_pairs, bool) or not isinstance(min_pairs, int) or min_pairs < 1:
        raise ValueError("min_pairs must be a positive integer.")


def estimate_spa(statistics: SPAStatistics, j: int = DEFAULT_J, min_pairs: int = DEFAULT_MIN_PAIRS) -> SPAEstimate:
    """ประมาณ p จากสมการ (18) (คัดลอกตรรกะจาก image_detector/spa.py)"""
    validate_parameters(j, min_pairs)
    c_counts, d_counts = statistics.c_counts, statistics.d_counts
    x_counts, y_counts = statistics.x_counts, statistics.y_counts

    sum_y_minus_x = sum(y_counts[m] - x_counts[m] for m in range(j + 1))      # T
    a_term = (2 * c_counts[0] - c_counts[j + 1]) / 4.0
    b_term = -(2 * d_counts[0] - d_counts[2 * j + 2] + 2 * sum_y_minus_x) / 2.0
    constant_term = float(sum_y_minus_x)
    coefficients = (a_term, b_term, constant_term)
    diagnostics = SPADiagnostics(
        j=j, c0=c_counts[0], c_j_plus_1=c_counts[j + 1], d0=d_counts[0], d_2j_plus_2=d_counts[2 * j + 2],
        sum_x=sum(x_counts[:j + 1]), sum_y=sum(y_counts[:j + 1]), trace_difference=sum_y_minus_x,
    )

    def unavailable(status: str, reason: str) -> SPAEstimate:
        return SPAEstimate(None, None, None, statistics.pair_count, statistics.sample_count,
                           coefficients=coefficients, status=status, reason=reason, diagnostics=diagnostics)

    if statistics.pair_count < min_pairs:
        return unavailable("insufficient_pairs", f"Fewer than {min_pairs} complete sample pairs are available.")
    if 2 * c_counts[0] <= c_counts[j + 1]:
        return unavailable("assumption_failed_c", "The required relation 2*C0 > C(j+1) is not satisfied.")
    if 2 * d_counts[0] < d_counts[2 * j + 2]:
        return unavailable("assumption_failed_d", "The required relation 2*D0 >= D(2j+2) is not satisfied.")

    tiny = 1e-12
    if abs(a_term) < tiny:
        if abs(b_term) < tiny:
            return unavailable("degenerate_equation", "Both quadratic and linear terms are effectively zero.")
        roots = (-constant_term / b_term,)
    else:
        discriminant = b_term ** 2 - 4.0 * a_term * constant_term
        diagnostics.discriminant = discriminant
        if discriminant < -tiny:
            return unavailable("no_real_root", "The SPA equation has a negative discriminant and no real root.")
        sqrt_discriminant = math.sqrt(max(0.0, discriminant))
        roots = ((-b_term + sqrt_discriminant) / (2.0 * a_term), (-b_term - sqrt_discriminant) / (2.0 * a_term))

    embedding_rate = min(roots)
    diagnostics.selected_root = embedding_rate
    shared = dict(pair_count=statistics.pair_count, sample_count=statistics.sample_count,
                  coefficients=coefficients, roots=roots, diagnostics=diagnostics)
    if not math.isfinite(embedding_rate):
        return SPAEstimate(None, None, None, status="non_finite_root",
                           reason="The selected mathematical root is not finite.", **shared)
    if not 0.0 <= embedding_rate <= 1.0:
        return SPAEstimate(embedding_rate, None, None, status="out_of_range",
                           reason="The selected root lies outside the physical 0..100% range.", **shared)
    return SPAEstimate(embedding_rate, embedding_rate * statistics.sample_count,
                       embedding_rate * statistics.sample_count / 2.0, status="estimated", reason=None, **shared)


# --------------------------------------------------------------------------------------------
# วิดีโอ
# --------------------------------------------------------------------------------------------

class SPAVideo:
    def __init__(self, height: int, width: int, j: int = DEFAULT_J, min_pairs: int = DEFAULT_MIN_PAIRS,
                 prefix_step: int = 10, segment_percent: int = 10, segment_step: int = 5):
        validate_parameters(j, min_pairs)
        self.height, self.width, self.j, self.min_pairs = height, width, j, min_pairs
        self.prefix_step, self.segment_percent, self.segment_step = prefix_step, segment_percent, segment_step
        self.vectors: List[np.ndarray] = []          # แต่ละตัว (3, 642)

    def add(self, frame: np.ndarray) -> None:
        frame = check_frame(frame, self.height, self.width)
        self.vectors.append(np.stack([spa_vector(frame[:, :, c]) for c in range(3)]))

    def finish(self) -> Dict[str, Any]:
        if not self.vectors:
            raise ValueError("No frames were added.")
        vectors = np.stack(self.vectors)                                          # (F, 3, 642)
        frame_count = vectors.shape[0]
        temporal_prefix = prefix_ranges(frame_count, self.prefix_step)
        temporal_segments = sliding_ranges(frame_count, self.segment_percent, self.segment_step)

        targets: Dict[str, Dict[str, Any]] = {}
        for name in TARGETS:
            series = vectors.sum(axis=1) if name == "Whole" else vectors[:, "RGB".index(name)]
            cum = cumulative(series)
            span = lambda s, e: estimate_spa(statistics_from_vector(cum[e] - cum[s]), self.j, self.min_pairs)
            targets[name] = {
                "statistics": statistics_from_vector(cum[-1]),
                "whole": span(0, frame_count),
                "per_frame": [span(f, f + 1) for f in range(frame_count)],
                "temporal_prefix": [RangeResult(0, end, p, span(0, end)) for p, end in temporal_prefix],
                "temporal_segments": [RangeResult(s, e, None, span(s, e)) for s, e in temporal_segments],
            }
        return {"frame_count": frame_count, "j": self.j, "min_pairs": self.min_pairs, "targets": targets}


def analyze_spa(video_path: str, j: int = DEFAULT_J, min_pairs: int = DEFAULT_MIN_PAIRS, prefix_step: int = 10,
                segment_percent: int = 10, segment_step: int = 5,
                start_frame: int = 0, frame_count: Optional[int] = None) -> Dict[str, Any]:
    info = video_info(video_path)
    detector = SPAVideo(info["height"], info["width"], j, min_pairs, prefix_step, segment_percent, segment_step)
    for _, frame in iter_frames(video_path, start_frame, frame_count):
        detector.add(frame)
    return {"info": info, **detector.finish()}


def _rate(estimate: SPAEstimate) -> str:
    return "   N/A" if estimate.embedding_rate is None else f"{estimate.embedding_rate:.4f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample Pair Analysis for a video (per frame and temporal ranges).")
    parser.add_argument("filepath")
    parser.add_argument("--j", type=int, default=DEFAULT_J)
    parser.add_argument("--min-pairs", type=int, default=DEFAULT_MIN_PAIRS)
    parser.add_argument("--prefix-step", type=int, default=10)
    parser.add_argument("--segment-percent", type=int, default=10)
    parser.add_argument("--segment-step", type=int, default=5)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument("--frame-count", type=int, default=None)
    parser.add_argument("--per-frame", action="store_true", help="Print the estimated rate of every frame")
    args = parser.parse_args()
    try:
        report = analyze_spa(args.filepath, args.j, args.min_pairs, args.prefix_step, args.segment_percent,
                             args.segment_step, args.start_frame, args.frame_count)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))

    print(f"Video: {args.filepath}  frames={report['frame_count']}  j={report['j']}  min_pairs={report['min_pairs']}")
    for name, r in report["targets"].items():
        whole = r["whole"]
        rates = [e.embedding_rate for e in r["per_frame"] if e.embedding_rate is not None]
        print(f"\n[{name}] whole: rate={_rate(whole)} status={whole.status} pairs={whole.pair_count}")
        if rates:
            print(f"  per frame: mean={np.mean(rates):.4f} min={np.min(rates):.4f} max={np.max(rates):.4f}")
        print("  temporal prefix: " + "  ".join(f"0-{x.percent}%={_rate(x.estimate)}" for x in r["temporal_prefix"]))
        if args.per_frame:
            print("  per frame: " + " ".join(_rate(e) for e in r["per_frame"]))


if __name__ == "__main__":
    main()
