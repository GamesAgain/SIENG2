"""Sample Pair Analysis (SPA) - Dumitrescu, Wu, Wang, IEEE Trans. Signal Processing 51(7), 2003
ตรวจและ "ประมาณอัตรา" ของ LSB replacement จากสถิติของ "คู่ pixel" ที่อยู่ติดกัน

LSB replacement ทิ้งร่องรอยอะไร (ตามบทความ)
    คู่ pixel (u, v) ที่ต่างกันเป็นเลขคี่ (|u-v| = 2m+1) แบ่งเป็น 2 ชนิดตามว่าตัวไหนใหญ่กว่า
        X_{2m+1} : คู่ที่ "ค่าคู่ (even)" ใหญ่กว่า   เช่น (2k, 2k-2m-1)
        Y_{2m+1} : คู่ที่ "ค่าคี่ (odd)" ใหญ่กว่า    เช่น (2k+1, 2k-2m)
    ภาพธรรมชาติ: |X| ~ |Y| (สมมติฐาน (1) ของบทความ เพราะไม่มีเหตุให้ฝั่งใดใหญ่กว่า)
    LSB replacement แบบสุ่มสลับ LSB ทำให้คู่ย้ายระหว่างเซตเหล่านี้ด้วยความน่าจะเป็นที่คำนวณได้
    -> จำนวนในเซตเปลี่ยน -> |X| กับ |Y| ไม่เท่ากัน -> ย้อนกลับไปหา p ได้ด้วยสมการกำลังสอง

ตัวแปรสำคัญ (อ่านตารางนี้ก่อน)
    u, v                  pixel 2 ตัวที่อยู่ติดกัน (ซ้าย, ขวา) = "คู่ pixel" 1 คู่
    value_gap             |u - v|                       ผลต่างของค่า pixel
    high_bit_gap          |(u>>1) - (v>>1)|             ผลต่างเมื่อทิ้ง bit ล่างสุด (ไม่เปลี่ยนเมื่อฝัง LSB)
    d_counts[n]           |D_n| = จำนวนคู่ที่ value_gap = n                     (n = 0..255)
    c_counts[m]           |C_m| = จำนวนคู่ที่ high_bit_gap = m                  (m = 0..127)
    x_counts[m]           |X_{2m+1}| = คู่ที่ value_gap = 2m+1 และค่าคู่ใหญ่กว่า   (m = 0..127)
    y_counts[m]           |Y_{2m+1}| = คู่ที่ value_gap = 2m+1 และค่าคี่ใหญ่กว่า   (m = 0..127)
    j                     รวมผลของ m = 0..j เข้าด้วยกัน (pooling) ให้สถิติมากขึ้น/นิ่งขึ้น (บทความแนะนำ ~30)
    sum_y_minus_x         T = ผลรวมของ (|Y| - |X|) สำหรับ m = 0..j  (ถ้าไม่ฝัง ควรใกล้ 0)
    p                     อัตราการฝัง = bit ที่ฝัง / จำนวน sample ทั้งหมด (0..1) = สิ่งที่เราต้องการประมาณ

เซตที่ใช้นับ (นับจากคู่ pixel ทั้งหมด P)
    D_n  : คู่ที่ |u - v| = n                                       ความสัมพันธ์ที่ใช้ตรวจโค้ดได้:
    C_m  : คู่ที่ |(u>>1) - (v>>1)| = m                              D_{2m+1} = X_{2m+1} + Y_{2m+1}
    X, Y : ตามข้างบน                                                 C_m = X_{2m-1} + D_{2m} + Y_{2m+1}

สมการ (18) ของบทความ (กรณี i = 0, pooling m = 0..j):   a_term * p^2 + b_term * p + constant_term = 0
        a_term        = (2|C_0| - |C_{j+1}|) / 4                 ตัวคูณของ p^2
        b_term        = -( 2|D_0| - |D_{2j+2}| + 2*T ) / 2       ตัวคูณของ p
        constant_term = T                                        ค่าคงที่
    ค่าประมาณ p = "รากที่น้อยกว่า" ; เงื่อนไข: 2|C_0| > |C_{j+1}| และ 2|D_0| >= |D_{2j+2}|
    บทความชี้ว่าความคลาดเคลื่อนน้อยสุดที่ i = 0 และ j ~ 30 (ค่าเริ่มต้น DEFAULT_J) และแม่นกว่ามากเมื่อใช้คู่ที่ติดกันในภาพ
ข้อจำกัดที่เห็นจากการทดลอง
    - ภาพ clean ได้ค่าไม่เป็น 0 เป๊ะ (สมมติฐาน (1) ไม่ตรง 100%) ; ฝังเต็มทั้งภาพสมการเสื่อม (no_real_root)
"""
import argparse
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

