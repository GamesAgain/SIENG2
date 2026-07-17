"""Wrapper around the GNU `strings` CLI (binutils, installed in the Docker image).

Extracts printable-character runs from a file's raw bytes - the classic first pass for spotting
plaintext hidden anywhere in a container (an appended overlay, a metadata/tEXt chunk, an embedded
file header, padding). Note: on compressed data (a normal JPEG/PNG pixel stream) most runs are
just coincidental printable bytes - that is inherent to `strings`, so a higher `min_len` and the
caller's interesting/search filters are what surface the meaningful text.
"""
import re
import subprocess

_TIMEOUT = 120
# `strings -t x` lines look like:  "  4a12 some readable text". Capture the hex offset and keep the
# rest verbatim (a string may contain spaces), separated by exactly one whitespace char.
_LINE = re.compile(r"^\s*([0-9a-fA-F]+)\s(.*)$")

# GNU `strings -e` encodings we expose.
_ENCODING_FLAG = {
    "ascii": "s",      # 7-bit single byte (the classic default)
    "8bit": "S",       # 8-bit single byte (covers UTF-8 / extended)
    "utf16le": "l",    # 16-bit little-endian (Windows wide text)
    "utf16be": "b",    # 16-bit big-endian
}


def scan(file_path: str, min_len: int = 6, encoding: str = "ascii", cap: int = 50000) -> dict:
    """Run GNU strings and return {'strings': [{offset, text}], 'encoding', 'truncated', 'error'}.
    `min_len` maps to `-n`; the whole file is scanned (`-a`); `cap` bounds the returned list."""
    flag = _ENCODING_FLAG.get(encoding, "s")
    cmd = ["strings", "-a", "-t", "x", "-n", str(max(1, min_len)), "-e", flag, file_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT)
    except FileNotFoundError:
        return {"strings": [], "error": "strings is not installed in this environment."}
    except subprocess.TimeoutExpired:
        return {"strings": [], "error": "strings scan timed out."}

    items = []
    truncated = False
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        items.append({"offset": int(m.group(1), 16), "text": m.group(2)})
        if len(items) >= cap:
            truncated = True
            break

    return {"strings": items, "encoding": encoding, "truncated": truncated, "error": None}
