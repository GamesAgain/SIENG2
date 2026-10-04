"""Write and verify PNG metadata before replacing the destination."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from src.core.stego.metadata_handlers.png_handler import MetadataPNGHandler
from src.gui.features.embed.forms.metadata.file_info import get_png_file_info


def save_png_metadata(source: str, destination: str, entries: dict[str, str], progress_callback=None) -> str:
    def report(percent: int, message: str) -> None:
        if progress_callback:
            progress_callback(percent, message)

    handler = MetadataPNGHandler()
    target = Path(destination)
    report(10, "Writing PNG metadata…")
    # Stage on the destination filesystem so replace is atomic, including Save As
    # onto the source. An unsuccessful write/verification leaves it untouched.
    with TemporaryDirectory(prefix=".sieng-metadata-", dir=target.parent) as directory:
        staged = Path(directory) / "metadata.png"
        handler.embed_metadata(source, dict(entries), save_path=str(staged),
                               create_backup=False, merge_existing=False)
        report(70, "Verifying saved metadata…")
        get_png_file_info(str(staged))
        if handler.read_itxt_chunk(str(staged)) != entries:
            raise ValueError("Saved PNG metadata does not match the form inputs.")
        os.replace(staged, target)
    report(100, "PNG metadata saved and verified.")
    return str(target)
