"""
Entrypoint that runs inside the sieng2-analyzer Docker image (see docker/Dockerfile).
Dispatches a subcommand and prints its result as JSON on stdout - this is what
docker_bridge.py (the host-side caller) parses back.

Subcommands:
  analyze <file>                       full file analysis (metadata/structure/statistical)
  zsteg-scan <file> [opts]             enumerate LSB hiding combinations (PNG/BMP)
  zsteg-extract <file> <combination>   pull raw bytes out of one combination

analyze() and its dependencies print debug info to stdout - that has to be kept
off real stdout or it would corrupt the JSON, so it's captured while they run.
"""
import sys
import json
import argparse
import io
import contextlib


def _emit(result: dict):
    print(json.dumps(result, default=str))


def main():
    parser = argparse.ArgumentParser(prog="sieng2-analyzer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze")
    p_analyze.add_argument("file")

    p_scan = sub.add_parser("zsteg-scan")
    p_scan.add_argument("file")
    p_scan.add_argument("--all", action="store_true")
    p_scan.add_argument("--bits")
    p_scan.add_argument("--channels")
    p_scan.add_argument("--order")
    p_scan.add_argument("--bit-order", choices=["lsb", "msb"])
    p_scan.add_argument("--limit", type=int)

    p_extract = sub.add_parser("zsteg-extract")
    p_extract.add_argument("file")
    p_extract.add_argument("combination")

    p_strings = sub.add_parser("strings-scan")
    p_strings.add_argument("file")
    p_strings.add_argument("--min", type=int, default=6)
    p_strings.add_argument("--encoding", default="ascii",
                           choices=["ascii", "8bit", "utf16le", "utf16be"])

    p_carve = sub.add_parser("carve")
    p_carve.add_argument("file")
    p_carve.add_argument("--out", required=True)

    args = parser.parse_args()

    debug_output = io.StringIO()
    with contextlib.redirect_stdout(debug_output):
        if args.command == "analyze":
            from src.core.analyzer.handle import analyze
            result = analyze(args.file)
        elif args.command == "zsteg-scan":
            from src.core.analyzer.external_tools.zsteg_wrapper import scan
            result = scan(args.file, all_methods=args.all, bits=args.bits, channels=args.channels,
                          order=args.order, bit_order=args.bit_order, limit=args.limit)
        elif args.command == "zsteg-extract":
            from src.core.analyzer.external_tools.zsteg_wrapper import extract
            result = extract(args.file, args.combination)
        elif args.command == "strings-scan":
            from src.core.analyzer.external_tools.strings_wrapper import scan
            result = scan(args.file, min_len=args.min, encoding=args.encoding)
        elif args.command == "carve":
            from src.core.analyzer.external_tools.binwalk_wrapper import carve
            result = carve(args.file, args.out)

    _emit(result)


if __name__ == "__main__":
    main()
