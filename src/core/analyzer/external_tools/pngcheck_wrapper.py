"""Wrapper around `pngcheck` (installed in the Docker image) - the reference PNG validator.

Our own png_integrity() checks CRCs and finds the post-IEND overlay; pngcheck adds the structural
validation those don't cover: malformed/illegal chunks, wrong chunk ordering, truncated IDAT,
out-of-range IHDR values, etc. We keep only the findings our own checks don't already report, so
pngcheck is a strengthening cross-check rather than a source of duplicate anomalies.
"""
import subprocess

_TIMEOUT = 60
# categories our own analysis already surfaces (skip to avoid double-reporting)
_ALREADY_COVERED = ("crc", "additional data after iend", "unknown", "private, ancillary")
_MEANINGFUL = ("error", "invalid", "corrupt", "illegal", "truncat", "out of range",
               "incorrect", "wrong", "missing", "bad ")


def check(file_path: str) -> dict:
    """Return {'ok': bool|None, 'messages': [str], 'error': str|None}. `messages` are the
    structural problems pngcheck found that our own checks don't already report."""
    try:
        proc = subprocess.run(["pngcheck", "-v", file_path], capture_output=True, text=True, timeout=_TIMEOUT)
    except FileNotFoundError:
        return {"ok": None, "messages": [], "error": "pngcheck is not installed in this environment."}
    except subprocess.TimeoutExpired:
        return {"ok": None, "messages": [], "error": "pngcheck timed out."}

    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    messages = []
    for line in out.splitlines():
        s = line.strip()
        low = s.lower()
        if "no error" in low:  # pngcheck's success line ("No errors detected in ...")
            continue
        if not any(k in low for k in _MEANINGFUL):
            continue
        if any(k in low for k in _ALREADY_COVERED):
            continue
        messages.append(s)

    return {"ok": proc.returncode == 0, "messages": messages, "error": None}
