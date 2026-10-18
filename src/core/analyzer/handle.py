from __future__ import annotations

import argparse
from pathlib import Path
from pprint import pprint
from typing import TYPE_CHECKING

from src.core.analyzer.formats.avi.avi_handler import AVIHandler
from src.core.analyzer.formats.png.png_handler import PNGHandler
from src.core.analyzer.formats.wav.wav_handler import WAVHandler
from src.core.analyzer.models.analysis import AnalysisResult
from src.core.analyzer.parameters import AnalysisParameters

if TYPE_CHECKING:
    from src.core.analyzer.models.avi import (
        AVIFrameChiSquareDetailResult,
        AVIFrameRSDetailResult,
        AVIFrameSPADetailResult,
    )


def analyze_file(
    file_path: str | Path,
    parameters: AnalysisParameters | None = None,
) -> AnalysisResult:
    path = Path(file_path).expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    extension = path.suffix.lower()

    if extension == ".png":
        handler = PNGHandler(path)
    elif extension == ".wav":
        handler = WAVHandler(path)
    elif extension == ".avi":
        handler = AVIHandler(path)
    else:
        raise ValueError(f"Unsupported file format: {extension or '(no extension)'}")

    return handler.analyze(parameters)


def analyze(
    file_path: str | Path,
    parameters: AnalysisParameters | None = None,
) -> AnalysisResult:
    """Public entry point used by the GUI or other parts of the application."""
    return analyze_file(file_path, parameters)


def print_analysis_result(result: AnalysisResult) -> None:
    """Print the important analyzer values in a CLI-friendly layout."""
    if result.file.format != "WAV":
        pprint(result, sort_dicts=False)
        return

    info = result.audio_info
    chi_report = result.chi_square
    chi_square = (
        chi_report.channels["CH1"].whole
        if chi_report is not None and "CH1" in chi_report.channels
        else None
    )

    print("WAV ANALYSIS RESULT")
    print(f"File              : {result.file.name}")
    print(f"Path              : {result.file.path}")
    print(f"File size         : {result.file.size:,} bytes")

    if info is not None:
        print(f"Channels          : {info.channel_count}")
        print(f"Sample rate       : {info.sample_rate:,} Hz")
        print(f"Frames            : {info.frame_count:,}")
        print(f"Samples           : {info.sample_count:,}")
        print(f"Duration          : {info.duration_seconds:.3f} seconds")
        print(f"Sample width      : {info.sample_width_bits}-bit")
        print(f"Compression       : {info.compression_type}")

    print("\nCHI-SQUARE (CH1)")
    if chi_square is None or chi_square.chi_square_total is None:
        sample_count = 0 if chi_square is None else chi_square.sample_count
        valid_pairs = 0 if chi_square is None else chi_square.valid_pairs
        print("Chi-square        : N/A")
        print("p-value           : N/A")
        print(f"Samples analyzed  : {sample_count:,}")
        print(f"Valid pairs       : {valid_pairs:,}")
        print("Reason            : Not enough valid value pairs")
    else:
        print(f"Chi-square        : {chi_square.chi_square_total:.10g}")
        print(f"p-value           : {chi_square.p_value:.10g}")
        print(f"Degrees of freedom: {chi_square.dof:,}")
        print(f"Samples analyzed  : {chi_square.sample_count:,}")
        print(f"Valid pairs       : {chi_square.valid_pairs:,}")

    print("\nRS ANALYSIS (CH1)")
    rs_report = result.rs
    rs_measurement = (
        rs_report.channels["CH1"].whole
        if rs_report is not None and "CH1" in rs_report.channels
        else None
    )
    if rs_measurement is None:
        print("Status            : unavailable")
    else:
        payload = rs_measurement.payload
        print(f"Groups            : {rs_measurement.rs.total_groups:,}")
        print(f"Status            : {payload.status}")
        print(
            "Estimated rate    : "
            + (f"{payload.embedding_rate * 100:.4f}%"
               if payload.embedding_rate is not None else "N/A")
        )
        if rs_report.decision is not None:
            labels = {
                "Stego": "Evidence found",
                "Clean": "No evidence found",
                "Unknown": "Unable to assess",
            }
            print(f"Assessment        : {labels[rs_report.decision.classification]}")
            if rs_report.decision.classification == "Unknown":
                print(f"Reason            : {rs_report.decision.reason}")

    print("\nSAMPLE PAIR ANALYSIS (CH1)")
    spa = result.spa
    if spa is None or "CH1" not in spa.channels:
        print("Status            : unavailable")
        print("Reason            : No CH1 SPA result")
        return

    spa_analysis = spa.channels["CH1"]
    estimate = spa_analysis.estimate
    decision = spa.decision
    print(
        f"Parameters        : j={spa_analysis.statistics.j}, "
        f"min pairs={result.parameters.spa_min_pairs:,}"
    )
    print(f"Status            : {estimate.status}")
    print(f"Samples analyzed  : {estimate.sample_count:,}")
    print(f"Adjacent pairs    : {estimate.pair_count:,}")
    if estimate.embedding_rate is None:
        print("Estimated rate    : N/A")
        print("Estimated bits    : N/A")
        print("Changed samples   : N/A")
        print(f"Reason            : {estimate.reason}")
        return

    print(f"Raw estimated rate: {estimate.embedding_rate * 100:.4f}%")
    if decision is not None and decision.evaluated_rate is not None:
        suffix = " (clamped)" if decision.was_clamped else ""
        print(
            f"Evaluated rate    : "
            f"{decision.evaluated_rate * 100:.4f}%{suffix}"
        )
    if estimate.estimated_payload_bits is None:
        print("Estimated bits    : N/A")
        print("Changed samples   : N/A")
        print(f"Reason            : {estimate.reason}")
        return

    print(f"Estimated bits    : {estimate.estimated_payload_bits:,.2f}")
    print(f"Changed samples   : {estimate.expected_changed_samples:,.2f}")


