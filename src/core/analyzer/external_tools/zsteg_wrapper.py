"""
Wrapper around the zsteg CLI (Ruby gem, installed in the Docker image) - LSB
steganography detection/extraction for PNG and BMP.

zsteg systematically enumerates hiding hypotheses (bit plane b1..b8, channel
r/g/b/a/rgb/bgr, bit order lsb/msb, pixel scan order xy/yx) and reports any
combination whose extracted bitstream decodes to readable text or a known file
signature. This is EXTRACTION (pull the hidden bytes out), complementary to the
statistical detectors which only give a probabilistic "is something hidden" verdict.

Two entry points:
  scan(...)    -> enumerate combinations, return the list of findings
  extract(...) -> pull the raw bytes out of one chosen combination
"""
import re
import base64
import subprocess

# A zsteg result line looks like:  "b1,r,lsb,xy         .. text: "FLAG{...}""
# Empty combinations are overwritten with \r (progress style); real findings end with \n,
# so splitting the output on any CR/LF run isolates each finding on its own segment.
_FINDING_RE = re.compile(r'^(\S+)\s+\.\.\s+(text|file|data):\s*(.*)$')

_TIMEOUT = 120


def scan(file_path: str, all_methods: bool = False, bits: str = None, channels: str = None,
         order: str = None, bit_order: str = None, limit: int = None) -> dict:
    """Run a zsteg scan and return {'findings': [...], 'error': str|None}.
    Each finding: {'combination': 'b1,r,lsb,xy', 'type': 'text'|'file'|'data', 'content': str}."""
    cmd = ["zsteg"]
    if all_methods:
        cmd.append("-a")
    if bits:
        cmd += ["-b", bits]
    if channels:
        cmd += ["-c", channels]
    if order:
        cmd += ["-o", order]
    if bit_order == "lsb":
        cmd.append("--lsb")
    elif bit_order == "msb":
        cmd.append("--msb")
    if limit is not None:
        cmd += ["-l", str(limit)]
    cmd.append(file_path)

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT)
    except FileNotFoundError:
        return {"findings": [], "error": "zsteg is not installed in this environment."}
    except subprocess.TimeoutExpired:
        return {"findings": [], "error": "zsteg scan timed out."}

    stdout = proc.stdout.decode("utf-8", "replace")
    findings = []
    for segment in re.split(r"[\r\n]+", stdout):
        match = _FINDING_RE.match(segment.strip())
        if not match:
            continue
        combination, ftype, content = match.group(1), match.group(2), match.group(3).strip()
        if ftype == "text":
            content = content.strip('"')  # zsteg wraps text findings in quotes
        findings.append({"combination": combination, "type": ftype, "content": content})

    stderr = proc.stderr.decode("utf-8", "replace").strip()
    return {"findings": findings, "error": stderr or None}


def extract(file_path: str, combination: str, limit: int = 65536) -> dict:
    """Pull the raw bytes out of one combination (e.g. 'b1,r,lsb,xy') via `zsteg -E`.
    Returns the payload base64-encoded (may be binary), capped at `limit` bytes for preview."""
    try:
        proc = subprocess.run(["zsteg", "-E", combination, file_path], capture_output=True, timeout=_TIMEOUT)
    except FileNotFoundError:
        return {"error": "zsteg is not installed in this environment."}
    except subprocess.TimeoutExpired:
        return {"error": "zsteg extraction timed out."}

    data = proc.stdout
    return {
        "combination": combination,
        "total_bytes": len(data),
        "truncated": len(data) > limit,
        "data_b64": base64.b64encode(data[:limit]).decode("ascii"),
        "error": None,
    }
