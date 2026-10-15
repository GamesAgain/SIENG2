"""Host-side Docker bridge. The uploaded file is mounted read-only."""

import json
import subprocess
import time
import uuid
from pathlib import Path


IMAGE = "sieng2-analyzer"


def inspect(file_path: str, *, cancel_check=None, timeout: int = 180) -> dict:
    path = Path(file_path).resolve(strict=True)
    container = f"sieng2-inspect-{uuid.uuid4().hex[:12]}"
    command = [
        "docker", "run", "--rm", "--name", container, "--network", "none",
        "--memory", "1g", "--cpus", "2", "-v", f"{path}:/data/input{path.suffix.lower()}:ro",
        IMAGE, "inspect", f"/data/input{path.suffix.lower()}",
    ]
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise RuntimeError("Docker CLI was not found. Install Docker and build sieng2-analyzer.") from exc
    deadline = time.monotonic() + timeout
    try:
        while True:
            if cancel_check and cancel_check():
                raise InterruptedError("Inspection cancelled.")
            if time.monotonic() >= deadline:
                raise TimeoutError("Inspection exceeded its time limit.")
            try:
                stdout, stderr = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                continue
    except (InterruptedError, TimeoutError):
        # Only the uniquely named container created by this invocation is stopped.
        try:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()
        raise
    if process.returncode != 0:
        detail = stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"Docker inspection failed: {detail[:600] or 'unknown error'}")
    try:
        result = json.loads(stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Inspector returned invalid JSON.") from exc
    if not isinstance(result, dict) or "structure_analysis" not in result or "metadata_analysis" not in result:
        raise RuntimeError("Inspector returned an incomplete result.")
    return result

