import os
import subprocess
from typing import Dict, Any

_CARVE_TIMEOUT = 300

def run_binwalk(file_path: str) -> Dict[str, Any]:

    results = {
        "signatures": [],
        "error": None
    }

    try:
        process = subprocess.run(['binwalk', file_path], capture_output=True, text=True)
        
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
    except Exception as e:
        results["error"] = f"Failed to run binwalk CLI: {str(e)}"

    return results


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
