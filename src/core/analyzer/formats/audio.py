"""WAV bit statistics and shared Docker-backed file inspection."""

from typing import Any

from src.core.analyzer.file_types import AnalyzerFileType


def analyze_file_structure(file_info: AnalyzerFileType) -> dict[str, Any]:
    from src.core.analyzer.inspection.bridge import inspect
    print(f"[File Structure] format={file_info.format_name} media=audio")
    return inspect(file_info.path)["structure_analysis"]


def analyze_metadata(file_info: AnalyzerFileType) -> dict[str, Any]:
    from src.core.analyzer.inspection.bridge import inspect
    print(f"[Metadata] format={file_info.format_name} media=audio")
    return inspect(file_info.path)["metadata_analysis"]


def analyze_bit_statistics(
    file_info: AnalyzerFileType, *, min_expected=5.0, prefix_step=10,
    segment_percent=10, segment_step=5, spa_j=30, spa_min_pairs=100,
    progress_callback=None, cancel_check=None,
) -> dict[str, Any]:
    """Analyze PCM sample sequences, keeping stereo channels independent."""
    from src.core.analyzer.bit_statistics.audio.wav_io import read_wav
    from src.core.analyzer.bit_statistics.audio.detectors import (
        chi_counts, chi_result, rs_measurement, spa_measurement,
    )
    from src.core.analyzer.bit_statistics.video.video_io import prefix_ranges, sliding_ranges
    from src.core.analyzer.bit_statistics.video.chi_square import PrefixResult as ChiPrefix, SegmentResult as ChiSegment
    from src.core.analyzer.bit_statistics.video.rs_analysis import RSMeasurement, RangeResult as RSRange
    from src.core.analyzer.bit_statistics.video.spa import RangeResult as SPARange

    print(f"[Bit Statistics] format={file_info.format_name} media=audio")
    info, samples = read_wav(file_info.path)
    total = len(samples)
    if not total:
        raise ValueError("WAV has no PCM samples to analyze.")
    prefixes = prefix_ranges(total, prefix_step)
    segments = sliding_ranges(total, segment_percent, segment_step)
    channels = {name: index for index, name in enumerate(info["channel_names"])}
    targets = ("Whole", *channels)
    reports = {name: {target: {"progressive_prefix": [], "segments": []}
                      for target in targets} for name in ("chi_square", "rs", "spa")}

    ranges = [("whole", 0, total, None)]
    ranges += [("prefix", 0, end, percent) for percent, end in prefixes]
    ranges += [("segment", start, end, None) for start, end in segments]
    for position, (kind, start, end, percent) in enumerate(ranges, 1):
        if cancel_check and cancel_check():
            raise RuntimeError("Analysis cancelled.")
        values = {name: samples[start:end, index] for name, index in channels.items()}
        for target in targets:
            selected = list(values.values()) if target == "Whole" else [values[target]]
            counts = sum((chi_counts(value, info["bits_per_sample"]) for value in selected))
            chi = chi_result(counts, min_expected)
            rs, payload = rs_measurement(selected)
            stats, spa = spa_measurement(selected, spa_j, spa_min_pairs)
            data = {name: reports[name][target] for name in reports}
            if kind == "whole":
                data["chi_square"]["whole"] = chi
                data["rs"].update(whole=rs, payload=payload)
                data["spa"].update(statistics=stats, estimate=spa)
            elif kind == "prefix":
                data["chi_square"]["progressive_prefix"].append(ChiPrefix(percent, end, chi))
                data["rs"]["progressive_prefix"].append(RSRange(start, end, percent, RSMeasurement(rs, payload)))
                data["spa"]["progressive_prefix"].append(SPARange(start, end, percent, spa))
            else:
                data["chi_square"]["segments"].append(ChiSegment(start, end, chi))
                data["rs"]["segments"].append(RSRange(start, end, None, RSMeasurement(rs, payload)))
                data["spa"]["segments"].append(SPARange(start, end, None, spa))
        if progress_callback:
            progress_callback(min(95, int(position * 95 / len(ranges))), f"Audio range {position}/{len(ranges)}")
    for data in reports["chi_square"].values():
        data["prefix"] = data["progressive_prefix"]
    for data in reports["rs"].values():
        data["prefix"] = data["progressive_prefix"]
    if progress_callback:
        progress_callback(100, "Analysis complete")
    return {"audio_info": info, **reports}


