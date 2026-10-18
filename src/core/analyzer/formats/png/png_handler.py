"""PNG loading and adaptation of the reference detectors to shared models."""

from pathlib import Path

import numpy as np
from PIL import Image

from src.core.analyzer.formats.png.detector.chi_square import (
    analyze_chi_square,
    sliding_segment,
)
from src.core.analyzer.formats.png.detector.rs_analysis import (
    analyze_rs,
    load_image_targets,
    payload_from_results,
    pool_rs_results,
    rs_core,
)
from src.core.analyzer.formats.png.detector.spa import analyze_spa
from src.core.analyzer.formats.png.profile_evaluator import (
    evaluate_chi_square,
    evaluate_rs,
    evaluate_spa,
)
from src.core.analyzer.models.analysis import AnalysisResult
from src.core.analyzer.models.common import BitStatisticsResult, FileInfo, RSMeasurement
from src.core.analyzer.models.png import (
    PNGChiSquareResult,
    PNGMediaInfo,
    PNGRSResult,
    PNGSPAAnalysis,
    PNGSPAResult,
)
from src.core.analyzer.models.series import SpatialPrefix, SpatialSegment, SpatialSeries
from src.core.analyzer.parameters import AnalysisParameters


class PNGHandler:
    """Analyze an 8-bit L, RGB or RGBA PNG without changing its pixels."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path).expanduser().resolve()

    def analyze(self, parameters: AnalysisParameters | None = None) -> AnalysisResult:
        selected = parameters or AnalysisParameters()
        selected.validate()

        if not self.file_path.is_file():
            raise FileNotFoundError(f"File not found: {self.file_path}")
        if self.file_path.suffix.lower() != ".png":
            raise ValueError(f"Expected a .png file: {self.file_path}")

        try:
            with Image.open(self.file_path) as image:
                if image.format != "PNG":
                    raise ValueError(f"Not a valid PNG file: {self.file_path}")
                if image.mode not in {"L", "RGB", "RGBA"}:
                    raise ValueError("PNG analysis supports 8-bit L, RGB or RGBA images only.")
                image.load()
                media_info = PNGMediaInfo(image.width, image.height, image.mode)
        except OSError as exc:
            raise ValueError(f"Not a valid PNG file: {self.file_path}") from exc

        chi_raw = analyze_chi_square(
            str(self.file_path),
            min_expected=selected.min_expected,
            prefix_step=selected.prefix_step,
            segment_percent=selected.segment_percent,
            segment_step=selected.segment_step,
        )
        rs_raw = analyze_rs(str(self.file_path), prefix_step=selected.prefix_step)
        spa_raw = analyze_spa(
            str(self.file_path),
            j=selected.spa_j,
            min_pairs=selected.spa_min_pairs,
        )

        chi_channels = {}
        for name, report in chi_raw.items():
            samples_per_pixel = 3 if name == "Whole" else 1
            chi_channels[name] = SpatialSeries(
                whole=report["whole"],
                prefix=tuple(
                    SpatialPrefix(
                        percent=item.percent,
                        end=item.sample_count // samples_per_pixel,
                        analysis=item.chi_square,
                    )
                    for item in report["prefix"]
                ),
                segments=tuple(
                    SpatialSegment(item.start, item.end, item.chi_square)
                    for item in report["segments"]
                ),
            )

        rs_targets = load_image_targets(str(self.file_path))
        locked_chi_raw = chi_raw
        if (selected.min_expected != 5 or selected.segment_percent != 5
                or selected.segment_step != 1):
            target_name = "Whole" if "Whole" in chi_raw else "L"
            target_pixels = (
                np.stack(tuple(rs_targets[name] for name in "RGB"), axis=-1)
                if target_name == "Whole" else rs_targets["L"]
            )
            locked_chi_raw = {
                target_name: {
                    "segments": sliding_segment(
                        target_pixels, min_expected=5,
                        segment_percent=5, step_percent=1,
                    ),
                },
            }
        locked_spa_raw = spa_raw
        if selected.spa_j != 30 or selected.spa_min_pairs != 100:
            locked_spa_raw = analyze_spa(str(self.file_path), j=30, min_pairs=100)
        locked_parameters = AnalysisParameters(segment_percent=5, segment_step=1)
        rs_channels = {}
        for name, report in rs_raw.items():
            source_channels = (
                tuple(rs_targets.values()) if name == "Whole" else (rs_targets[name],)
            )
            prefixes = []
            for item in report["prefix"]:
                flipped = [
                    rs_core(np.bitwise_xor(channel, 1), pixel_limit=item.pixel_count)
                    for channel in source_channels
                ]
                flipped_result = (
                    pool_rs_results(flipped) if len(flipped) > 1 else flipped[0]
                )
                prefix_payload = payload_from_results(
                    item.rs,
                    flipped_result,
                    item.pixel_count * len(source_channels),
                )
                prefixes.append(
                    SpatialPrefix(
                        item.percent,
                        item.pixel_count,
                        RSMeasurement(item.rs, prefix_payload),
                    )
                )
            rs_channels[name] = SpatialSeries(
                whole=RSMeasurement(report["whole"], report["payload"]),
                prefix=tuple(prefixes),
                segments=(),
            )
        spa_channels = {
            name: PNGSPAAnalysis(report["statistics"], report["estimate"])
            for name, report in spa_raw.items()
        }

        return AnalysisResult(
            file=FileInfo(
                path=str(self.file_path),
                name=self.file_path.name,
                extension=self.file_path.suffix.lower(),
                size=self.file_path.stat().st_size,
                format="PNG",
            ),
            media_info=media_info,
            parameters=selected,
            structure=None,
            metadata=None,
            bit_statistics=BitStatisticsResult(
                chi_square=PNGChiSquareResult(
                    chi_channels,
                    decision=evaluate_chi_square(locked_chi_raw, locked_parameters),
                ),
                rs=PNGRSResult(rs_channels, decision=evaluate_rs(rs_raw)),
                spa=PNGSPAResult(
                    spa_channels,
                    decision=evaluate_spa(locked_spa_raw, locked_parameters),
                ),
            ),
        )
