"""RS Analysis (Fridrich, Goljan, Du) - ตรวจและ "ประมาณอัตรา" ของ LSB replacement

LSB replacement ทิ้งร่องรอยอะไร
    การฝังเขียนทับ LSB ด้วย bit สุ่ม = สลับ 2k <-> 2k+1 แบบสุ่ม ทำให้ภาพ "ขรุขระ" ขึ้นเล็กน้อย
    ภาพธรรมชาติค่า pixel ข้างเคียงมักใกล้กัน (เรียบ) ส่วนภาพที่ถูกฝังจะมี noise ระดับ LSB เพิ่ม
    และการสลับ LSB ด้วยตัวเอง (flipping) กับภาพที่ถูกฝังแล้ว มีผลต่างจากภาพ clean

RS ตรวจอะไร
    1) แบ่งภาพเป็นกลุ่ม 4 pixel ติดกัน (แนวนอน ไม่ซ้อนกัน)
    2) วัดความขรุขระของกลุ่มด้วย f(G) = ผลรวมของ |ผลต่างระหว่าง pixel ที่อยู่ติดกัน|
    3) "flip" pixel บางตัวในกลุ่มตาม mask M แล้ววัด f ใหม่
         f เพิ่มขึ้น -> กลุ่ม Regular (R)     f ลดลง -> กลุ่ม Singular (S)     f เท่าเดิม -> Unusable (U)
    4) ทำทั้ง mask M และ -M ได้ 4 ค่า: RM, SM, R(-M), S(-M)  (เป็นสัดส่วนของกลุ่มทั้งหมด)

    flip มี 2 แบบ (ทำกับ pixel ตำแหน่งที่ mask ระบุ)
         F1  : 0<->1, 2<->3, 4<->5, ...   (สลับ LSB = สิ่งเดียวกับที่ LSB replacement ทำ)
         F-1 : -1<->0, 1<->2, 3<->4, ...  (สลับ "เลื่อน" คู่ไปอีกขั้น)
    mask M ใช้ F1 ที่ตำแหน่ง mask=1, ใช้ F-1 ที่ตำแหน่ง mask=-1, ไม่แตะที่ mask=0
    mask -M คือกลับเครื่องหมาย (ตำแหน่ง 1 กลายเป็น F-1) ค่าเริ่มต้น M = (0, 1, 1, 0)

    ภาพ clean:  RM ~ R(-M)  และ  SM ~ S(-M)           (สมมติฐานของ RS)
    ยิ่งฝังมาก: RM ลดลง, SM เพิ่มขึ้น แต่ R(-M), S(-M) เปลี่ยนในทางตรงข้ามน้อยกว่า -> สองคู่นี้ "แยกออกจากกัน"

ตัวแปรสำคัญ (อ่านตารางนี้ก่อน)
    group                 pixel 4 ตัวที่ติดกันในแถวเดียวกัน (1 กลุ่ม)
    f(group)              ความขรุขระของกลุ่ม = ผลรวม |ผลต่างของ pixel ข้างเคียง|  (discrimination)
    RM / SM / UM          สัดส่วนกลุ่ม Regular / Singular / Unusable เมื่อ flip ตาม mask M
    R_negM / S_negM / U_negM   เช่นเดียวกัน แต่ flip ตาม mask -M
    *_count               จำนวนกลุ่ม (ก่อนหารเป็นสัดส่วน)
    gap_observed          RM - SM          ของ "ภาพจริง"                    (ในบทความเรียก d0)
    gap_flipped           RM - SM          ของ "ภาพที่ flip LSB ทั้งภาพ"     (d1)
    gap_observed_neg      R(-M) - S(-M)    ของภาพจริง                       (d-0)
    gap_flipped_neg       R(-M) - S(-M)    ของภาพที่ flip ทั้งภาพ            (d-1)
    x                     ตัวไม่ทราบค่าของสมการ (ยังไม่ใช่อัตราการฝัง) ; rate = x / (x - 1/2)
    embedding_rate        อัตราการฝัง = bit ที่ฝัง / จำนวน sample ทั้งหมด (0..1) = สิ่งที่ต้องการประมาณ

ประมาณอัตราการฝัง (payload_from_results)
    วัด 2 ครั้ง: ภาพจริง และภาพที่ XOR LSB ทุก pixel (เทียบเท่าฝังเต็ม 100%) ได้ค่า 8 ตัว
    แก้สมการกำลังสองของ Fridrich  2(d1+d0)x^2 + (d-0 - d-1 - d1 - 3*d0)x + (d0 - d-0) = 0
        d0 = RM-SM,  d-0 = R(-M)-S(-M)  จากภาพจริง ;  d1, d-1 = ค่าเดียวกันจากภาพที่ flip ทั้งภาพ
    เลือกรากที่ |x| น้อยกว่า แล้ว  rate = x / (x - 1/2)   (rate = สัดส่วนของ sample ที่ใช้ฝัง 0..1)

ข้อจำกัดที่เห็นจากการทดลอง
    - ภาพ clean ไม่ได้ให้ค่า 0 เป๊ะ (สมมติฐาน RM~R(-M) ไม่ตรงทุกภาพ) จึงมีพื้นหลัง/bias เล็กน้อย
    - ที่ rate ต่ำมาก (< ~0.1) แยกจากพื้นหลังได้ยาก
    - ต้องการภาพที่มีหลายกลุ่ม; ภาพเล็กหรือเรียบมาก (เช่น ภาพวาด) ผลแกว่ง
"""
import argparse
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from PIL import Image

