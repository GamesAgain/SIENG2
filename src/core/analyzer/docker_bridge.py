"""
Host-side bridge to the analyzer backend, which runs inside the sieng2-analyzer
Docker container (its tools - binwalk/exiftool/zsteg - don't run natively on
Windows). Each function shells out to `docker run` on demand, once per call - no
server/container to keep running, just Docker Desktop up in the background.

  analyze(file)               -> full analysis (same shape handle.analyze() returns)
  zsteg_scan(file, **opts)    -> LSB combination enumeration (PNG/BMP)
  zsteg_extract(file, combo)  -> raw bytes of one combination, base64-encoded
"""
import subprocess
import json
from pathlib import Path

IMAGE_NAME = "sieng2-analyzer"
_TIMEOUT = 120


def _run(container_args: list, file_path: str, extra_mounts: list = None, timeout: int = None) -> dict:
    """Mount the file's directory read-only and run the analyzer CLI with the given args.
    `container_args` uses the placeholder {file} which is replaced by the in-container path.
    `extra_mounts` is [(host_dir, container_dir), ...] mounted writable - needed by commands
    that produce output (carving), since /data itself is read-only."""
    path = Path(file_path).resolve()
    if not path.is_file():
        return {"error": f"File not found: {file_path}"}

    container_path = f"/data/{path.name}"
    args = [a.replace("{file}", container_path) for a in container_args]

    mounts = ["-v", f"{path.parent}:/data:ro"]
    for host_dir, container_dir in (extra_mounts or []):
        mounts += ["-v", f"{host_dir}:{container_dir}"]

    try:
        process = subprocess.run(
            ["docker", "run", "--rm", *mounts, IMAGE_NAME, *args],
            capture_output=True, text=True, timeout=timeout or _TIMEOUT,
        )
    except FileNotFoundError:
        return {"error": "Docker not found. Please install Docker Desktop and make sure it's running."}
    except subprocess.TimeoutExpired:
        return {"error": "Analysis timed out."}

    if process.returncode != 0:
        detail = (process.stderr or process.stdout).strip()
        if "daemon is running" in detail or "pipe/dockerDesktop" in detail:
            return {"error": "Docker Desktop doesn't seem to be running. Please start it and try again."}
        return {"error": f"Analyzer container failed: {detail}"}

    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError:
        return {"error": f"Analyzer container returned invalid JSON: {process.stdout[:500]!r}"}


def analyze(file_path: str) -> dict:
    return _run(["analyze", "{file}"], file_path)


def zsteg_scan(file_path: str, all_methods: bool = False, bits: str = None, channels: str = None,
               order: str = None, bit_order: str = None, limit: int = None) -> dict:
    args = ["zsteg-scan", "{file}"]
    if all_methods:
        args.append("--all")
    if bits:
        args += ["--bits", bits]
    if channels:
        args += ["--channels", channels]
    if order:
        args += ["--order", order]
    if bit_order:
        args += ["--bit-order", bit_order]
    if limit is not None:
        args += ["--limit", str(limit)]
    return _run(args, file_path)


def zsteg_extract(file_path: str, combination: str) -> dict:
    return _run(["zsteg-extract", "{file}", combination], file_path)

def carve(file_path: str, out_dir: str) -> dict:
    """Extract embedded files into `out_dir` on the host (mounted writable at /out)."""
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    return _run(["carve", "{file}", "--out", "/out"], file_path,
                extra_mounts=[(str(out), "/out")], timeout=330)
