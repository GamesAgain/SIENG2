import os
import re
import subprocess
from typing import Dict, Any

_CARVE_TIMEOUT = 300
_SCAN_TIMEOUT = 120  # binwalk is the slowest tool and parses untrusted input - bound it
_ENTROPY_LINE = re.compile(r"^\s*(\d+)\s+0x[0-9A-Fa-f]+\s+(Rising|Falling) entropy edge \(([\d.]+)\)")

def run_binwalk(file_path: str) -> Dict[str, Any]:

    results = {
        "signatures": [],
        "error": None
    }

    try:
        process = subprocess.run(['binwalk', file_path], capture_output=True, text=True,
                                 timeout=_SCAN_TIMEOUT)

        if process.returncode != 0 and not process.stdout:
            results["error"] = f"Binwalk error: {process.stderr}"
            return results

        for line in process.stdout.split('\n'):
            line = line.strip()
            if line and line[0].isdigit():
                parts = line.split(maxsplit=2)
                if len(parts) >= 3:
                    offset = int(parts[0])
                    description = parts[2]
                    results["signatures"].append({
                        "offset": offset,
                        "description": description
                    })
    except subprocess.TimeoutExpired:
        results["error"] = "Binwalk scan timed out."
    except Exception as e:
        results["error"] = f"Failed to run binwalk CLI: {str(e)}"

    return results


def entropy_scan(file_path: str, high: float = 0.95, dip: float = 0.35,
                 edge_floor: int = 2048) -> Dict[str, Any]:
    """Run binwalk's entropy analysis and flag a genuine low->high transition into random data.

    An embedded encrypted/compressed blob shows up as entropy climbing to ~1.0 *right after* a
    clearly-structured (low-entropy) region - data that carries no file magic (binwalk's signature
    scan misses it) and no plaintext (strings misses it). We require a preceding falling edge below
    `dip`, so a uniformly-high-entropy carrier (a JPEG/PNG stream, or MJPG video whose every frame
    is compressed) never trips it - those never drop that low between their many rising edges.
    """
    try:
        proc = subprocess.run(["binwalk", "-E", "--nplot", file_path],
                              capture_output=True, text=True, timeout=_CARVE_TIMEOUT)
    except FileNotFoundError:
        return {"edges": [], "high_entropy_offsets": [], "error": "binwalk is not installed."}
    except subprocess.TimeoutExpired:
        return {"edges": [], "high_entropy_offsets": [], "error": "Entropy scan timed out."}

    edges, hot, low_before = [], [], False
    for line in proc.stdout.splitlines():
        m = _ENTROPY_LINE.match(line)
        if not m:
            continue
        offset, direction, value = int(m.group(1)), m.group(2).lower(), float(m.group(3))
        edges.append({"offset": offset, "direction": direction, "entropy": value})
        if direction == "falling":
            low_before = value <= dip  # remember we just dropped into structured/low-entropy data
        elif direction == "rising":
            if value >= high and offset > edge_floor and low_before:
                hot.append(offset)
            low_before = False
    return {"edges": edges, "high_entropy_offsets": hot, "error": None}


def carve(file_path: str, out_dir: str, max_files: int = 50,
          max_size: int = 50 * 1024 * 1024) -> Dict[str, Any]:
    """Extract the files binwalk finds embedded in `file_path` into `out_dir` (`binwalk -e`).

    Where scan() only reports that something is embedded, this pulls the bytes out. Bounded with
    -n/-j (and no -M recursion) so a crafted carrier can't fan out into a decompression bomb.
    """
    # --run-as=root: binwalk refuses to run its third-party extractors as root without this. We're
    # inside a disposable, network-less analysis container, which is exactly the isolation that
    # guard is asking for, so it's safe to acknowledge here rather than drop privileges.
    cmd = ["binwalk", "-e", "--run-as=root", "-C", out_dir,
           "-n", str(max_files), "-j", str(max_size), file_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_CARVE_TIMEOUT)
    except FileNotFoundError:
        return {"extracted": [], "error": "binwalk is not installed in this environment."}
    except subprocess.TimeoutExpired:
        return {"extracted": [], "error": "Carving timed out."}

    extracted = []
    for root, _dirs, names in os.walk(out_dir):
        for name in names:
            full = os.path.join(root, name)
            try:
                extracted.append({"name": os.path.relpath(full, out_dir),
                                  "size": os.path.getsize(full)})
            except OSError:
                continue
    extracted.sort(key=lambda f: f["name"])

    error = None
    if not extracted:
        # binwalk exits 0 with nothing to do when no signature is extractable
        error = (proc.stderr or "").strip() or None
    return {"extracted": extracted, "error": error}
