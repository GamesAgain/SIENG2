"""
Drop-in replacement for src.core.analyzer.handle.analyze() that runs the real
analysis inside the sieng2-analyzer Docker container instead of importing it
directly - handle.py depends on binwalk/exiftool, which don't run natively on
Windows. Same signature, same return shape; only the caller (GUI pages) needs
to import from here instead.

Runs `docker run` on demand, once per call - no server/container to keep
running, just Docker Desktop itself needs to be up in the background.
"""
import subprocess
import json
from pathlib import Path

IMAGE_NAME = "sieng2-analyzer"


def analyze(file_path: str) -> dict:
    path = Path(file_path).resolve()
    if not path.is_file():
        return {"error": f"File not found: {file_path}"}

    mount_dir = path.parent
    container_path = f"/data/{path.name}"

    try:
        process = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{mount_dir}:/data:ro",
                IMAGE_NAME,
                container_path,
            ],
            capture_output=True, text=True, timeout=120,
        )
    except FileNotFoundError:
        return {"error": "Docker not found. Please install Docker Desktop and make sure it's running."}
    except subprocess.TimeoutExpired:
        return {"error": "Analysis timed out after 120 seconds."}

    if process.returncode != 0:
        detail = (process.stderr or process.stdout).strip()
        if "daemon is running" in detail or "pipe/dockerDesktop" in detail:
            return {"error": "Docker Desktop doesn't seem to be running. Please start it and try again."}
        return {"error": f"Analyzer container failed: {detail}"}

    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError:
        return {"error": f"Analyzer container returned invalid JSON: {process.stdout[:500]!r}"}
