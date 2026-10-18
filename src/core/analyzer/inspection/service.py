"""Normalize ExifTool, Hachoir, Binwalk and container integrity checks."""

import base64
import json
import re
import struct
import subprocess
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _command(argv: list[str], timeout: int = 60) -> tuple[str, str | None]:
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, errors="replace", timeout=timeout
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return "", f"{argv[0]}: {exc}"
    if argv[0] == "pngcheck":
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return output, None if output.strip() else "pngcheck produced no output."
    if proc.returncode and not proc.stdout.strip():
        return "", f"{argv[0]}: {proc.stderr.strip()[:300] or 'failed'}"
    return proc.stdout, None


def _metadata(path: Path) -> dict:
    output, error = _command(
        ["exiftool", "-json", "-a", "-u", "-ee", "-G1", str(path)]
    )
    raw = {}
    if not error:
        try:
            records = json.loads(output)
            raw = records[0] if isinstance(records, list) and records else {}
            if not isinstance(raw, dict):
                raise ValueError("not an object")
        except (ValueError, TypeError) as exc:
            error = f"ExifTool returned invalid JSON: {exc}"
    time_anomalies, software_anomalies, text_anomalies = [], [], []
    if not error:
        def parse_date(value):
            try:
                value = str(value).strip()
                if re.search(r"[+-]\d{2}:?\d{2}$", value):
                    return datetime.strptime(value, "%Y:%m:%d %H:%M:%S%z")
                return datetime.strptime(value[:19], "%Y:%m:%d %H:%M:%S")
            except (TypeError, ValueError):
                return None

        created = next(
            (parse_date(value) for key, value in raw.items()
             if key.endswith("FileCreateDate")), None
        )
        modified = next(
            (parse_date(value) for key, value in raw.items()
             if key.endswith("FileModifyDate")), None
        )
        if created and modified and (created.tzinfo is None) == (modified.tzinfo is None) and modified < created:
            time_anomalies.append({"tag": "Timestamp", "message": "Modification time precedes creation time."})
        for key, value in raw.items():
            if key.endswith(("FileCreateDate", "FileModifyDate", "FileAccessDate")):
                date = parse_date(value)
                now = datetime.now(timezone.utc) if date and date.tzinfo else datetime.now()
                if date and date > now + timedelta(days=1):
                    time_anomalies.append({"tag": key, "message": "Timestamp is in the future."})
            if any(token in key.lower() for token in ("software", "creator", "producer", "tool")):
                if any(token in str(value).lower() for token in (
                    "steghide", "stegosuite", "opensteg", "silenteye", "deepsound", "outguess"
                )):
                    software_anomalies.append({"tag": key, "message": f"Steganography software marker: {value}"})
            if isinstance(value, str) and key not in ("SourceFile", "File:Directory"):
                if re.search(r"flag\{|ctf\{|-----BEGIN|PRIVATE KEY", value, re.I):
                    text_anomalies.append({"tag": key, "message": "Secret-marker pattern in metadata text."})
                if len(value) > 200:
                    text_anomalies.append({"tag": key, "message": f"Unusually long text ({len(value)} characters)."})
                if any((ord(char) < 32 and char not in "\t\r\n") or ord(char) == 127 for char in value):
                    text_anomalies.append({"tag": key, "message": "Non-printable control characters in metadata text."})
    return {
        "status": "error" if error else "ok", "error": error, "raw_data": raw,
        "time_anomalies": time_anomalies, "software_anomalies": software_anomalies,
        "text_anomalies": text_anomalies,
    }


