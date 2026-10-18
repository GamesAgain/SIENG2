"""Chi-square Pairs-of-Values (PoV) สำหรับวิดีโอ - ต่อยอดจาก image_detector/chi_square.py

สิ่งที่เหมือนภาพ (ดูคำอธิบายเต็มใน image_detector/chi_square.py)
    LSB replacement ทำให้จำนวน pixel ค่า 2k กับ 2k+1 เท่ากันในทุกคู่
    e = (n_2k + n_2k+1) / 2 ,  chi2 = sum (n_2k - e)^2 / e  เฉพาะคู่ที่ e >= min_expected ,  dof = คู่ที่ใช้ - 1
    p = P(chi2_dof >= chi2)   p สูง = คู่ค่าเท่ากัน = น่าสงสัย ; p ต่ำ = ดูเหมือน clean

สิ่งที่เพิ่มสำหรับวิดีโอ
    chi-square คำนวณจาก histogram 256 ค่าเท่านั้น และ histogram บวกกันได้ จึงเก็บต่อเฟรมแล้วรวมได้อิสระ
    sequential ในวิดีโอมี 2 แกน จึงมี prefix / segment 2 ชุด
        temporal  (หน่วย = เฟรม)  ฝังต่อเนื่องทั้งวิดีโอ: เฟรมต้นฝังเต็ม เฟรมท้าย clean
        spatial   (หน่วย = pixel) ฝังจากต้นเฟรมทุกเฟรม: รวม histogram ของ pixel ช่วงเดียวกันจากทุกเฟรม
    targets: Whole (RGB ทุกช่องรวม) / R / G / B  ; Whole นับทุก channel ของ pixel ไปด้วยกันเหมือนภาพ

วิธีเก็บ count ของแกน spatial ให้ถูก (ไม่ต้องคำนวณซ้ำทีละ prefix)
    รวมจุดตัดทั้งหมดของ prefix และ segment เป็น "boundaries" แล้วแบ่ง pixel ของเฟรมเป็นชิ้น (chunk) ตามจุดตัด
    เก็บ histogram ต่อชิ้น (รวมทุกเฟรม) -> prefix / segment = ผลรวมของชิ้นที่อยู่ในช่วง (cumsum)

ตัวแปรสำคัญ
    frame_histograms[f, t, v]   จำนวน sample ค่า v ของ target t ในเฟรม f
    chunk_histograms[k, t, v]   จำนวน sample ค่า v ของ target t ในชิ้น pixel ที่ k (รวมทุกเฟรม)
"""
import argparse
from typing import Any, Dict, List, Optional

import numpy as np
from scipy.stats import chi2

from src.core.analyzer.models.avi import (
    AVIChiSquareAnalysis as ChiSquareResult,
    AVIPrefixResult as PrefixResult,
    AVISegmentResult as SegmentResult,
)

from .video_io import check_frame, cumulative, iter_frames, prefix_ranges, sliding_ranges, video_info

TARGETS = ("Whole", "R", "G", "B")


def validate_min_expected(min_expected: float) -> float:
    try:
        value = float(min_expected)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_expected must be a finite number greater than or equal to 5.") from exc
    if not np.isfinite(value) or value < 5:
        raise ValueError("min_expected must be a finite number greater than or equal to 5.")
    return value


def chi_square_from_histogram(value_counts: np.ndarray, min_expected: float = 5) -> ChiSquareResult:
    """Chi-square PoV จาก histogram 256 ค่า (เทียบเท่า image_detector.chi_square_pov ของ sample ชุดเดียวกัน)"""
    min_expected = validate_min_expected(min_expected)
    value_counts = np.asarray(value_counts)
    sample_count = int(value_counts.sum())
    if sample_count == 0:
        return ChiSquareResult(None, None, sample_count=0, valid_pairs=0,
                               status="empty", reason="No samples were provided.")

    even_counts = value_counts[0::2].astype(float)             # ค่า 2k
    odd_counts = value_counts[1::2].astype(float)              # ค่า 2k+1
    expected_per_pair = (even_counts + odd_counts) / 2.0       # ถ้าฝังเต็ม สองค่าในคู่เท่ากัน

    pair_is_usable = expected_per_pair >= min_expected
    valid_pairs = int(pair_is_usable.sum())
    if valid_pairs < 2:
        return ChiSquareResult(None, None, sample_count=sample_count, valid_pairs=valid_pairs,
                               status="insufficient_pairs",
                               reason=f"Only {valid_pairs} pair(s) have expected count >= {min_expected:g}; need at least 2.")

    chi_square_value = float((((even_counts - expected_per_pair) ** 2)[pair_is_usable]
                              / expected_per_pair[pair_is_usable]).sum())
    dof = valid_pairs - 1
    return ChiSquareResult(chi_square_value, float(chi2.sf(chi_square_value, dof)), dof,
                           sample_count, valid_pairs, "ok")


