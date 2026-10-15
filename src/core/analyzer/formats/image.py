"""Image Analyzer backend.

File Structure and Metadata use Docker inspection. Bit Statistics is backed by
the validated Chi-square, RS, and SPA image detectors.
"""

from pathlib import Path
from typing import Any

from PIL import Image

from src.core.analyzer.bit_statistics.chi_square import analyze_chi_square
from src.core.analyzer.bit_statistics.rs_analysis import analyze_rs
from src.core.analyzer.bit_statistics.spa import analyze_spa
from src.core.analyzer.file_types import AnalyzerFileType


def analyze_file_structure(file_info: AnalyzerFileType) -> dict[str, Any]:
    from src.core.analyzer.inspection.bridge import inspect
    print(f"[File Structure] format={file_info.format_name} media=image")
    return inspect(file_info.path)["structure_analysis"]


def analyze_metadata(file_info: AnalyzerFileType) -> dict[str, Any]:
    from src.core.analyzer.inspection.bridge import inspect
    print(f"[Metadata] format={file_info.format_name} media=image")
    return inspect(file_info.path)["metadata_analysis"]


def analyze_bit_statistics(
    file_info: AnalyzerFileType,
    *,
    min_expected: float = 5.0,
    prefix_step: int = 10,
    segment_percent: int = 10,
    segment_step: int = 5,
    spa_j: int = 30,
    spa_min_pairs: int = 100,
) -> dict[str, Any]:
    """Run the three validated image bit-statistics detectors."""
    print(f"[Bit Statistics] format={file_info.format_name} media=image")
    with Image.open(file_info.path) as image:
        image_info = {
            "name": Path(file_info.path).name,
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
            "format": image.format,
        }

    return {
        "image_info": image_info,
        "chi_square": analyze_chi_square(
            file_info.path,
            min_expected=min_expected,
            prefix_step=prefix_step,
            segment_percent=segment_percent,
            segment_step=segment_step,
        ),
        "rs": analyze_rs(file_info.path, prefix_step=prefix_step),
        "spa": analyze_spa(
            file_info.path,
            j=spa_j,
            min_pairs=spa_min_pairs,
        ),
    }