DEFAULT_MASK = (0, 1, 1, 0)
GROUP_SIZE = 4


@dataclass
class RSResult:
    """จำนวนและสัดส่วนกลุ่ม R/S/U ภายใต้ mask M และ -M"""

    total_groups: int = 0          # จำนวนกลุ่ม 4 pixel ที่วัดได้ (RM+SM+UM)
    sample_count: int = 0          # จำนวน sample ในกลุ่มเหล่านั้น (= total_groups x 4)
    RM_count: int = 0              # จำนวนกลุ่ม Regular   ภายใต้ M   (flip แล้วขรุขระขึ้น)
    SM_count: int = 0              # จำนวนกลุ่ม Singular  ภายใต้ M   (flip แล้วเรียบขึ้น)
    UM_count: int = 0              # จำนวนกลุ่ม Unusable  ภายใต้ M   (flip แล้วเท่าเดิม)
    R_negM_count: int = 0          # จำนวนกลุ่ม Regular   ภายใต้ -M
    S_negM_count: int = 0          # จำนวนกลุ่ม Singular  ภายใต้ -M
    U_negM_count: int = 0          # จำนวนกลุ่ม Unusable  ภายใต้ -M
    RM: Optional[float] = None     # RM_count / total_groups    (สัดส่วน; None ถ้าไม่มีกลุ่ม)
    SM: Optional[float] = None
    UM: Optional[float] = None
    R_negM: Optional[float] = None
    S_negM: Optional[float] = None
    U_negM: Optional[float] = None


@dataclass
class RSPayloadEstimate:
    """อัตราการฝังที่ประมาณได้ (embedding_rate) และขนาด payload

    status บอกว่าประมาณได้หรือไม่ และถ้าไม่ได้เพราะอะไร (ใช้ชื่อชุดเดียวกับ SPA):
        estimated            ประมาณได้ และอยู่ในช่วง 0..1
        out_of_range         ประมาณได้ แต่ค่านอก 0..1 (เก็บ embedding_rate ไว้ให้ดู ไม่แปลงเป็น payload)
        insufficient_groups  ไม่มีกลุ่มให้วัด (ภาพแคบกว่า 4 pixel / ค่าใดค่าหนึ่งใน 8 ค่าเป็น None)
        degenerate_equation  a และ b ของสมการ ~ 0 หาคำตอบไม่ได้
        no_real_root         discriminant ติดลบ (เช่นเมื่อฝังเต็มทั้งภาพ)
        non_finite_root      รากไม่ใช่จำนวนจำกัด
    """

    embedding_rate: Optional[float]
    estimated_payload_bits: Optional[float]
    expected_changed_samples: Optional[float]
    capacity_samples: int
    root: Optional[float] = None
    status: str = "unavailable"
    reason: Optional[str] = None


@dataclass
class PrefixResult:
    """ผล RS ของ pixel_count pixel แรก (ตามลำดับ raster)"""

    percent: int
    pixel_count: int
    rs: RSResult


# --------------------------------------------------------------------------------------------
# ขั้นพื้นฐาน: นับสัดส่วนกลุ่ม
# --------------------------------------------------------------------------------------------

def result_from_counts(counts: Sequence[int]) -> RSResult:
    """counts = (RM, SM, UM, R-M, S-M, U-M) เป็นจำนวนกลุ่ม -> RSResult (มีสัดส่วนด้วย)"""
    regular_m, singular_m, unusable_m, regular_neg_m, singular_neg_m, unusable_neg_m = (int(count) for count in counts)
    total_groups = regular_m + singular_m + unusable_m       # จำนวนกลุ่มทั้งหมด (ของ M และ -M เท่ากัน)
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


