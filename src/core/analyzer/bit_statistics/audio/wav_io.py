"""Read supported integer PCM WAV samples without changing their LSBs."""

from pathlib import Path
import wave

import numpy as np


def read_wav(path: str):
    try:
        with wave.open(path, "rb") as source:
            if source.getcomptype() != "NONE":
                raise ValueError("WAV Bit Statistics supports uncompressed PCM only.")
            channels = source.getnchannels()
            width = source.getsampwidth()
            rate = source.getframerate()
            count = source.getnframes()
            if channels not in (1, 2) or width not in (1, 2) or rate <= 0:
                raise ValueError("WAV Bit Statistics supports 8/16-bit mono or stereo PCM only.")
            raw = source.readframes(count)
    except (EOFError, wave.Error) as exc:
        raise ValueError(f"Invalid or unsupported PCM WAV: {exc}") from exc

    expected = count * channels * width
    if len(raw) != expected:
        raise ValueError("WAV data is truncated.")
    dtype = np.uint8 if width == 1 else np.dtype("<i2")
    samples = np.frombuffer(raw, dtype=dtype).reshape(count, channels)
    info = {
        "name": Path(path).name, "format": "WAV", "encoding": "PCM",
        "sample_rate": rate, "bits_per_sample": width * 8,
        "channel_count": channels, "channel_names": ["Mono"] if channels == 1 else ["Left", "Right"],
        "samples_per_channel": count, "duration_seconds": count / rate,
    }
    return info, samples
