"""RS Analysis สำหรับวิดีโอ (Fridrich, Goljan, Du) - ต่อยอดจาก image_detector/rs_analysis.py

สิ่งที่เหมือนภาพ (ดูคำอธิบายเต็มใน image_detector/rs_analysis.py)
    กลุ่ม 4 pixel แนวนอน (ไม่ข้ามแถว) ; f(G) = sum |ผลต่างข้างเคียง| ; flip ตาม mask M = (0,1,1,0) และ -M
    -> สัดส่วน Regular / Singular / Unusable ; วัดทั้งเฟรมจริงและเฟรมที่ XOR LSB ทั้งหมด
    แก้สมการ 2(d1+d0)x^2 + (d-0 - d-1 - d1 - 3 d0)x + (d0 - d-0) = 0 ,  rate = x / (x - 1/2)

สิ่งที่เพิ่มสำหรับวิดีโอ
    count ต่อเฟรมต่อช่อง = (RM, SM, UM, R-M, S-M, U-M) ของเฟรมจริง และของเฟรมที่ flip LSB (รวม 12 ค่า)
    กลุ่มไม่ข้ามเฟรม (แต่ละเฟรมแบ่งกลุ่มของตัวเอง) แล้ว "รวมจำนวนกลุ่ม" ข้ามเฟรม/ช่องก่อนแก้สมการ
    (ไม่เฉลี่ย rate ของแต่ละเฟรม เพราะสมการไม่เป็นเชิงเส้น และ count รวมนิ่งกว่า)
    ระดับผล: whole / per_frame / temporal_prefix / temporal_segments  (RS ใช้ประมาณอัตราของการฝังแบบสุ่ม
    จึงไม่ทำแกน spatial ซึ่งเป็นงานของ chi-square)
    capacity_samples ของช่วง = จำนวนเฟรม x H x W x จำนวนช่อง (นิยามเดียวกับภาพ: นับทุก sample ของช่อง)
"""
import argparse
import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from src.core.analyzer.models.avi import (
    AVIPrefixResult,
    AVIRSPayloadEstimate as RSPayloadEstimate,
    AVIRSMeasurement as RSMeasurement,
    AVIRSStatistics as RSResult,
    AVISegmentResult,
)

from .video_io import check_frame, cumulative, iter_frames, prefix_ranges, sliding_ranges, video_info

DEFAULT_MASK = (0, 1, 1, 0)
GROUP_SIZE = 4
TARGETS = ("Whole", "R", "G", "B")


# --------------------------------------------------------------------------------------------
# แกนหลัก (เหมือน image_detector)
# --------------------------------------------------------------------------------------------

def validate_mask(mask: Sequence[int]) -> tuple:
    if len(mask) != GROUP_SIZE or any(
        not isinstance(value, (int, np.integer)) or isinstance(value, (bool, np.bool_)) or value not in (-1, 0, 1)
        for value in mask
    ):
        raise ValueError("mask must contain four integers from {-1, 0, 1}.")
    if all(value == 0 for value in mask):
        raise ValueError("mask must flip at least one pixel.")
    return tuple(int(v) for v in mask)


def result_from_counts(counts: Sequence[int]) -> RSResult:
    regular_m, singular_m, unusable_m, regular_neg_m, singular_neg_m, unusable_neg_m = (int(c) for c in counts)
    total_groups = regular_m + singular_m + unusable_m
    if total_groups == 0:
        return RSResult()
    return RSResult(
        total_groups=total_groups, sample_count=total_groups * GROUP_SIZE,
        RM_count=regular_m, SM_count=singular_m, UM_count=unusable_m,
        R_negM_count=regular_neg_m, S_negM_count=singular_neg_m, U_negM_count=unusable_neg_m,
        RM=regular_m / total_groups, SM=singular_m / total_groups, UM=unusable_m / total_groups,
        R_negM=regular_neg_m / total_groups, S_negM=singular_neg_m / total_groups,
        U_negM=unusable_neg_m / total_groups,
    )


