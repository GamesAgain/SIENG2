"""Container entry point: JSON on stdout, diagnostics on stderr."""

import argparse
import json
import sys

from .service import inspect_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["inspect"])
    parser.add_argument("file_path")
    args = parser.parse_args()
    try:
        result = inspect_file(args.file_path)
    except Exception as exc:
        print(f"Inspection failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
