"""Chi-square Pairs-of-Values (PoV) attack - ตรวจ LSB replacement จาก histogram ของ pixel

LSB replacement ทิ้งร่องรอยอะไร
    ค่า pixel 8 bit จับคู่ได้เป็น (2k, 2k+1) เช่น (150, 151) ต่างกันแค่ LSB
    LSB replacement ทำได้แค่ "สลับภายในคู่" (150 <-> 151) ไม่มีวันข้ามไปคู่อื่น (150 -> 149 ไม่ได้)
    ถ้า bit ที่ฝังเป็นสุ่ม (เข้ารหัสแล้ว) โอกาสไปทาง 150 หรือ 151 เท่ากัน 50/50
    => หลังฝัง จำนวน pixel ของ 2k กับ 2k+1 จะ "เท่ากันเกือบเป๊ะ" ในทุกคู่ (histogram เป็นขั้นบันได)
    ภาพธรรมชาติทั่วไปไม่เป็นแบบนี้ สองค่าในคู่เดียวกันมักไม่เท่ากัน

Chi-square ตรวจอะไร
    ตั้งสมมติฐานว่า "สองค่าในคู่เท่ากัน" (= ฝังเต็มแล้ว) ค่าคาดหวัง e = (n_2k + n_2k+1) / 2
    statistic = sum( (n_2k - e)^2 / e )   นับเฉพาะค่าคู่ของแต่ละคู่ (ค่าคี่ถูกกำหนดจากค่าคู่ จึงไม่นับซ้ำ)
    dof = (จำนวนคู่ที่ใช้) - 1,   p = P(chi2 >= statistic)   (หางขวา)

ตัวแปรสำคัญ (อ่านตารางนี้ก่อน)
    samples               ค่า pixel 8 bit (0..255) ทุกตัวที่ป้อนเข้ามา (ทุก channel ปนกัน)
    even_counts[k]        จำนวน pixel ที่มีค่า 2k      (ค่าคู่ของคู่ที่ k)    k = 0..127
    odd_counts[k]         จำนวน pixel ที่มีค่า 2k+1    (ค่าคี่ของคู่ที่ k)
    expected_per_pair[k]  ค่าคาดหวังของคู่ที่ k ถ้าฝังเต็ม = (even + odd) / 2
    min_expected          ใช้เฉพาะคู่ที่ expected_per_pair >= ค่านี้ (กฎมาตรฐานของ chi-square: >= 5)
    valid_pairs           จำนวนคู่ที่ใช้ได้ ;  dof = valid_pairs - 1
    chi_square_value      ผลรวม (even - expected)^2 / expected ของคู่ที่ใช้ได้ (ในโค้ดเก็บที่ chi_square_total)
    p_value               P(chi2 >= chi_square_value)  สูง = สองค่าในคู่เท่ากัน = น่าสงสัย
    pixel                 หน่วยนับของ prefix / segment = 1 pixel (ทุก channel ของ pixel นั้นไปด้วยกัน)

วิธีอ่านผล (สำคัญ: กลับด้านกับ test ทั่วไป)
    p สูง (ใกล้ 1)  = สองค่าในคู่เท่ากันมาก = น่าสงสัยว่ามีการฝัง
    p ต่ำ (ใกล้ 0)  = สองค่าในคู่ต่างกันตามธรรมชาติ = ดูเหมือนภาพ clean
    ถ้าฝังเต็ม statistic จะอยู่ราว 0.5 * dof (ไม่ใช่ dof) ดังนั้น p ใกล้ 1.0
    ข้อจำกัด: ได้ผลเมื่อฝัง "หนาแน่น" ในช่วงที่ทดสอบเท่านั้น
      - ฝังต่อเนื่องจากต้นภาพ (sequential)  -> prefix / segment เห็นชัด
      - ฝังสุ่มตำแหน่งทั้งภาพ (shuffled)    -> เห็นเฉพาะเมื่อฝังเกือบเต็ม (ตาบอดที่ rate ต่ำ)
      - ภาพที่มีสีน้อย / ภาพเล็ก มีคู่ที่ใช้ได้น้อย -> คำนวณไม่ได้ (คืน None)

ฟังก์ชันหลัก
    chi_square_pov      ทดสอบ 1 ชุดค่า pixel
    progressive_prefix  ทดสอบ 0-10%, 0-20%, ... 0-100% ของภาพ (สะสมจากต้นภาพ) -> หาจุดสิ้นสุดการฝัง
    sliding_segment     ทดสอบหน้าต่างความยาวคงที่เลื่อนไปตามภาพ (ไม่สะสม) -> หาช่วงที่ฝังอยู่กลางภาพ
"""
import argparse
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image
from scipy.stats import chi2