def chi_square_p_values(histograms: np.ndarray, min_expected: float = 5) -> np.ndarray:
    """p-value ของ histogram หลายชุดพร้อมกัน (..., 256) -> (...) ; คำนวณไม่ได้ (คู่ไม่พอ / ว่าง) = NaN

    สูตรเดียวกับ chi_square_from_histogram แต่ vectorized (ใช้กับ spatial prefix / segment ของทุกเฟรม)
    """
    min_expected = validate_min_expected(min_expected)
    histograms = np.asarray(histograms, dtype=float)
    shape = histograms.shape[:-1]
    flat = histograms.reshape(-1, 256)
    even, odd = flat[:, 0::2], flat[:, 1::2]
    expected = (even + odd) / 2.0
    usable = expected >= min_expected
    valid_pairs = usable.sum(axis=1)
    terms = np.where(usable, (even - expected) ** 2 / np.where(usable, expected, 1.0), 0.0)
    statistic = terms.sum(axis=1)
    p_values = np.full(flat.shape[0], np.nan)
    ok = valid_pairs >= 2
    p_values[ok] = chi2.sf(statistic[ok], valid_pairs[ok] - 1)
    return p_values.reshape(shape)


class ChiSquareVideo:
    """สะสม histogram ทีละเฟรม (add) แล้วสรุปทุกระดับ (finish)

    frame_spatial=True: คำนวณ spatial prefix / segment "ของแต่ละเฟรม" ไว้ด้วย (เหมือนรัน image detector ทีละเฟรม)
        ผลอยู่ที่ finish()["frame_spatial"] = {"prefix_p": (F, n_prefix, 4), "segment_p": (F, n_segment, 4)}
    """

    def __init__(self, height: int, width: int, min_expected: float = 5, prefix_step: int = 10,
                 segment_percent: int = 10, segment_step: int = 5, frame_spatial: bool = False):
        self.height, self.width = height, width
        self.frame_spatial = frame_spatial
        self.frame_prefix_p: List[np.ndarray] = []
        self.frame_segment_p: List[np.ndarray] = []
        self.min_expected = validate_min_expected(min_expected)
        self.prefix_step, self.segment_percent, self.segment_step = prefix_step, segment_percent, segment_step

        pixels = height * width
        self.spatial_prefix = prefix_ranges(pixels, prefix_step)
        self.spatial_segments = sliding_ranges(pixels, segment_percent, segment_step)

        # จุดตัดทั้งหมดของแกน spatial -> ชิ้น pixel ; chunk k = pixel [boundaries[k], boundaries[k+1])
        cuts = {0, pixels}
        cuts.update(end for _, end in self.spatial_prefix)
        for start, end in self.spatial_segments:
            cuts.update((start, end))
        self.boundaries = np.array(sorted(cuts), dtype=np.int64)
        self.boundary_index = {int(b): i for i, b in enumerate(self.boundaries)}
        chunk_count = len(self.boundaries) - 1
        chunk_of_pixel = np.searchsorted(self.boundaries, np.arange(pixels), side="right") - 1
        self._offsets = chunk_of_pixel * 256                         # ใช้ bincount ครั้งเดียวต่อช่อง
        self._chunk_count = chunk_count

        self.chunk_histograms = np.zeros((chunk_count, len(TARGETS), 256), dtype=np.int64)
        self.frame_histograms: List[np.ndarray] = []                 # แต่ละตัว (4, 256)

    def add(self, frame: np.ndarray) -> None:
        pixels = check_frame(frame, self.height, self.width).reshape(-1, 3)
        chunks = np.empty((self._chunk_count, len(TARGETS), 256), dtype=np.int64)
        for channel in range(3):
            chunks[:, channel + 1, :] = np.bincount(self._offsets + pixels[:, channel],
                                                    minlength=self._chunk_count * 256).reshape(-1, 256)
        chunks[:, 0, :] = chunks[:, 1:, :].sum(axis=1)               # Whole = R + G + B
        self.chunk_histograms += chunks
        self.frame_histograms.append(chunks.sum(axis=0))
        if self.frame_spatial:                                       # prefix / segment ภายในเฟรมนี้
            by_chunk = cumulative(chunks)
            ends = [self.boundary_index[end] for _, end in self.spatial_prefix]
            starts = [self.boundary_index[s] for s, _ in self.spatial_segments]
            stops = [self.boundary_index[e] for _, e in self.spatial_segments]
            self.frame_prefix_p.append(chi_square_p_values(by_chunk[ends], self.min_expected))
            self.frame_segment_p.append(chi_square_p_values(by_chunk[stops] - by_chunk[starts], self.min_expected))

    def finish(self) -> Dict[str, Any]:
        if not self.frame_histograms:
            raise ValueError("No frames were added.")
        frames = np.stack(self.frame_histograms)                      # (F, 4, 256)
        frame_count = frames.shape[0]
        by_frame = cumulative(frames)                                 # (F+1, 4, 256)
        by_chunk = cumulative(self.chunk_histograms)                  # (chunks+1, 4, 256)
        temporal_prefix = prefix_ranges(frame_count, self.prefix_step)
        temporal_segments = sliding_ranges(frame_count, self.segment_percent, self.segment_step)
        index = self.boundary_index
        test = lambda counts: chi_square_from_histogram(counts, self.min_expected)

        targets: Dict[str, Dict[str, Any]] = {}
        for t, name in enumerate(TARGETS):
            targets[name] = {
                "whole": test(by_frame[frame_count, t]),
                "per_frame": [test(frames[f, t]) for f in range(frame_count)],
                "temporal_prefix": [PrefixResult(p, end, test(by_frame[end, t])) for p, end in temporal_prefix],
                "temporal_segments": [SegmentResult(s, e, test(by_frame[e, t] - by_frame[s, t]))
                                      for s, e in temporal_segments],
                "spatial_prefix": [PrefixResult(p, end, test(by_chunk[index[end], t]))
                                   for p, end in self.spatial_prefix],
                "spatial_segments": [SegmentResult(s, e, test(by_chunk[index[e], t] - by_chunk[index[s], t]))
                                     for s, e in self.spatial_segments],
            }
        report = {"frame_count": frame_count, "pixels_per_frame": self.height * self.width, "targets": targets}
        if self.frame_spatial:
            report["frame_spatial"] = {"prefix_p": np.stack(self.frame_prefix_p),
                                       "segment_p": np.stack(self.frame_segment_p),
                                       "prefix_ranges": self.spatial_prefix,
                                       "segment_ranges": self.spatial_segments}
        return report


