"""
Entrypoint that runs inside the sieng2-analyzer Docker image (see docker/Dockerfile).
Takes a file path, runs the normal analyze(), and prints the result as JSON on
stdout - this is what docker_bridge.py (the host-side caller) parses back.

analyze() and its dependencies (exiftool_wrapper, dispatcher, format handlers)
print debug info to stdout - that has to be kept off real stdout or it would
corrupt the JSON, so it's captured and discarded while analyze() runs.
"""
import sys
import json
import io
import contextlib

from src.core.analyzer.handle import analyze


def main():
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: python -m src.core.analyzer.cli <file_path>"}))
        sys.exit(1)

    file_path = sys.argv[1]

    debug_output = io.StringIO()
    with contextlib.redirect_stdout(debug_output):
        result = analyze(file_path)

    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
