"""อ่านวิดีโอทีละเฟรม + สร้างช่วง prefix / segment ที่ detector วิดีโอทั้งสามใช้ร่วมกัน

หลักการของ detector วิดีโอ
    วิดีโอ = ภาพหลายภาพเรียงตามเวลา แต่ละเฟรม (H, W, 3) ใช้ detector ของภาพได้ตรง ๆ
    ทุก detector คำนวณจาก "จำนวนนับ" (count) ที่บวกกันได้ จึงอ่านทีละเฟรม เก็บแค่ count ต่อเฟรม
    แล้วรวม (pool) ข้ามเฟรมก่อนคำนวณสถิติ -> ไม่ต้องโหลดทั้งวิดีโอ และได้ผลหลายระดับจาก count ชุดเดียว

ระดับผลลัพธ์ (หน่วยของตำแหน่ง)
    whole               ทั้งวิดีโอ (รวม count ทุกเฟรม)
    per_frame           ทีละเฟรม -> กราฟตามเวลา
    temporal_prefix     เฟรม 0..10%, 0..20%, ... (สะสม)          หน่วย = เฟรม   -> หาจุดจบของการฝังต่อเนื่องตามแกนเวลา
    temporal_segments   หน้าต่างเฟรมเลื่อน (ไม่สะสม)               หน่วย = เฟรม   -> หาช่วงเฟรมที่ฝังกลางวิดีโอ
    spatial_prefix      pixel 0..10%, 0..20%, ... ของ "ทุกเฟรม"    หน่วย = pixel  -> การฝังที่เริ่มจากต้นเฟรมทุกเฟรม
    spatial_segments    หน้าต่าง pixel เลื่อน ของทุกเฟรม           หน่วย = pixel  -> ช่วง pixel ที่ฝังกลางเฟรม

ช่วงทั้งหมดใช้กฎเดียวกับ image_detector: ปลายช่วง = ceil(total x percent / 100), prefix เติม 100% เสมอ,
หน้าต่างสุดท้ายถูกบังคับให้ชิดท้าย ; start รวม, end ไม่รวม
"""
import math
from typing import Any, Dict, Iterator, List, Optional, Tuple

import numpy as np


def _require_cv2():
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise RuntimeError("Video analysis requires the 'opencv-python' package.") from exc
    return cv2


def video_info(path: str) -> Dict[str, Any]:
    """ข้อมูลพื้นฐานจาก header (จำนวนเฟรมจริงนับตอนอ่าน)"""
    cv2 = _require_cv2()
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"OpenCV cannot open video: {path}")
        fourcc = int(capture.get(cv2.CAP_PROP_FOURCC))
        info = {
            "width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "frame_rate": float(capture.get(cv2.CAP_PROP_FPS)),
            "header_frame_count": int(capture.get(cv2.CAP_PROP_FRAME_COUNT)),
            "codec": "".join(chr((fourcc >> (8 * i)) & 0xFF) for i in range(4)).rstrip("\x00 ").strip() or "RAW",
        }
    finally:
        capture.release()
    if info["width"] <= 0 or info["height"] <= 0:
        raise ValueError("Video has an invalid resolution.")
    return info


def iter_frames(path: str, start_frame: int = 0, frame_count: Optional[int] = None
                ) -> Iterator[Tuple[int, np.ndarray]]:
    """ให้ (index, เฟรม RGB uint8 (H, W, 3)) ทีละเฟรม ; อ่านต่อเนื่องไม่ seek เพื่อให้ได้เฟรมตรงลำดับแน่นอน"""
    cv2 = _require_cv2()
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"OpenCV cannot open video: {path}")
        index = yielded = 0
        while frame_count is None or yielded < frame_count:
            success, frame = capture.read()
            if not success:
                break
            if index >= start_frame:
                if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
                    raise ValueError(f"Frame {index} is not an 8-bit 3-channel image.")
                yield index, np.ascontiguousarray(frame[:, :, ::-1])        # BGR -> RGB
                yielded += 1
            index += 1
    finally:
        capture.release()


def check_frame(frame: np.ndarray, height: int, width: int) -> np.ndarray:
    frame = np.asarray(frame)
    if frame.dtype != np.uint8 or frame.shape != (height, width, 3):
        raise ValueError(f"frame must be a ({height}, {width}, 3) uint8 RGB array.")
    return frame


def _check_percent(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or not 1 <= value <= 100:
        raise ValueError(f"{name} must be an integer in the range 1..100.")


def prefix_ranges(total: int, step: int) -> List[Tuple[int, int]]:
    """[(percent, end)] ของ 0..step%, 0..2step%, ..., 0..100%"""
    _check_percent("prefix step", step)
    return [(percent, math.ceil(total * percent / 100)) for percent in list(range(step, 100, step)) + [100]]


def sliding_ranges(total: int, segment_percent: int, step_percent: int) -> List[Tuple[int, int]]:
    """[(start, end)] หน้าต่างยาว segment_percent% เลื่อนทีละ step_percent% ; หน้าต่างสุดท้ายชิดท้าย"""
    _check_percent("segment length", segment_percent)
    _check_percent("segment step", step_percent)
    if step_percent > segment_percent:
        raise ValueError("segment step must not exceed segment length.")
    if total == 0:
        return []
    window = math.ceil(total * segment_percent / 100)
    stride = max(1, math.ceil(total * step_percent / 100))
    starts = list(range(0, total - window + 1, stride))
    if starts[-1] != total - window:
        starts.append(total - window)
    return [(start, start + window) for start in starts]


def cumulative(series: np.ndarray) -> np.ndarray:
    """cumsum ตามแกนแรก โดยเติม 0 ข้างหน้า: out[k] = ผลรวมของ series[0:k]  -> ช่วง [s, e) = out[e] - out[s]"""
    series = np.asarray(series, dtype=np.int64)
    return np.concatenate((np.zeros((1, *series.shape[1:]), dtype=np.int64), np.cumsum(series, axis=0)))
