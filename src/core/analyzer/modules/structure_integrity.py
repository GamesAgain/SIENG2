"""
Raw-byte structure integrity checks - the things a chunk-tree parser (hachoir)
can't reliably answer on its own:

  - content_end : the byte offset where the format's OWN structure says the file
                  should end. Anything past it is an appended overlay (the most
                  basic file-structure hiding technique). Computed from the
                  format's headers (PNG: after IEND / RIFF: declared size), NOT
                  from how many bytes the parser happened to consume - a parser
                  will silently swallow trailing bytes as "padding" and hide the
                  overlay (the bug this replaces).
  - PNG CRC     : every PNG chunk stores a CRC32 of its own type+data. If it
                  doesn't match, the chunk was edited by hand (not re-encoded) -
                  a near-zero-false-positive tampering signal (what pngcheck does).
  - RIFF JUNK   : JUNK/PAD chunks are spec padding, meant to be filler (zeros).
                  A JUNK chunk full of varied bytes is data hidden in padding.

Kept deliberately small and dependency-free; hachoir still produces the tree the
GUI displays, this only adds the integrity signals on top.
"""
import struct
import zlib

PNG_SIG = b"\x89PNG\r\n\x1a\n"
RIFF_PADDING_TAGS = {b"JUNK", b"PAD ", b"FLLR"}
JUNK_DISTINCT_BYTES_THRESHOLD = 16  # genuine padding uses 1-2 distinct values; hidden data uses many


def png_integrity(raw: bytes) -> dict:
    """Walk PNG chunks: verify each CRC32, find where IEND ends."""
    anomalies = []
    content_end = None

    if raw[:8] != PNG_SIG:
        return {"content_end": None, "anomalies": []}

    pos = 8
    while pos + 12 <= len(raw):
        length = struct.unpack(">I", raw[pos:pos + 4])[0]
        ctype = raw[pos + 4:pos + 8]
        if pos + 12 + length > len(raw):
            break  # truncated/corrupt chunk header, stop cleanly
        data = raw[pos + 8:pos + 8 + length]
        stored_crc = struct.unpack(">I", raw[pos + 8 + length:pos + 12 + length])[0]
        if (zlib.crc32(ctype + data) & 0xFFFFFFFF) != stored_crc:
            anomalies.append({
                "type": "crc_error",
                "detail": f"Chunk '{ctype.decode('latin1')}' at offset {pos} has a bad CRC32 "
                          f"(its data was edited without re-encoding)",
            })
        pos += 12 + length
        if ctype == b"IEND":
            content_end = pos
            break

    return {"content_end": content_end, "anomalies": anomalies}


def riff_integrity(raw: bytes) -> dict:
    """Use the RIFF header's declared size for content_end; scan JUNK/PAD chunks
    (including those nested inside LIST chunks, as AVI nests heavily)."""
    anomalies = []
    content_end = None

    if raw[:4] != b"RIFF" or len(raw) < 12:
        return {"content_end": None, "anomalies": []}

    declared = struct.unpack("<I", raw[4:8])[0]
    end = 8 + declared
    content_end = end if 0 < end <= len(raw) else None

    _scan_riff_chunks(raw, 12, min(end, len(raw)), anomalies)
    return {"content_end": content_end, "anomalies": anomalies}


def _scan_riff_chunks(raw: bytes, start: int, end: int, anomalies: list):
    pos = start
    while pos + 8 <= end:
        fourcc = raw[pos:pos + 4]
        size = struct.unpack("<I", raw[pos + 4:pos + 8])[0]
        payload = raw[pos + 8:pos + 8 + size]
        if pos + 8 + size > len(raw):
            break  # truncated chunk, stop cleanly

        if fourcc in RIFF_PADDING_TAGS:
            distinct = len(set(payload))
            if distinct > JUNK_DISTINCT_BYTES_THRESHOLD:
                nonzero = sum(1 for b in payload if b != 0)
                anomalies.append({
                    "type": "junk_stuffed",
                    "detail": f"'{fourcc.decode('latin1').strip()}' padding chunk ({size} bytes) holds varied "
                              f"data ({distinct} distinct byte values, {nonzero} non-zero) - padding should be filler",
                })
        elif fourcc == b"LIST" and size >= 4:
            _scan_riff_chunks(raw, pos + 12, pos + 8 + size, anomalies)  # recurse into the LIST body

        pos += 8 + size + (size & 1)  # chunks are word-aligned
