"""Check MP3 tag boundaries and MPEG Layer III frame layout."""

from __future__ import annotations

from pathlib import Path


_MPEG1_BITRATES = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
_MPEG2_BITRATES = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
_SAMPLE_RATES = (44100, 48000, 32000)


def _frame_size(header: bytes) -> int | None:
    if len(header) != 4:
        return None
    bits = int.from_bytes(header, "big")
    if bits & 0xFFE00000 != 0xFFE00000:
        return None
    version = (bits >> 19) & 3
    layer = (bits >> 17) & 3
    bitrate_index = (bits >> 12) & 15
    sample_index = (bits >> 10) & 3
    if version == 1 or layer != 1 or not 1 <= bitrate_index <= 14 or sample_index == 3:
        return None
    bitrate = (_MPEG1_BITRATES if version == 3 else _MPEG2_BITRATES)[bitrate_index]
    sample_rate = _SAMPLE_RATES[sample_index] // (1 if version == 3 else 2 if version == 2 else 4)
    padding = (bits >> 9) & 1
    size = (144000 if version == 3 else 72000) * bitrate // sample_rate + padding
    return size if size >= 4 else None


def inspect_mp3_integrity(path: Path) -> dict:
    """Return the audio boundary, excluding valid trailing ID3v1/APEv2 tags."""
    size = path.stat().st_size
    anomalies = []
    with path.open("rb") as stream:
        head = stream.read(10)
        audio_start = 0
        if head[:3] == b"ID3":
            version = head[3] if len(head) >= 4 else 0
            size_bytes = head[6:10]
            if version not in (2, 3, 4) or len(size_bytes) != 4 or any(byte & 0x80 for byte in size_bytes):
                anomalies.append({"type": "invalid_id3", "detail": "Invalid ID3v2 header or size."})
                return {"content_end": None, "anomalies": anomalies}
            tag_size = sum(byte << shift for byte, shift in zip(size_bytes, (21, 14, 7, 0)))
            audio_start = 10 + tag_size + (10 if version == 4 and head[5] & 0x10 else 0)
            if audio_start > size:
                anomalies.append({"type": "truncated_id3", "detail": "ID3v2 declared size exceeds file size."})
                return {"content_end": None, "anomalies": anomalies}

        audio_stop = size
        if audio_stop >= 128:
            stream.seek(audio_stop - 128)
            if stream.read(3) == b"TAG":
                audio_stop -= 128
        if audio_stop >= 32:
            stream.seek(audio_stop - 32)
            footer = stream.read(32)
            if footer[:8] == b"APETAGEX":
                ape_size = int.from_bytes(footer[12:16], "little")
                if 32 <= ape_size <= audio_stop - audio_start:
                    audio_stop -= ape_size
                    if audio_stop >= 32:
                        stream.seek(audio_stop - 32)
                        if stream.read(8) == b"APETAGEX":
                            audio_stop -= 32
                else:
                    anomalies.append({"type": "invalid_ape", "detail": "APEv2 declared size is invalid."})

        position = audio_start
        frame_count = 0
        while position + 4 <= audio_stop:
            stream.seek(position)
            frame_size = _frame_size(stream.read(4))
            if frame_size is None:
                break
            if position + frame_size > audio_stop:
                anomalies.append({"type": "truncated_mpeg_frame", "detail": f"MPEG frame at offset {position} exceeds audio data."})
                break
            position += frame_size
            frame_count += 1

    if frame_count == 0:
        if not any(item["type"] == "truncated_mpeg_frame" for item in anomalies):
            anomalies.append({"type": "invalid_mpeg_audio", "detail": "No valid MPEG Layer III frame begins after the ID3v2 tag."})
        return {"content_end": None, "anomalies": anomalies, "mpeg_frame_count": 0}
    return {
        "content_end": position,
        "overlay_stop": audio_stop,
        "anomalies": anomalies,
        "mpeg_frame_count": frame_count,
    }