def _hachoir(path: Path) -> dict:
    result = {"parsed_size_bytes": 0, "structure": [], "error": None}
    try:
        from hachoir.core.log import log
        from hachoir.parser import createParser

        log.use_print = False
        parser = createParser(str(path))
        if parser is None:
            raise ValueError("Hachoir does not support this file.")
        result["parsed_size_bytes"] = parser.size // 8
        count = [0]

        def walk(field, depth=0):
            count[0] += 1
            node = {
                "name": str(field.name),
                "description": str(field.description or ""),
                "size_bytes": field.size // 8,
            }
            if field.is_field_set and depth < 5 and count[0] < 3000:
                node["sub_chunks"] = [walk(child, depth + 1) for child in field]
            elif not field.is_field_set:
                node["value"] = str(field.display or "")[:500]
            return node

        for field in parser:
            if count[0] >= 3000:
                break
            result["structure"].append(walk(field))
    except Exception as exc:
        result["error"] = f"Hachoir: {exc}"
    return result


def _binwalk(path: Path) -> dict:
    output, error = _command(["binwalk", str(path)], timeout=120)
    signatures = []
    for line in output.splitlines():
        match = re.match(r"^\s*(\d+)\s+0x[0-9a-fA-F]+\s+(.+)$", line)
        if match:
            signatures.append({"offset": int(match.group(1)), "description": match.group(2)})
    return {"signatures": signatures, "error": error}


def _mediainfo(path: Path) -> dict:
    output, error = _command(["mediainfo", "--Output=JSON", str(path)])
    if error:
        return {"error": error}
    try:
        tracks = json.loads(output).get("media", {}).get("track", [])
    except (ValueError, AttributeError):
        return {"error": "MediaInfo returned invalid JSON."}
    return {"tracks": tracks, "error": None}


def _png_integrity(path: Path) -> dict:
    anomalies, end = [], None
    with path.open("rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            return {"content_end": None, "anomalies": [{"type": "invalid_header", "detail": "Invalid PNG signature."}]}
        while stream.tell() + 12 <= path.stat().st_size:
            offset = stream.tell()
            length, kind = struct.unpack(">I4s", stream.read(8))
            if offset + 12 + length > path.stat().st_size:
                anomalies.append({"type": "truncated_chunk", "detail": f"Truncated PNG chunk at {offset}."})
                break
            crc, remaining = zlib.crc32(kind), length
            while remaining:
                block = stream.read(min(remaining, 1024 * 1024))
                crc, remaining = zlib.crc32(block, crc), remaining - len(block)
            if crc & 0xffffffff != struct.unpack(">I", stream.read(4))[0]:
                anomalies.append({"type": "crc_error", "detail": f"Bad CRC in {kind.decode('latin1')} at {offset}."})
            if kind == b"IEND":
                end = stream.tell()
                break
    if end is None:
        anomalies.append({"type": "missing_iend", "detail": "PNG IEND chunk was not found."})
    return {"content_end": end, "anomalies": anomalies}


def _riff_integrity(path: Path) -> dict:
    size, anomalies = path.stat().st_size, []
    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) < 12 or header[:4] != b"RIFF":
            return {"content_end": None, "anomalies": [{"type": "invalid_header", "detail": "Invalid RIFF header."}]}
        declared = struct.unpack("<I", header[4:8])[0] + 8
        if declared > size:
            anomalies.append({"type": "truncated_riff", "detail": "RIFF declared size exceeds file size."})
        end = min(declared, size)
        if header[8:12] == b"AVI " and end < size:
            stream.seek(end)
            while stream.tell() + 12 <= size:
                start, head = stream.tell(), stream.read(12)
                if head[:4] != b"RIFF" or head[8:12] != b"AVIX":
                    break
                next_end = start + 8 + struct.unpack("<I", head[4:8])[0]
                if next_end > size or next_end <= start:
                    break
                end = next_end
                stream.seek(next_end)

        def scan(start, stop, depth=0):
            if depth > 8:
                return
            offset = start
            while offset + 8 <= stop:
                stream.seek(offset)
                kind, length = struct.unpack("<4sI", stream.read(8))
                chunk_end = offset + 8 + length
                if chunk_end > stop:
                    anomalies.append({"type": "truncated_chunk", "detail": f"RIFF chunk at {offset} exceeds its parent."})
                    break
                if kind in (b"JUNK", b"PAD ", b"FLLR") and length:
                    if len(set(stream.read(min(length, 4096)))) > 16:
                        anomalies.append({"type": "junk_stuffed", "detail": f"Varied data in {kind.decode('latin1').strip()} at {offset}."})
                elif kind == b"LIST" and length >= 4:
                    scan(offset + 12, chunk_end, depth + 1)
                offset = chunk_end + (length & 1)
        scan(12, min(declared, size))
    return {"content_end": end, "anomalies": anomalies}