@dataclass
class ChiSquareResult:
    chi_square_total: Optional[float]     # chi_square_value ที่คำนวณได้ (None ถ้าคำนวณไม่ได้)
    p_value: Optional[float]              # สูง = น่าสงสัย
    dof: Optional[int] = None             # degrees of freedom = valid_pairs - 1
    sample_count: Optional[int] = None    # จำนวน sample ที่ใส่เข้ามา
    valid_pairs: Optional[int] = None     # จำนวนคู่ที่ expected >= min_expected
    status: str = "unavailable"           # ok / empty / insufficient_pairs (ดูข้างล่าง)
    reason: Optional[str] = None          # คำอธิบายสั้น ๆ เมื่อคำนวณไม่ได้ (None เมื่อ status = ok)

    # status:
    #   ok                  คำนวณได้ (มี p_value)
    #   empty               ไม่มี sample เลย
    #   insufficient_pairs  คู่ที่ใช้ได้ (expected >= min_expected) น้อยกว่า 2 -> dof ไม่พอ (ภาพสีน้อย / prefix เล็ก)


@dataclass
class PrefixResult:
    percent: int                          # prefix นี้ครอบคลุม 0-percent% ของภาพ (นับจาก pixel แรก)
    sample_count: int                     # จำนวน sample ใน prefix (pixel x channel)
    chi_square: ChiSquareResult


@dataclass
class SegmentResult:
    start: int                            # ตำแหน่ง pixel (นับ pixel ไม่ใช่ sample), รวมตัวนี้
    end: int                              # ไม่รวมตัวนี้
    sample_count: int                     # จำนวน sample ในหน้าต่าง (pixel x channel)
    chi_square: ChiSquareResult


# --------------------------------------------------------------------------------------------
# แกนหลัก: ทดสอบ 1 ชุดค่า
# --------------------------------------------------------------------------------------------

def chi_square_pov(samples: np.ndarray, min_expected: float = 5) -> ChiSquareResult:
    """Chi-square PoV บนค่า pixel 8 bit (จำนวนเต็ม 0..255) ชุดเดียว"""

    # Step 0: ตรวจ input
    samples = np.asarray(samples).ravel()
    try:
        min_expected = float(min_expected)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_expected must be a finite number greater than or equal to 5.") from exc
    if not np.isfinite(min_expected) or min_expected < 5:
        # < 5 ทำให้ chi-square ไม่ใช่ค่าประมาณที่เชื่อถือได้ (กฎมาตรฐาน expected >= 5)
        raise ValueError("min_expected must be a finite number greater than or equal to 5.")

    if samples.size == 0:
        return ChiSquareResult(None, None, sample_count=0, valid_pairs=0,
                               status="empty", reason="No samples were provided.")

    if not np.issubdtype(samples.dtype, np.integer):
        raise ValueError("samples must contain integer values in the range 0..255.")
    if samples.min() < 0 or samples.max() > 255:
        raise ValueError("samples must contain integer values in the range 0..255.")

    # Step 1: นับจำนวน pixel ของแต่ละค่า 0..255 แล้วแยกเป็นค่าคู่ (0,2,4,..) กับค่าคี่ (1,3,5,..)
    #         even_counts[k] = จำนวน pixel ที่มีค่า 2k,  odd_counts[k] = จำนวน pixel ที่มีค่า 2k+1  (128 คู่)
    value_counts = np.bincount(samples, minlength=256)       # value_counts[v] = จำนวน pixel ที่มีค่า v
    even_counts = value_counts[0::2].astype(float)
    odd_counts = value_counts[1::2].astype(float)

    # Step 2: ค่าคาดหวังต่อคู่ ถ้าฝังเต็ม = ครึ่งหนึ่งของผลรวมในคู่
    expected_per_pair = (even_counts + odd_counts) / 2.0

    # Step 3: ใช้เฉพาะคู่ที่ expected พอ (>= min_expected) แล้วรวม (observed - expected)^2 / expected
    #         observed = จำนวนค่าคู่ (even_counts) ; ค่าคี่ไม่ต้องนับ เพราะ odd - expected = -(even - expected)
    pair_is_usable = expected_per_pair >= min_expected
    valid_pairs = int(pair_is_usable.sum())
    if valid_pairs < 2:                      # dof = valid_pairs - 1 ต้อง >= 1
        return ChiSquareResult(None, None, sample_count=int(samples.size), valid_pairs=valid_pairs,
                               status="insufficient_pairs",
                               reason=f"Only {valid_pairs} pair(s) have expected count >= {min_expected:g}; need at least 2.")

    chi_square_value = float((((even_counts - expected_per_pair) ** 2)[pair_is_usable]
                              / expected_per_pair[pair_is_usable]).sum())

    # Step 4: p-value แบบหางขวา (survival function)  p สูง = สองค่าในคู่เท่ากัน = น่าสงสัย
    dof = valid_pairs - 1
    return ChiSquareResult(
        chi_square_total=chi_square_value,
        p_value=float(chi2.sf(chi_square_value, dof)),
        dof=dof,
        sample_count=int(samples.size),
        valid_pairs=valid_pairs,
        status="ok",
    )


