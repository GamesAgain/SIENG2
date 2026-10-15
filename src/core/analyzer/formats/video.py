"""AVI bit statistics and shared Docker-backed file inspection."""

from typing import Any

from src.core.analyzer.file_types import AnalyzerFileType


def analyze_file_structure(file_info: AnalyzerFileType) -> dict[str, Any]:
    from src.core.analyzer.inspection.bridge import inspect
    print(f"[File Structure] format={file_info.format_name} media=video")
    return inspect(file_info.path)["structure_analysis"]


def analyze_metadata(file_info: AnalyzerFileType) -> dict[str, Any]:
    from src.core.analyzer.inspection.bridge import inspect
    print(f"[Metadata] format={file_info.format_name} media=video")
    return inspect(file_info.path)["metadata_analysis"]


def analyze_bit_statistics(
    file_info: AnalyzerFileType, *, min_expected=5.0, prefix_step=10,
    segment_percent=10, segment_step=5, spa_j=30, spa_min_pairs=100,
    start_frame=0, frame_count=None, progress_callback=None, cancel_check=None,
) -> dict[str, Any]:
    """Decode once and feed exactly the same RGB frames to all detectors."""
    from src.core.analyzer.bit_statistics.video.chi_square import ChiSquareVideo
    from src.core.analyzer.bit_statistics.video.rs_analysis import RSVideo
    from src.core.analyzer.bit_statistics.video.spa import SPAVideo
    from src.core.analyzer.bit_statistics.video.video_io import video_info, iter_frames

    if start_frame < 0 or (frame_count is not None and frame_count < 1):
        raise ValueError("Invalid video frame range.")
    print(f"[Bit Statistics] format={file_info.format_name} media=video")
    info = video_info(file_info.path)
    args = (prefix_step, segment_percent, segment_step)
    chi = ChiSquareVideo(info["height"], info["width"], min_expected, *args)
    rs = RSVideo(info["height"], info["width"], prefix_step=prefix_step,
                 segment_percent=segment_percent, segment_step=segment_step)
    spa = SPAVideo(info["height"], info["width"], spa_j, spa_min_pairs, *args)
    count = 0
    expected = max(1, info["header_frame_count"] - start_frame)
    if frame_count is not None:
        expected = min(expected, frame_count)
    for index, frame in iter_frames(file_info.path, start_frame, frame_count):
        if cancel_check and cancel_check():
            raise RuntimeError("Analysis cancelled.")
        chi.add(frame)
        rs.add(frame)
        spa.add(frame)
        count += 1
        if progress_callback and (count == 1 or count % 10 == 0):
            progress_callback(min(95, int(count * 95 / expected)), f"Frame {index}")
    reports = {"chi_square": chi.finish(), "rs": rs.finish(), "spa": spa.finish()}
    if any(report["frame_count"] != count for report in reports.values()):
        raise RuntimeError("Detector frame counts do not match.")
    fps = info["frame_rate"]
    info.update(decoded_frame_count=count, start_frame=start_frame,
                end_frame=start_frame + count,
                duration_seconds=count / fps if fps > 0 else None)
    for report in reports.values():
        for target in report["targets"].values():
            target["progressive_prefix"] = target["temporal_prefix"]
            target["frame_segments"] = target["temporal_segments"]
    if progress_callback:
        progress_callback(100, "Analysis complete")
    return {"video_info": info, **reports}


def analyze_video_frame_details(file_path, frame_index, parameters, cancel_check=None):
    """Read an exact frame sequentially and calculate image-style spatial details."""
    import numpy as np
    from src.core.analyzer.bit_statistics.video.video_io import iter_frames
    from src.core.analyzer.bit_statistics import chi_square, rs_analysis, spa

    selected = None
    for index, frame in iter_frames(file_path):
        if cancel_check and cancel_check():
            raise RuntimeError("Frame analysis cancelled.")
        if index == frame_index:
            selected = frame
            break
    if selected is None:
        raise ValueError(f"Cannot read frame {frame_index}.")
    targets = {"Whole": selected, **{name: selected[:, :, i] for i, name in enumerate("RGB")}}
    chi_report = {}
    rs_report = {}
    spa_stats = {}
    for name, samples in targets.items():
        chi_report[name] = {
            "whole": chi_square.chi_square_pov(samples.ravel(), parameters.min_expected),
            "prefix": chi_square.progressive_prefix(samples, parameters.min_expected, parameters.prefix_step),
            "segments": chi_square.sliding_segment(samples, parameters.min_expected,
                                                   parameters.segment_percent, parameters.segment_step),
        }
        if name == "Whole":
            continue
        whole = rs_analysis.rs_core(samples)
        flipped = rs_analysis.rs_core(np.bitwise_xor(samples, 1))
        rs_report[name] = {"whole": whole,
            "payload": rs_analysis.payload_from_results(whole, flipped, samples.size),
            "prefix": rs_analysis.progressive_prefix(samples, step=parameters.prefix_step)}
        spa_stats[name] = spa.collect_spa_statistics(samples)
    pooled = rs_analysis.pool_rs_results([rs_report[n]["whole"] for n in "RGB"])
    flipped = rs_analysis.pool_rs_results([rs_analysis.rs_core(selected[:, :, i] ^ 1) for i in range(3)])
    prefix = []
    for i, item in enumerate(rs_report["R"]["prefix"]):
        prefix.append(rs_analysis.PrefixResult(item.percent, item.pixel_count,
            rs_analysis.pool_rs_results([rs_report[n]["prefix"][i].rs for n in "RGB"])))
    rs_report = {"Whole": {"whole": pooled,
        "payload": rs_analysis.payload_from_results(pooled, flipped, selected.size), "prefix": prefix}, **rs_report}
    spa_stats = {"Whole": spa.pool_spa_statistics(list(spa_stats.values())), **spa_stats}
    spa_report = {name: {"statistics": stats,
        "estimate": spa.estimate_spa(stats, j=parameters.spa_j, min_pairs=parameters.spa_min_pairs)}
        for name, stats in spa_stats.items()}
    return {"frame_index": frame_index, "chi_square": chi_report, "rs": rs_report, "spa": spa_report}


