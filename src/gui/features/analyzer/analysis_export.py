"""Export a completed result using the interactive mockup's JSON structure."""

import json
from dataclasses import asdict
from PyQt6.QtCore import QIODevice, QSaveFile


def export_analysis(result, destination) -> None:
    """Write the result snapshot atomically, preserving raw precision and nulls."""
    parameters = asdict(result.parameters)
    parameters["min_pairs"] = parameters.pop("spa_min_pairs")
    parameters["rs_mask"] = [0, 1, 1, 0]
    snapshot = asdict(result)
    document = {
        "schema_version": 2,
        "mode": "python",
        "file": {**result.image_info, "path": result.file_path,
                 "size": result.file_fingerprint.size,
                 "sha256": result.file_fingerprint.sha256,
                 "modified_ns": result.file_fingerprint.modified_ns},
        "parameters": parameters,
        "results": {name: snapshot[name] for name in ("chi_square", "rs", "spa")},
    }
    data = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    output = QSaveFile(str(destination))
    if not output.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(output.errorString())
    if output.write(data) != len(data):
        output.cancelWriting()
        raise OSError(output.errorString())
    if not output.commit():
        raise OSError(output.errorString())