def _as_pixel_rows(samples: np.ndarray) -> np.ndarray:
    """(H,W,C) -> (H*W, C) ; (H,W) -> (H*W, 1)  เพื่อนับเป็นหน่วย "pixel" (ทุก channel ของ pixel ไปด้วยกัน)"""
    samples = np.asarray(samples)
    if samples.ndim == 3:
        return samples.reshape(-1, samples.shape[2])
    if samples.ndim == 2:
        return samples.reshape(-1, 1)
    raise ValueError("samples must be a 2D or 3D image array.")


# --------------------------------------------------------------------------------------------
# Prefix (สะสมจากต้นภาพ): หาว่าการฝังต่อเนื่องจบที่ไหน
# --------------------------------------------------------------------------------------------

def progressive_prefix(samples: np.ndarray, min_expected: float = 5, step: int = 10) -> List[PrefixResult]:
    """ทดสอบ 0-step%, 0-2*step%, ... 0-100% ของภาพ (สะสม) ตามลำดับ raster

    ถ้าฝังต่อเนื่องจากต้นภาพ p จะสูงตราบที่ prefix ยังอยู่ในส่วนที่ฝัง แล้วตกลงเมื่อ prefix
    เลยจุดสิ้นสุด (เพราะมีส่วนที่ไม่ได้ฝังปนเข้ามา) ข้อควรรู้: p ตกช้ากว่าจุดจบจริงเล็กน้อย (ดู Exp 1)
    """
    if isinstance(step, bool) or not isinstance(step, (int, np.integer)) or not 1 <= step <= 100:
        raise ValueError("step must be an integer in the range 1..100.")

    pixels = _as_pixel_rows(samples)                       # แถวละ 1 pixel (มีค่าของทุก channel)
    total_pixels = pixels.shape[0]

    # เติม 100 เสมอ กัน step ที่หาร 100 ไม่ลงตัว (เช่น 30 -> 30,60,90,100)
    percent_list = list(range(step, 100, step)) + [100]
    results: List[PrefixResult] = []
    for percent in percent_list:
        prefix_pixels = math.ceil(total_pixels * percent / 100)     # จำนวน pixel ของ prefix
        prefix_samples = pixels[:prefix_pixels].ravel()             # sample ทุก channel ของ pixel เหล่านั้น
        results.append(PrefixResult(percent, int(prefix_samples.size), chi_square_pov(prefix_samples, min_expected)))
    return results


# --------------------------------------------------------------------------------------------
# Segment (หน้าต่างเลื่อน ไม่สะสม): หาช่วงที่ฝังอยู่กลางภาพ
# --------------------------------------------------------------------------------------------

def sliding_segment(
    samples: np.ndarray,
    min_expected: float = 5,
    segment_percent: int = 10,
    step_percent: int = 5,
) -> List[SegmentResult]:
    """ทดสอบหน้าต่างยาว segment_percent% ที่เลื่อนทีละ step_percent% ตามลำดับ raster (หน้าต่างแยกกัน)

    ต่างจาก prefix: ไม่รวมส่วนต้นภาพ จึงเห็นการฝังที่อยู่ "กลางภาพ" ได้ (หน้าต่างในช่วงที่ฝังจะได้ p สูง)
    หน้าต่างสุดท้ายถูกบังคับให้ชิดท้ายภาพ จึงอาจซ้อนกับหน้าต่างก่อนหน้ามากกว่าหน้าต่างอื่น
    start รวม, end ไม่รวม และนับเป็นตำแหน่ง pixel
    """
    if not 0 < segment_percent <= 100:
        raise ValueError("segment_percent must be in the range 1..100.")
    if not 0 < step_percent <= segment_percent:
        raise ValueError("step_percent must be in the range 1..segment_percent.")

    pixels = _as_pixel_rows(samples)
    total_pixels = pixels.shape[0]
    if total_pixels == 0:
        return []

    window_pixels = math.ceil(total_pixels * segment_percent / 100)            # ความยาวหน้าต่าง (pixel)
    stride_pixels = max(1, math.ceil(total_pixels * step_percent / 100))       # ระยะเลื่อน (pixel)

    window_starts = list(range(0, total_pixels - window_pixels + 1, stride_pixels))
    last_window_start = total_pixels - window_pixels
    if window_starts[-1] != last_window_start:                                  # ให้หน้าต่างสุดท้ายชนท้ายภาพพอดี
        window_starts.append(last_window_start)

    results: List[SegmentResult] = []
    for start in window_starts:
        window_samples = pixels[start:start + window_pixels].ravel()           # sample ทุก channel ในหน้าต่าง
        results.append(SegmentResult(start, start + window_pixels, int(window_samples.size),
                                     chi_square_pov(window_samples, min_expected)))
    return results