DEFAULT_J = 30             # รวมผลของ m = 0..j (บทความแนะนำ ~30)
DEFAULT_MIN_PAIRS = 100    # จำนวนคู่ขั้นต่ำที่ยอมให้ประมาณ


@dataclass
class SPAStatistics:
    """จำนวนคู่ในแต่ละเซต C, D, X, Y (นับดิบ ใช้รวมหลาย channel ได้โดยบวกกัน)"""

    c_counts: List[int]       # |C_m|, m = 0..127      คู่ที่ high_bit_gap = m
    d_counts: List[int]       # |D_n|, n = 0..255      คู่ที่ value_gap = n
    x_counts: List[int]       # |X_{2m+1}|, m = 0..127 (เก็บที่ index m) ค่าคู่ใหญ่กว่า
    y_counts: List[int]       # |Y_{2m+1}|, m = 0..127 (เก็บที่ index m) ค่าคี่ใหญ่กว่า
    pair_count: int           # จำนวนคู่ pixel ทั้งหมดที่นับได้
    sample_count: int         # จำนวน sample (pixel x channel) ทั้งหมดของภาพ


@dataclass
class SPAEstimate:
    """อัตราการฝังที่ประมาณได้ พร้อมสมการและสถานะ

    status: estimated / insufficient_pairs / assumption_failed_c / assumption_failed_d /
            degenerate_equation / no_real_root / non_finite_root / out_of_range
    """

    embedding_rate: Optional[float]                  # p ที่ประมาณได้ (None ถ้าประมาณไม่ได้)
    estimated_payload_bits: Optional[float]          # p x จำนวน sample
    expected_changed_samples: Optional[float]        # ครึ่งหนึ่งของ bit ที่ฝัง (LSB replacement เปลี่ยนจริงครึ่งหนึ่ง)
    pair_count: int
    sample_count: int
    coefficients: Optional[Tuple[float, float, float]] = None   # (a_term, b_term, constant_term) ของสมการ
    roots: Tuple[float, ...] = ()                    # รากทั้งหมดของสมการ
    status: str = "unavailable"
    reason: Optional[str] = None
    diagnostics: Optional["SPADiagnostics"] = None


@dataclass
class SPADiagnostics:
    """ค่าตั้งต้นและค่าระหว่างทางของสมการ (18) เพื่อให้ตรวจย้อนได้"""

    j: int                         # ค่า j ที่ใช้
    c0: int                        # |C_0|
    c_j_plus_1: int                # |C_{j+1}|
    d0: int                        # |D_0|
    d_2j_plus_2: int               # |D_{2j+2}|
    sum_x: int                     # ผลรวม |X_{2m+1}| ของ m = 0..j
    sum_y: int                     # ผลรวม |Y_{2m+1}| ของ m = 0..j
    trace_difference: int          # T = sum_y - sum_x
    discriminant: Optional[float] = None    # b^2 - 4ac ของสมการ
    selected_root: Optional[float] = None   # รากที่เลือก (= ค่าประมาณ p)


# --------------------------------------------------------------------------------------------
# นับสถิติของคู่ pixel
# --------------------------------------------------------------------------------------------