def make_groups(channel: np.ndarray) -> np.ndarray:
    """กลุ่ม 4 pixel แนวนอนทั้งเฟรม ไม่ซ้อน ไม่ข้ามแถว (ตัดท้ายแถวที่ไม่ครบ 4)"""
    height, width = channel.shape
    usable_width = (width // GROUP_SIZE) * GROUP_SIZE
    if usable_width == 0:
        return np.empty((0, GROUP_SIZE), dtype=np.int32)
    return channel[:, :usable_width].reshape(-1, GROUP_SIZE).astype(np.int32)   # int32 กัน F-1 ได้ -1 / 256


def discrimination(groups: np.ndarray) -> np.ndarray:
    return np.abs(np.diff(groups, axis=1)).sum(axis=1)


def flip(values: np.ndarray, operation: int) -> np.ndarray:
    """1 = F1 (สลับ LSB), -1 = F-1 (เลื่อนคู่: คู่ -> -1, คี่ -> +1), 0 = ไม่แตะ"""
    if operation == 1:
        return values ^ 1
    if operation == -1:
        return values + np.where(values % 2 == 0, -1, 1)
    return values


def classify_counts(groups: np.ndarray, mask: Sequence[int]) -> tuple:
    flipped = groups.copy()
    for column, operation in enumerate(mask):
        flipped[:, column] = flip(flipped[:, column], operation)
    before, after = discrimination(groups), discrimination(flipped)
    regular = int(np.count_nonzero(after > before))
    singular = int(np.count_nonzero(after < before))
    return regular, singular, len(groups) - regular - singular


def rs_counts(channel: np.ndarray, mask: Sequence[int] = DEFAULT_MASK) -> np.ndarray:
    """(RM, SM, UM, R-M, S-M, U-M) ของ 1 ช่องของ 1 เฟรม"""
    groups = make_groups(channel)
    if len(groups) == 0:
        return np.zeros(6, dtype=np.int64)
    return np.array((*classify_counts(groups, mask), *classify_counts(groups, tuple(-v for v in mask))),
                    dtype=np.int64)


def payload_from_results(observed: RSResult, fully_flipped: RSResult, capacity_samples: int) -> RSPayloadEstimate:
    """แก้สมการ RS ของ Fridrich จากภาพจริง (observed) และภาพที่ flip LSB ทั้งภาพ (fully_flipped)"""
    def unavailable(status: str, reason: str) -> RSPayloadEstimate:
        return RSPayloadEstimate(None, None, None, capacity_samples, status=status, reason=reason)

    values = (observed.RM, observed.SM, observed.R_negM, observed.S_negM,
              fully_flipped.RM, fully_flipped.SM, fully_flipped.R_negM, fully_flipped.S_negM)
    if any(value is None for value in values):
        return unavailable("insufficient_groups", "No complete 4-pixel groups are available to measure.")
    (regular_m, singular_m, regular_neg_m, singular_neg_m,
     regular_m_flipped, singular_m_flipped, regular_neg_m_flipped, singular_neg_m_flipped) = (float(v) for v in values)

    gap_observed = regular_m - singular_m                                  # d0
    gap_flipped = regular_m_flipped - singular_m_flipped                   # d1
    gap_observed_neg = regular_neg_m - singular_neg_m                      # d-0
    gap_flipped_neg = regular_neg_m_flipped - singular_neg_m_flipped       # d-1

    a_term = 2.0 * (gap_flipped + gap_observed)
    b_term = gap_observed_neg - gap_flipped_neg - gap_flipped - 3.0 * gap_observed
    constant_term = gap_observed - gap_observed_neg
    tiny = 1e-12
    if abs(a_term) < tiny:
        if abs(b_term) < tiny:
            return unavailable("degenerate_equation", "Both the quadratic and linear terms are effectively zero.")
        roots = [-constant_term / b_term]
    else:
        discriminant = b_term * b_term - 4.0 * a_term * constant_term
        if discriminant < -tiny:
            return unavailable("no_real_root", "The RS equation has a negative discriminant and no real root.")
        sqrt_discriminant = math.sqrt(max(0.0, discriminant))
        roots = [(-b_term + sqrt_discriminant) / (2.0 * a_term), (-b_term - sqrt_discriminant) / (2.0 * a_term)]

    root = min(roots, key=abs)
    if not math.isfinite(root) or abs(root - 0.5) < tiny:
        return unavailable("non_finite_root", "The selected root is not finite or makes the rate undefined.")
    embedding_rate = root / (root - 0.5)
    if not math.isfinite(embedding_rate):
        return unavailable("non_finite_root", "The embedding rate computed from the root is not finite.")
    if not 0.0 <= embedding_rate <= 1.0:
        return RSPayloadEstimate(embedding_rate, None, None, capacity_samples, root, status="out_of_range",
                                 reason="The estimated rate lies outside the physical 0..100% range.")
    return RSPayloadEstimate(embedding_rate, embedding_rate * capacity_samples,
                             embedding_rate * capacity_samples / 2.0, capacity_samples, root, status="estimated")


def measure(observed_counts: np.ndarray, flipped_counts: np.ndarray, capacity_samples: int) -> RSMeasurement:
    observed = result_from_counts(observed_counts)
    return RSMeasurement(observed, payload_from_results(observed, result_from_counts(flipped_counts),
                                                        int(capacity_samples)))


# --------------------------------------------------------------------------------------------
# วิดีโอ: สะสม count ต่อเฟรม แล้วรวม
# --------------------------------------------------------------------------------------------

class RSVideo:
    def __init__(self, height: int, width: int, mask: Sequence[int] = DEFAULT_MASK, prefix_step: int = 10,
                 segment_percent: int = 10, segment_step: int = 5):
        self.height, self.width = height, width
        self.mask = validate_mask(mask)
        self.prefix_step, self.segment_percent, self.segment_step = prefix_step, segment_percent, segment_step
        self.observed: List[np.ndarray] = []      # แต่ละตัว (3, 6) : ช่อง R, G, B
        self.flipped: List[np.ndarray] = []

    def add(self, frame: np.ndarray) -> None:
        frame = check_frame(frame, self.height, self.width)
        self.observed.append(np.stack([rs_counts(frame[:, :, c], self.mask) for c in range(3)]))
        self.flipped.append(np.stack([rs_counts(frame[:, :, c] ^ 1, self.mask) for c in range(3)]))

    def finish(self) -> Dict[str, Any]:
        if not self.observed:
            raise ValueError("No frames were added.")
        observed, flipped = np.stack(self.observed), np.stack(self.flipped)       # (F, 3, 6)
        frame_count = observed.shape[0]
        samples_per_frame_channel = self.height * self.width
        temporal_prefix = prefix_ranges(frame_count, self.prefix_step)
        temporal_segments = sliding_ranges(frame_count, self.segment_percent, self.segment_step)

        targets: Dict[str, Dict[str, Any]] = {}
        for name in TARGETS:
            if name == "Whole":                    # รวมจำนวนกลุ่มของ 3 ช่อง (ไม่เฉลี่ยสัดส่วน)
                obs, flp, channels = observed.sum(axis=1), flipped.sum(axis=1), 3
            else:
                c = "RGB".index(name)
                obs, flp, channels = observed[:, c], flipped[:, c], 1
            cum_obs, cum_flp = cumulative(obs), cumulative(flp)
            capacity = lambda frames: frames * samples_per_frame_channel * channels
            span = lambda s, e: measure(cum_obs[e] - cum_obs[s], cum_flp[e] - cum_flp[s], capacity(e - s))
            targets[name] = {
                "whole": span(0, frame_count),
                "per_frame": [span(f, f + 1) for f in range(frame_count)],
                "temporal_prefix": [AVIPrefixResult(p, end, span(0, end)) for p, end in temporal_prefix],
                "temporal_segments": [AVISegmentResult(s, e, span(s, e)) for s, e in temporal_segments],
            }
        return {"frame_count": frame_count, "mask": self.mask, "targets": targets}


def analyze_rs(video_path: str, mask: Sequence[int] = DEFAULT_MASK, prefix_step: int = 10,
               segment_percent: int = 10, segment_step: int = 5,
               start_frame: int = 0, frame_count: Optional[int] = None) -> Dict[str, Any]:
    info = video_info(video_path)
    detector = RSVideo(info["height"], info["width"], mask, prefix_step, segment_percent, segment_step)
    for _, frame in iter_frames(video_path, start_frame, frame_count):
        detector.add(frame)
    return {"info": info, **detector.finish()}


def _rate(measurement: RSMeasurement) -> str:
    rate = measurement.payload.embedding_rate
    return "   N/A" if rate is None else f"{rate:.4f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="RS analysis for a video (per frame and temporal ranges).")
    parser.add_argument("filepath")
    parser.add_argument("--prefix-step", type=int, default=10)
    parser.add_argument("--segment-percent", type=int, default=10)
    parser.add_argument("--segment-step", type=int, default=5)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument("--frame-count", type=int, default=None)
    parser.add_argument("--per-frame", action="store_true", help="Print the estimated rate of every frame")
    args = parser.parse_args()
    try:
        report = analyze_rs(args.filepath, DEFAULT_MASK, args.prefix_step, args.segment_percent,
                            args.segment_step, args.start_frame, args.frame_count)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))

    print(f"Video: {args.filepath}  frames={report['frame_count']}  mask={report['mask']}")
    for name, r in report["targets"].items():
        whole = r["whole"]
        rates = [m.payload.embedding_rate for m in r["per_frame"] if m.payload.embedding_rate is not None]
        print(f"\n[{name}] whole: rate={_rate(whole)} status={whole.payload.status} "
              f"RM={whole.rs.RM:.4f} SM={whole.rs.SM:.4f} R-M={whole.rs.R_negM:.4f} S-M={whole.rs.S_negM:.4f}")
        if rates:
            print(f"  per frame: mean={np.mean(rates):.4f} min={np.min(rates):.4f} max={np.max(rates):.4f}")
        print("  temporal prefix: " + "  ".join(f"0-{x.percent}%={_rate(x.analysis)}" for x in r["temporal_prefix"]))
        if args.per_frame:
            print("  per frame: " + " ".join(_rate(m) for m in r["per_frame"]))


if __name__ == "__main__":
    main()