def inspect_file(file_path: str) -> dict:
    path = Path(file_path).resolve(strict=True)
    suffix = path.suffix.lower()
    if suffix not in (".png", ".wav", ".avi"):
        raise ValueError("Only PNG, WAV and AVI are supported.")
    size = path.stat().st_size
    with ThreadPoolExecutor(max_workers=4) as pool:
        metadata_job = pool.submit(_metadata, path)
        tree_job = pool.submit(_hachoir, path)
        signatures_job = pool.submit(_binwalk, path)
        validation_job = (
            pool.submit(_command, ["pngcheck", "-v", str(path)])
            if suffix == ".png" else pool.submit(_mediainfo, path)
        )
        integrity = _png_integrity(path) if suffix == ".png" else _riff_integrity(path)
        metadata, tree = metadata_job.result(), tree_job.result()
        signatures, validation = signatures_job.result(), validation_job.result()
    end = integrity["content_end"]
    overlay = {"exists": end is not None and size > end, "offset": end,
               "size": size - end if end is not None and size > end else 0}
    if overlay["exists"]:
        with path.open("rb") as stream:
            stream.seek(end)
            overlay["preview_b64"] = base64.b64encode(stream.read(512)).decode("ascii")
    findings = list(integrity["anomalies"])
    if overlay["exists"]:
        findings.append({"type": "overlay", "detail": f"{overlay['size']} bytes after declared file content."})
    if suffix == ".png":
        output, error = validation
        pngcheck = {"output": output[-4000:], "error": error}
        for line in output.splitlines():
            lowered = line.lower()
            if "no error" in lowered or any(token in lowered for token in ("crc", "additional data after iend")):
                continue
            if any(token in lowered for token in ("error", "invalid", "corrupt", "illegal", "truncat", "missing")):
                findings.append({"type": "pngcheck", "detail": line.strip()[:300]})
    else:
        pngcheck = None
    media = validation if suffix != ".png" else None
    if media and not media.get("error"):
        tracks = media.get("tracks", [])
        general = next((track for track in tracks if track.get("@type") == "General"), {})
        try:
            reported = int(general.get("FileSize", 0))
            streams = sum(int(track.get("StreamSize", 0)) for track in tracks
                          if track.get("@type") != "General" and str(track.get("StreamSize", "")).isdigit())
        except (TypeError, ValueError):
            reported, streams = 0, 0
        gap = reported - streams - overlay["size"] if streams else 0
        if gap > max(16384, int(reported * 0.10)):
            findings.append({"type": "stream_gap", "detail": f"{gap} bytes are not accounted for by media streams."})
    errors = [value for value in (
        tree["error"], signatures["error"], pngcheck.get("error") if pngcheck else None,
        media.get("error") if media else None,
    ) if value]
    structure = {
        "status": "partial" if errors else "ok", "errors": errors,
        "hachoir_raw": tree, "binwalk_raw": signatures,
        "overlay_analysis": overlay, "integrity_anomalies": findings,
        "suspicious_count": len(findings), "pngcheck_raw": pngcheck,
        "mediainfo_raw": media,
    }
    return {"format": suffix[1:].upper(), "file_size": size,
            "structure_analysis": structure, "metadata_analysis": metadata}