# --------------------------------------------------------------------------------------------
# โหลดภาพ + รันครบชุด
# --------------------------------------------------------------------------------------------

def load_image_targets(image_path: str) -> Dict[str, np.ndarray]:
    """โหลดภาพ -> {"Whole": RGB ทั้งหมดรวม, "R","G","B": แยกช่อง}  หรือ {"L": ...} สำหรับภาพเกรย์

    mode อื่น (เช่น RGBA, P) จะถูกแปลงเป็น RGB (alpha ถูกทิ้ง)
    """
    with Image.open(image_path) as image:
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        array = np.array(image)

    if array.ndim == 2:
        return {"L": array}
    targets: Dict[str, np.ndarray] = {"Whole": array}
    for index, name in enumerate("RGB"[: array.shape[2]]):
        targets[name] = array[:, :, index]
    return targets


def analyze_chi_square(
    image_path: str,
    min_expected: float = 5,
    prefix_step: int = 10,
    segment_percent: int = 10,
    segment_step: int = 5,
) -> Dict[str, Any]:
    """รันครบชุดต่อ target (Whole / R / G / B / L): whole + prefix + segments"""
    report: Dict[str, Any] = {}
    for name, data in load_image_targets(image_path).items():
        report[name] = {
            "whole": chi_square_pov(np.asarray(data).ravel(), min_expected),
            "prefix": progressive_prefix(data, min_expected, prefix_step),
            "segments": sliding_segment(data, min_expected, segment_percent, segment_step),
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Chi-square PoV analysis for an image.")
    parser.add_argument("filepath", help="Path to the image to analyze")
    parser.add_argument("--min-expected", type=float, default=5, help="Minimum expected count per pair (default: 5)")
    parser.add_argument("--prefix-step", type=int, default=10, help="Cumulative prefix step in percent (default: 10)")
    parser.add_argument("--segment-percent", type=int, default=10, help="Segment length in percent (default: 10)")
    parser.add_argument("--segment-step", type=int, default=5, help="Distance between segment starts in percent (default: 5)")
    args = parser.parse_args()

    try:
        report = analyze_chi_square(args.filepath, args.min_expected, args.prefix_step,
                                    args.segment_percent, args.segment_step)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    def show(label: str, result: ChiSquareResult) -> None:
        chi_text = f"{result.chi_square_total:.6g}" if result.chi_square_total is not None else "N/A"
        p_text = f"{result.p_value:.5f}" if result.p_value is not None else "N/A"
        note = "" if result.status == "ok" else f"  [{result.status}]"
        print(f"  {label:<22} chi2={chi_text:<12} p={p_text:<10} dof={result.dof!s:<4} "
              f"pairs={result.valid_pairs!s:<4} samples={result.sample_count}{note}")

    print(f"Image: {args.filepath}")
    print(f"min_expected={args.min_expected:g}, prefix_step={args.prefix_step}%, "
          f"segment={args.segment_percent}%, segment_step={args.segment_step}%")
    print("(high p = pairs look equalised = suspicious; low p = looks like a natural/clean image)")
    for name, analysis in report.items():
        print(f"\n[{name}]")
        show("whole", analysis["whole"])
        print("  Prefix (cumulative):")
        for item in analysis["prefix"]:
            show(f"0-{item.percent}%", item.chi_square)
        print("  Segments (pixel positions, end exclusive):")
        for item in analysis["segments"]:
            show(f"[{item.start}:{item.end})", item.chi_square)


if __name__ == "__main__":
    main()