def make_groups(channel: np.ndarray, pixel_limit: int) -> np.ndarray:
    """แบ่งเป็นกลุ่ม 4 pixel แนวนอน ไม่ซ้อนกัน และไม่ข้ามแถว ใช้เฉพาะ pixel_limit ตัวแรก (ตามลำดับ raster)"""
    height, width = channel.shape
    if width < GROUP_SIZE or pixel_limit == 0:
        return np.empty((0, GROUP_SIZE), dtype=channel.dtype)

    full_rows, remainder = divmod(pixel_limit, width)      # แถวที่ใช้เต็ม + pixel ที่เหลือในแถวถัดไป
    usable_width = (width // GROUP_SIZE) * GROUP_SIZE      # ตัดส่วนท้ายแถวที่ไม่ครบ 4
    groups = channel[:full_rows, :usable_width].reshape(-1, GROUP_SIZE)

    if remainder >= GROUP_SIZE and full_rows < height:      # แถวสุดท้ายที่ใช้ไม่เต็ม
        usable_remainder = (remainder // GROUP_SIZE) * GROUP_SIZE
        last_row = channel[full_rows, :usable_remainder].reshape(-1, GROUP_SIZE)
        groups = np.concatenate((groups, last_row))
    return groups


def discrimination(groups: np.ndarray) -> np.ndarray:
    """f(G) = ผลรวมของ |ผลต่างระหว่าง pixel ข้างเคียง| ในแต่ละกลุ่ม (ยิ่งมาก = ยิ่งขรุขระ)"""
    return np.abs(np.diff(groups, axis=1)).sum(axis=1)


def flip(values: np.ndarray, operation: int) -> np.ndarray:
    """flip pixel: operation 1 = F1 (สลับ LSB), -1 = F-1 (เลื่อนคู่), 0 = ไม่แตะ

    F-1 ของ x = ((x+1) XOR 1) - 1  ->  คู่ -> -1, คี่ -> +1  (0->-1, 1->2, 2->1, 3->4, ...)
    หมายเหตุ: F-1 ทำให้ได้ -1 หรือ 256 ได้ จึงต้องใช้ชนิดมีเครื่องหมาย (int32) ไม่ใช่ uint8
    """
    if operation == 1:
        return values ^ 1
    if operation == -1:
        return values + np.where(values % 2 == 0, -1, 1)
    return values


def classify_counts(groups: np.ndarray, mask: Sequence[int]) -> tuple[int, int, int]:
    """นับกลุ่ม Regular / Singular / Unusable สำหรับ mask หนึ่งตัว"""
    flipped = groups.copy()
    for column, operation in enumerate(mask):                # flip เฉพาะตำแหน่งที่ mask ระบุ
        flipped[:, column] = flip(flipped[:, column], operation)

    before = discrimination(groups)
    after = discrimination(flipped)
    regular = int(np.count_nonzero(after > before))          # ขรุขระขึ้น
    singular = int(np.count_nonzero(after < before))         # เรียบขึ้น
    unusable = len(groups) - regular - singular              # เท่าเดิม
    return regular, singular, unusable


def rs_core(
    channel: np.ndarray,
    mask: Sequence[int] = DEFAULT_MASK,
    pixel_limit: Optional[int] = None,
) -> RSResult:
    """จำแนกกลุ่มของ 1 channel ภายใต้ M และ -M  (pixel_limit = ใช้แค่ pixel แรก n ตัว)"""

    # Step 0: ตรวจ input
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

    # Step 1: แบ่งกลุ่ม 4 pixel แล้วแปลงเป็น int32 (กัน uint8 ล้นตอน F-1 ได้ -1 / 256)
    groups = make_groups(channel, int(pixel_limit))
    if len(groups) == 0:
        return RSResult()
    groups = groups.astype(np.int32)

    # Step 2: นับ R/S/U ภายใต้ M และ -M (-M = กลับเครื่องหมายทุกตำแหน่งของ mask)
    counts_m = classify_counts(groups, mask)                                   # (Regular, Singular, Unusable) ภายใต้ M
    counts_neg_m = classify_counts(groups, tuple(-value for value in mask))    # เช่นเดียวกัน ภายใต้ -M
    return result_from_counts((*counts_m, *counts_neg_m))


# --------------------------------------------------------------------------------------------
# ประมาณอัตราการฝัง
# --------------------------------------------------------------------------------------------

def payload_from_results(
    observed: RSResult,
    fully_flipped: RSResult,
    capacity_samples: int,
) -> RSPayloadEstimate:
    """แก้สมการ RS ของ Fridrich จากภาพจริง (observed) และภาพที่ flip LSB ทั้งภาพ (fully_flipped)"""
    def unavailable(status: str, reason: str) -> RSPayloadEstimate:
        return RSPayloadEstimate(None, None, None, capacity_samples, status=status, reason=reason)

    # Step 1: ต้องมีครบทั้ง 8 ค่า (ไม่มี None)
    values = (
        observed.RM, observed.SM, observed.R_negM, observed.S_negM,
        fully_flipped.RM, fully_flipped.SM, fully_flipped.R_negM, fully_flipped.S_negM,
    )
    if any(value is None for value in values):
        return unavailable("insufficient_groups", "No complete 4-pixel groups are available to measure.")
    (regular_m, singular_m, regular_neg_m, singular_neg_m,                       # ภาพจริง
     regular_m_flipped, singular_m_flipped, regular_neg_m_flipped, singular_neg_m_flipped) = (
        float(value) for value in values)                                         # ภาพที่ flip LSB ทั้งภาพ

    # Step 2: ผลต่าง R-S ของแต่ละกรณี  (ภาพจริง / ภาพที่ flip ทั้งภาพ  x  mask M / -M)
    gap_observed = regular_m - singular_m                                  # d0
    gap_flipped = regular_m_flipped - singular_m_flipped                   # d1
    gap_observed_neg = regular_neg_m - singular_neg_m                      # d-0
    gap_flipped_neg = regular_neg_m_flipped - singular_neg_m_flipped       # d-1

    # Step 3: สมการกำลังสองในตัวแปร x :  a_term * x^2 + b_term * x + constant_term = 0
    a_term = 2.0 * (gap_flipped + gap_observed)
    b_term = gap_observed_neg - gap_flipped_neg - gap_flipped - 3.0 * gap_observed
    constant_term = gap_observed - gap_observed_neg       # = 0 พอดี ถ้าภาพ clean ตรงสมมติฐาน RM~R(-M), SM~S(-M)
    tiny = 1e-12                                          # ถือว่าเป็นศูนย์ถ้าเล็กกว่านี้

    if abs(a_term) < tiny:                    # เหลือสมการเชิงเส้น
        if abs(b_term) < tiny:
            return unavailable("degenerate_equation", "Both the quadratic and linear terms are effectively zero.")
        roots = [-constant_term / b_term]
    else:
        discriminant = b_term * b_term - 4.0 * a_term * constant_term     # b^2 - 4ac
        if discriminant < -tiny:              # ไม่มีรากจริง
            return unavailable("no_real_root", "The RS equation has a negative discriminant and no real root.")
        sqrt_discriminant = math.sqrt(max(0.0, discriminant))
        roots = [(-b_term + sqrt_discriminant) / (2.0 * a_term), (-b_term - sqrt_discriminant) / (2.0 * a_term)]

    # Step 4: เลือกรากที่ |x| น้อยกว่า (ตามบทความ) แล้วแปลงเป็นอัตราการฝัง  rate = x / (x - 1/2)
    root = min(roots, key=abs)
    if not math.isfinite(root) or abs(root - 0.5) < tiny:
        return unavailable("non_finite_root", "The selected root is not finite or makes the rate undefined.")
    embedding_rate = root / (root - 0.5)
    if not math.isfinite(embedding_rate):
        return unavailable("non_finite_root", "The embedding rate computed from the root is not finite.")

    # Step 5: ถ้าอยู่นอก 0..1 ยังเก็บค่าไว้ให้ดู แต่ไม่แปลงเป็นขนาด payload
    if not 0.0 <= embedding_rate <= 1.0:
        return RSPayloadEstimate(embedding_rate, None, None, capacity_samples, root,
                                 status="out_of_range",
                                 reason="The estimated rate lies outside the physical 0..100% range.")

    return RSPayloadEstimate(
        embedding_rate=embedding_rate,
        estimated_payload_bits=embedding_rate * capacity_samples,
        expected_changed_samples=embedding_rate * capacity_samples / 2.0,   # LSB replacement เปลี่ยนจริงครึ่งหนึ่ง
        capacity_samples=capacity_samples,
        root=root,
        status="estimated",
    )


def estimate_rs_payload(
    channel: np.ndarray,
    mask: Sequence[int] = DEFAULT_MASK,
    pixel_limit: Optional[int] = None,
) -> RSPayloadEstimate:
    """ประมาณอัตราการฝังของ 1 channel (วัดภาพจริง + ภาพที่ XOR LSB ทั้งภาพ)"""
    channel = np.asarray(channel)
    observed = rs_core(channel, mask=mask, pixel_limit=pixel_limit)
    fully_flipped = rs_core(np.bitwise_xor(channel, 1), mask=mask, pixel_limit=pixel_limit)
    capacity_samples = int(channel.size) if pixel_limit is None else int(pixel_limit)
    return payload_from_results(observed, fully_flipped, capacity_samples)


# --------------------------------------------------------------------------------------------
# Prefix และรวมหลาย channel
# --------------------------------------------------------------------------------------------

def progressive_prefix(
    channel: np.ndarray,
    mask: Sequence[int] = DEFAULT_MASK,
    step: int = 10,
) -> List[PrefixResult]:
    """RS ของ 0-step%, 0-2*step%, ... 0-100% ของภาพ (สะสมตามลำดับ raster)"""
    if isinstance(step, bool) or not isinstance(step, (int, np.integer)) or not 1 <= step <= 100:
        raise ValueError("step must be an integer in the range 1..100.")
    channel = np.asarray(channel)
    if channel.ndim != 2:
        raise ValueError("channel must be a 2D image array.")

    results: List[PrefixResult] = []
    for percent in list(range(step, 100, step)) + [100]:     # เติม 100 เสมอ
        pixel_count = math.ceil(channel.size * percent / 100)
        results.append(PrefixResult(percent, pixel_count, rs_core(channel, mask=mask, pixel_limit=pixel_count)))
    return results


def pool_rs_results(results: Sequence[RSResult]) -> RSResult:
    """รวม "จำนวนกลุ่ม" ของหลาย channel ก่อน แล้วค่อยหาสัดส่วนร่วม (ไม่ใช่เฉลี่ยสัดส่วน)"""
    pooled_counts = [0] * 6                                   # RM, SM, UM, R-M, S-M, U-M (จำนวนกลุ่ม)
    for result in results:
        for position, group_count in enumerate((
            result.RM_count, result.SM_count, result.UM_count,
            result.R_negM_count, result.S_negM_count, result.U_negM_count,
        )):
            pooled_counts[position] += group_count
    return result_from_counts(pooled_counts)


# --------------------------------------------------------------------------------------------
# โหลดภาพ + รันครบชุด
# --------------------------------------------------------------------------------------------

def load_image_targets(image_path: str) -> Dict[str, np.ndarray]:
    """โหลดภาพ 8 bit L / RGB / RGBA -> {"R","G","B"} หรือ {"L"} (ทิ้ง alpha)"""
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
    """วิเคราะห์ทีละ channel แล้วรวมนับกลุ่มของ RGB เป็น "Whole" """
    targets = load_image_targets(image_path)
    report: Dict[str, Dict[str, Any]] = {}
    flipped_results: Dict[str, RSResult] = {}

    for name, channel in targets.items():
        whole = rs_core(channel, mask=mask)
        fully_flipped = rs_core(np.bitwise_xor(channel, 1), mask=mask)
        flipped_results[name] = fully_flipped
        report[name] = {
            "whole": whole,
            "payload": payload_from_results(whole, fully_flipped, channel.size),
            "prefix": progressive_prefix(channel, mask=mask, step=prefix_step),
        }

    if len(targets) > 1:                                       # ภาพสี: รวม 3 channel เป็น Whole
        names = list(targets)
        whole_result = pool_rs_results([report[n]["whole"] for n in names])
        whole_flipped = pool_rs_results([flipped_results[n] for n in names])
        capacity_samples = sum(targets[n].size for n in names)
        whole_prefix: List[PrefixResult] = []
        for index, item in enumerate(report[names[0]]["prefix"]):
            pooled = pool_rs_results([report[n]["prefix"][index].rs for n in names])
            whole_prefix.append(PrefixResult(item.percent, item.pixel_count, pooled))
        report = {
            "Whole": {
                "whole": whole_result,
                "payload": payload_from_results(whole_result, whole_flipped, capacity_samples),
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
        print(f"  Estimated payload: rate={rate}, bits={result.estimated_payload_bits:.0f}, "
              f"expected_changed={result.expected_changed_samples:.0f}")

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