def make_pairs(channel: np.ndarray) -> np.ndarray:
    """แบ่งเป็นคู่ pixel แนวนอน (p0,p1), (p2,p3), ... ไม่ซ้อนกัน และไม่ข้ามแถว"""
    height, width = channel.shape
    usable_width = (width // 2) * 2                          # ตัด pixel สุดท้ายของแถวถ้ากว้างเป็นเลขคี่
    if height == 0 or usable_width == 0:
        return np.empty((0, 2), dtype=channel.dtype)
    return channel[:, :usable_width].reshape(-1, 2)


def collect_spa_statistics(channel: np.ndarray) -> SPAStatistics:
    """นับ C, D, X, Y จาก 1 channel (ค่า 0..255 เป็นจำนวนเต็ม)"""

    # Step 0: ตรวจ input
    channel = np.asarray(channel)
    if channel.ndim != 2:
        raise ValueError("channel must be a 2D image array.")
    if not np.issubdtype(channel.dtype, np.integer):
        raise ValueError("channel must contain integers in the range 0..255.")
    if np.any(channel < 0) or np.any(channel > 255):
        raise ValueError("channel must contain integers in the range 0..255.")

    pairs = make_pairs(channel)
    if len(pairs) == 0:
        return SPAStatistics([0] * 128, [0] * 256, [0] * 128, [0] * 128, 0, int(channel.size))

    # Step 1: แยกเป็น pixel ซ้าย (u) / ขวา (v) ใช้ int32 กัน uint8 ล้นตอนลบ
    left = pairs[:, 0].astype(np.int32)
    right = pairs[:, 1].astype(np.int32)

    # Step 2: D_n = จำนวนคู่ที่ value_gap = n ; C_m = จำนวนคู่ที่ high_bit_gap = m
    value_gap = np.abs(left - right)                          # |u - v|
    high_bit_gap = np.abs((left >> 1) - (right >> 1))         # |(u>>1) - (v>>1)|
    d_counts = np.bincount(value_gap, minlength=256)[:256]
    c_counts = np.bincount(high_bit_gap, minlength=128)[:128]

    # Step 3: คู่ที่ value_gap เป็นเลขคี่ (= 2m+1) แบ่งเป็น X หรือ Y ตามว่าค่าคู่หรือค่าคี่ใหญ่กว่า
    has_odd_gap = value_gap % 2 == 1
    gap_index = (value_gap[has_odd_gap] - 1) // 2             # m ของแต่ละคู่ (value_gap = 2m+1)
    left_odd_gap, right_odd_gap = left[has_odd_gap], right[has_odd_gap]
    even_member = np.where(left_odd_gap % 2 == 0, left_odd_gap, right_odd_gap)   # สมาชิกของคู่ที่เป็นเลขคู่
    odd_member = np.where(left_odd_gap % 2 == 0, right_odd_gap, left_odd_gap)    # สมาชิกของคู่ที่เป็นเลขคี่
    even_is_larger = even_member > odd_member                 # True -> X ; False -> Y
    x_counts = np.bincount(gap_index[even_is_larger], minlength=128)[:128]
    y_counts = np.bincount(gap_index[~even_is_larger], minlength=128)[:128]

    return SPAStatistics(
        c_counts=c_counts.astype(int).tolist(),
        d_counts=d_counts.astype(int).tolist(),
        x_counts=x_counts.astype(int).tolist(),
        y_counts=y_counts.astype(int).tolist(),
        pair_count=int(len(pairs)),
        sample_count=int(channel.size),
    )


def pool_spa_statistics(statistics: Sequence[SPAStatistics]) -> SPAStatistics:
    """รวมจำนวนดิบของหลาย channel (บวกกัน) ก่อนแก้สมการ"""
    c_total = np.zeros(128, dtype=np.int64)
    d_total = np.zeros(256, dtype=np.int64)
    x_total = np.zeros(128, dtype=np.int64)
    y_total = np.zeros(128, dtype=np.int64)
    pair_total = sample_total = 0
    for item in statistics:
        c_total += np.asarray(item.c_counts, dtype=np.int64)
        d_total += np.asarray(item.d_counts, dtype=np.int64)
        x_total += np.asarray(item.x_counts, dtype=np.int64)
        y_total += np.asarray(item.y_counts, dtype=np.int64)
        pair_total += item.pair_count
        sample_total += item.sample_count
    return SPAStatistics(c_total.tolist(), d_total.tolist(), x_total.tolist(), y_total.tolist(),
                         pair_total, sample_total)


# --------------------------------------------------------------------------------------------
# แก้สมการ (18)
# --------------------------------------------------------------------------------------------

def estimate_spa(
    statistics: SPAStatistics,
    j: int = DEFAULT_J,
    min_pairs: int = DEFAULT_MIN_PAIRS,
) -> SPAEstimate:
    """ประมาณ p จากสมการ (18) ของบทความ (i = 0, pooling m = 0..j)

    j         รวมผลของ m = 0..j (ยิ่งมากยิ่งใช้ข้อมูลเยอะ แต่คู่ที่ห่างไกลอาจไม่ตรงสมมติฐาน)
    min_pairs จำนวนคู่ขั้นต่ำ ถ้าน้อยกว่านี้ไม่ประมาณ
    """

    # Step 0: ตรวจพารามิเตอร์ (j <= 126 เพื่อให้ index j+1 และ 2j+2 อยู่ในช่วงของ C และ D)
    if isinstance(j, bool) or not isinstance(j, int) or not 0 <= j <= 126:
        raise ValueError("j must be an integer in the range 0..126.")
    if isinstance(min_pairs, bool) or not isinstance(min_pairs, int) or min_pairs < 1:
        raise ValueError("min_pairs must be a positive integer.")

    c_counts, d_counts = statistics.c_counts, statistics.d_counts
    x_counts, y_counts = statistics.x_counts, statistics.y_counts

    # Step 1: ประกอบสัมประสิทธิ์ของสมการ  a_term * p^2 + b_term * p + constant_term = 0
    sum_y_minus_x = sum(y_counts[m] - x_counts[m] for m in range(j + 1))      # T
    a_term = (2 * c_counts[0] - c_counts[j + 1]) / 4.0                         # ตัวคูณของ p^2
    b_term = -(2 * d_counts[0] - d_counts[2 * j + 2] + 2 * sum_y_minus_x) / 2.0   # ตัวคูณของ p
    constant_term = float(sum_y_minus_x)                                       # ค่าคงที่
    coefficients = (a_term, b_term, constant_term)
    diagnostics = SPADiagnostics(
        j=j, c0=c_counts[0], c_j_plus_1=c_counts[j + 1], d0=d_counts[0], d_2j_plus_2=d_counts[2 * j + 2],
        sum_x=sum(x_counts[:j + 1]), sum_y=sum(y_counts[:j + 1]), trace_difference=sum_y_minus_x,
    )

    def unavailable(status: str, reason: str) -> SPAEstimate:
        return SPAEstimate(None, None, None, statistics.pair_count, statistics.sample_count,
                           coefficients=coefficients, status=status, reason=reason, diagnostics=diagnostics)

    # Step 2: เงื่อนไขของการหาสมการ (ถ้าไม่ผ่านแล้วค่าที่ได้เชื่อถือไม่ได้)
    if statistics.pair_count < min_pairs:
        return unavailable("insufficient_pairs", f"Fewer than {min_pairs} complete sample pairs are available.")
    if 2 * c_counts[0] <= c_counts[j + 1]:
        return unavailable("assumption_failed_c", "The required relation 2*C0 > C(j+1) is not satisfied.")
    if 2 * d_counts[0] < d_counts[2 * j + 2]:
        return unavailable("assumption_failed_d", "The required relation 2*D0 >= D(2j+2) is not satisfied.")

    # Step 3: หารากของสมการ
    tiny = 1e-12                                               # ถือว่าเป็นศูนย์ถ้าเล็กกว่านี้
    if abs(a_term) < tiny:                                     # เหลือสมการเชิงเส้น
        if abs(b_term) < tiny:
            return unavailable("degenerate_equation", "Both quadratic and linear terms are effectively zero.")
        roots = (-constant_term / b_term,)
    else:
        discriminant = b_term ** 2 - 4.0 * a_term * constant_term      # b^2 - 4ac
        diagnostics.discriminant = discriminant
        if discriminant < -tiny:
            return unavailable("no_real_root", "The SPA equation has a negative discriminant and no real root.")
        sqrt_discriminant = math.sqrt(max(0.0, discriminant))
        roots = ((-b_term + sqrt_discriminant) / (2.0 * a_term),
                 (-b_term - sqrt_discriminant) / (2.0 * a_term))

    # Step 4: ค่าประมาณ p = รากที่น้อยกว่า (ตามบทความ)
    embedding_rate = min(roots)
    diagnostics.selected_root = embedding_rate
    shared = dict(pair_count=statistics.pair_count, sample_count=statistics.sample_count,
                  coefficients=coefficients, roots=roots, diagnostics=diagnostics)
    if not math.isfinite(embedding_rate):
        return SPAEstimate(None, None, None, status="non_finite_root",
                           reason="The selected mathematical root is not finite.", **shared)
    if not 0.0 <= embedding_rate <= 1.0:                  # นอกช่วงจริง: เก็บค่าไว้ แต่ไม่แปลงเป็น payload
        return SPAEstimate(embedding_rate, None, None, status="out_of_range",
                           reason="The selected root lies outside the physical 0..100% range.", **shared)
    return SPAEstimate(
        embedding_rate,
        estimated_payload_bits=embedding_rate * statistics.sample_count,
        expected_changed_samples=embedding_rate * statistics.sample_count / 2.0,    # สลับ LSB จริงครึ่งหนึ่ง
        status="estimated", reason=None, **shared,
    )


# --------------------------------------------------------------------------------------------
# โหลดภาพ + รันครบชุด
# --------------------------------------------------------------------------------------------

def load_image_targets(image_path: str) -> Dict[str, np.ndarray]:
    """โหลดภาพ 8 bit L / RGB / RGBA -> {"R","G","B"} หรือ {"L"} (ทิ้ง alpha)"""
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
    """วิเคราะห์ทีละ channel แล้วรวมจำนวนคู่ของ RGB เป็น "Whole" """
    targets = load_image_targets(image_path)
    report: Dict[str, Dict[str, Any]] = {}
    for name, channel in targets.items():
        statistics = collect_spa_statistics(channel)
        report[name] = {"statistics": statistics, "estimate": estimate_spa(statistics, j=j, min_pairs=min_pairs)}

    if len(targets) > 1:                                   # ภาพสี: รวมจำนวนดิบของ 3 channel เป็น Whole
        whole = pool_spa_statistics([report[name]["statistics"] for name in targets])
        report = {"Whole": {"statistics": whole, "estimate": estimate_spa(whole, j=j, min_pairs=min_pairs)}, **report}
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample Pair Analysis for LSB replacement.")
    parser.add_argument("filepath", help="Path to the image to analyze")
    parser.add_argument("--j", type=int, default=DEFAULT_J, help="Upper pooling index in the SPA equation (default: 30)")
    parser.add_argument("--min-pairs", type=int, default=DEFAULT_MIN_PAIRS,
                        help="Minimum number of sample pairs (default: 100)")
    args = parser.parse_args()

    try:
        report = analyze_spa(args.filepath, j=args.j, min_pairs=args.min_pairs)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    def print_result(name: str, statistics: SPAStatistics, estimate: SPAEstimate) -> None:
        j = args.j
        sum_x, sum_y = sum(statistics.x_counts[:j + 1]), sum(statistics.y_counts[:j + 1])
        print(f"\n[{name}]")
        print(f"  pairs={statistics.pair_count}, samples={statistics.sample_count}")
        print(f"  raw: C0={statistics.c_counts[0]}, C{j + 1}={statistics.c_counts[j + 1]}, "
              f"D0={statistics.d_counts[0]}, D{2 * j + 2}={statistics.d_counts[2 * j + 2]}, "
              f"sumX={sum_x}, sumY={sum_y}")
        if estimate.coefficients is None:
            print("  equation: N/A")
        else:
            a_term, b_term, constant_term = estimate.coefficients
            roots = ", ".join(f"{root:.6g}" for root in estimate.roots)
            print(f"  equation: A={a_term:.6g}, B={b_term:.6g}, T={constant_term:.6g}, roots=[{roots}]")
        print(f"  status={estimate.status}")
        if estimate.reason:
            print(f"  reason={estimate.reason}")
        if estimate.embedding_rate is None:
            print("  Estimated embedded bits: N/A")
        elif estimate.estimated_payload_bits is None:
            print(f"  Estimated embed rate: {estimate.embedding_rate * 100:.2f}% (outside physical range 0..100%)")
        else:
            print(f"  Estimated embed rate: {estimate.embedding_rate * 100:.2f}%, "
                  f"bits={estimate.estimated_payload_bits:.0f}, "
                  f"expected_changed={estimate.expected_changed_samples:.0f}")

    print(f"Image: {args.filepath}")
    print(f"j={args.j}, min_pairs={args.min_pairs}")
    for name, analysis in report.items():
        print_result(name, analysis["statistics"], analysis["estimate"])


if __name__ == "__main__":
    main()