def analyze_chi_square(video_path: str, min_expected: float = 5, prefix_step: int = 10,
                       segment_percent: int = 10, segment_step: int = 5,
                       start_frame: int = 0, frame_count: Optional[int] = None) -> Dict[str, Any]:
    info = video_info(video_path)
    detector = ChiSquareVideo(info["height"], info["width"], min_expected, prefix_step, segment_percent, segment_step)
    for _, frame in iter_frames(video_path, start_frame, frame_count):
        detector.add(frame)
    return {"info": info, **detector.finish()}


def _p(result: ChiSquareResult) -> str:
    return "  N/A" if result.p_value is None else f"{result.p_value:.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Chi-square PoV analysis for a video (per frame, temporal, spatial).")
    parser.add_argument("filepath")
    parser.add_argument("--min-expected", type=float, default=5)
    parser.add_argument("--prefix-step", type=int, default=10)
    parser.add_argument("--segment-percent", type=int, default=10)
    parser.add_argument("--segment-step", type=int, default=5)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument("--frame-count", type=int, default=None)
    parser.add_argument("--per-frame", action="store_true", help="Print the p-value of every frame")
    args = parser.parse_args()
    try:
        report = analyze_chi_square(args.filepath, args.min_expected, args.prefix_step, args.segment_percent,
                                    args.segment_step, args.start_frame, args.frame_count)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))

    print(f"Video: {args.filepath}  frames={report['frame_count']}  pixels/frame={report['pixels_per_frame']}")
    print("(high p = pairs equalised = suspicious ; low p = looks clean)")
    for name, r in report["targets"].items():
        whole = r["whole"]
        print(f"\n[{name}] whole: chi2={whole.chi_square_total!s:.10} p={_p(whole)} dof={whole.dof}")
        print("  temporal prefix (frames): " + "  ".join(f"0-{x.percent}%={_p(x.analysis)}" for x in r["temporal_prefix"]))
        print("  spatial prefix (pixels):  " + "  ".join(f"0-{x.percent}%={_p(x.analysis)}" for x in r["spatial_prefix"]))
        print("  temporal segments:        " + "  ".join(f"[{x.start}:{x.end})={_p(x.analysis)}" for x in r["temporal_segments"]))
        print("  spatial segments:         " + "  ".join(f"[{x.start}:{x.end})={_p(x.analysis)}" for x in r["spatial_segments"]))
        if args.per_frame:
            print("  per frame: " + " ".join(_p(x) for x in r["per_frame"]))


if __name__ == "__main__":
    main()