def _require_avi_path(file_path: str | Path) -> Path:
    """Resolve and validate a path used by on-demand AVI analysis."""
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() != ".avi":
        raise ValueError(f"Expected an .avi file: {path}")
    return path


def analyze_avi_frame_chi_square(
    file_path: str | Path,
    frame_index: int,
    parameters: AnalysisParameters | None = None,
) -> AVIFrameChiSquareDetailResult:
    """Public entry point for on-demand Chi-square of one AVI frame."""
    path = _require_avi_path(file_path)
    return AVIHandler(path).analyze_frame_chi_square(frame_index, parameters)


def analyze_avi_frame_rs(
    file_path: str | Path,
    frame_index: int,
    parameters: AnalysisParameters | None = None,
) -> AVIFrameRSDetailResult:
    """Public entry point for on-demand RS analysis of one AVI frame."""
    path = _require_avi_path(file_path)
    return AVIHandler(path).analyze_frame_rs(frame_index, parameters)


def analyze_avi_frame_spa(
    file_path: str | Path,
    frame_index: int,
    parameters: AnalysisParameters | None = None,
) -> AVIFrameSPADetailResult:
    """Public entry point for on-demand SPA of one AVI frame."""
    path = _require_avi_path(file_path)
    return AVIHandler(path).analyze_frame_spa(frame_index, parameters)


def main() -> None:
    """Run the analyzer from the command line."""
    parser = argparse.ArgumentParser(
        description="Analyze a supported WAV or AVI file."
    )
    parser.add_argument("file_path", help="Path to the file to analyze")
    parser.add_argument(
        "--min-expected",
        type=float,
        default=5.0,
        help="Minimum expected count for each Chi-square pair (default: 5.0)",
    )
    args = parser.parse_args()

    try:
        result = analyze(
            args.file_path,
            AnalysisParameters(min_expected=args.min_expected),
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    print_analysis_result(result)


if __name__ == "__main__":
    main()
