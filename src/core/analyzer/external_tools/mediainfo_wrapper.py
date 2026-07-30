"""Wrapper around `mediainfo --Output=JSON` (installed in the Docker image).

Gives the analyzer a real understanding of an audio/video container - stream count, codecs, and
each stream's byte size - which our RIFF checks (overlay + JUNK) don't provide. The steganography-
relevant signal is the gap between the file size and the bytes accounted for by the declared
streams: data living in the container but in no stream is space a payload can hide in that a
trailing-overlay or padding-chunk check may miss.
"""
import json
import subprocess

_TIMEOUT = 60


def probe(file_path: str) -> dict:
    """Return {'format', 'file_size', 'tracks': [{type, format, stream_size}], 'stream_size_total',
    'unaccounted_bytes', 'error'}."""
    try:
        proc = subprocess.run(["mediainfo", "--Output=JSON", file_path],
                              capture_output=True, text=True, timeout=_TIMEOUT)
    except FileNotFoundError:
        return {"error": "mediainfo is not installed in this environment."}
    except subprocess.TimeoutExpired:
        return {"error": "mediainfo timed out."}

    try:
        tracks = json.loads(proc.stdout).get("media", {}).get("track", [])
    except (json.JSONDecodeError, AttributeError):
        return {"error": "mediainfo returned no parseable output."}

    def _int(v):
        return int(v) if v is not None and str(v).isdigit() else 0

    general = next((t for t in tracks if t.get("@type") == "General"), {})
    file_size = _int(general.get("FileSize"))
    summary, stream_total = [], 0
    for t in tracks:
        if t.get("@type") == "General":
            continue
        size = _int(t.get("StreamSize"))
        stream_total += size
        summary.append({"type": t.get("@type"), "format": t.get("Format"), "stream_size": size})

    # bytes in the file that no declared stream accounts for (headers add a little, so only a
    # large gap is meaningful - the handler decides whether to raise it as an anomaly)
    unaccounted = file_size - stream_total if file_size and stream_total else 0
    return {
        "format": general.get("Format"),
        "file_size": file_size,
        "tracks": summary,
        "stream_size_total": stream_total,
        "unaccounted_bytes": unaccounted,
        "error": None,
    }
