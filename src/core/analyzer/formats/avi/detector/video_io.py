"""Shared frame validation and range helpers for AVI detectors."""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import Any

import numpy as np


def _require_cv2():
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Video analysis requires the 'opencv-python' package."
        ) from exc
    return cv2


def video_info(path: str) -> dict[str, Any]:
    """Read basic video header information for detector CLI wrappers."""
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
            "codec": "".join(
                chr((fourcc >> (8 * index)) & 0xFF) for index in range(4)
            ).rstrip("\x00 ").strip() or "RAW",
        }
    finally:
        capture.release()
    if info["width"] <= 0 or info["height"] <= 0:
        raise ValueError("Video has an invalid resolution.")
    return info


def iter_frames(
    path: str,
    start_frame: int = 0,
    frame_count: int | None = None,
) -> Iterator[tuple[int, np.ndarray]]:
    """Yield contiguous RGB uint8 frames for standalone detector use."""
    cv2 = _require_cv2()
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"OpenCV cannot open video: {path}")
        index = yielded = 0
        while frame_count is None or yielded < frame_count:
            success, bgr_frame = capture.read()
            if not success:
                break
            if index >= start_frame:
                if (
                    bgr_frame.dtype != np.uint8
                    or bgr_frame.ndim != 3
                    or bgr_frame.shape[2] != 3
                ):
                    raise ValueError(
                        f"Frame {index} is not an 8-bit 3-channel image."
                    )
                yield index, np.ascontiguousarray(bgr_frame[:, :, ::-1])
                yielded += 1
            index += 1
    finally:
        capture.release()


def check_frame(frame: np.ndarray, height: int, width: int) -> np.ndarray:
    """Validate the common detector input contract: RGB uint8 HxWx3."""
    frame = np.asarray(frame)
    if frame.dtype != np.uint8 or frame.shape != (height, width, 3):
        raise ValueError(
            f"frame must be a ({height}, {width}, 3) uint8 RGB array."
        )
    return frame


def _check_percent(name: str, value: int) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, np.integer))
        or not 1 <= value <= 100
    ):
        raise ValueError(f"{name} must be an integer in the range 1..100.")


def prefix_ranges(total: int, step: int) -> list[tuple[int, int]]:
    """Return cumulative ``(percent, exclusive_end)`` ranges."""
    _check_percent("prefix step", step)
    percentages = [*range(step, 100, step), 100]
    return [
        (percent, math.ceil(total * percent / 100))
        for percent in percentages
    ]


def sliding_ranges(
    total: int,
    segment_percent: int,
    step_percent: int,
) -> list[tuple[int, int]]:
    """Return sliding ``(inclusive_start, exclusive_end)`` ranges."""
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
    """Prefix sums with a zero row so span [start, end) is O(1)."""
    series = np.asarray(series, dtype=np.int64)
    zero = np.zeros((1, *series.shape[1:]), dtype=np.int64)
    return np.concatenate((zero, np.cumsum(series, axis=0)))
