from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from PyQt6.QtCore import QObject, QStandardPaths, pyqtSignal

from src.core.crypto.key_management import RSAKeyInfo


@dataclass(frozen=True)
class KeyRecord:
    id: str
    label: str
    path: str
    role: str
    key_size: int | None
    encoding: str
    container: str
    encrypted: bool
    fingerprint: str | None
    added_at: str

    @property
    def exists(self) -> bool:
        return Path(self.path).is_file()

    @classmethod
    def from_dict(cls, data: dict) -> "KeyRecord":
        return cls(**data)


class KeyRegistry(QObject):
    """Store key paths and metadata. Passwords and key bytes are never saved."""

    changed = pyqtSignal()

    def __init__(self, storage_path: str | Path | None = None):
        super().__init__()
        self.storage_path = Path(storage_path) if storage_path else self.default_storage_path()
        self._records: list[KeyRecord] = []
        self.load()

    @staticmethod
    def default_storage_path() -> Path:
        config_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppConfigLocation
        )
        return Path(config_dir) / "rsa_keys.json"

    def records(self, role: str | None = None) -> list[KeyRecord]:
        records = self._records
        if role is not None:
            records = [record for record in records if record.role == role]
        return sorted(records, key=lambda record: record.label.casefold())

    def get(self, record_id: str) -> KeyRecord | None:
        return next((record for record in self._records if record.id == record_id), None)

    def add(self, label: str, info: RSAKeyInfo) -> KeyRecord:
        clean_label = label.strip() or Path(info.path).stem
        resolved_path = str(Path(info.path).resolve())

        existing = next(
            (
                record for record in self._records
                if Path(record.path) == Path(resolved_path) and record.role == info.role
            ),
            None,
        )
        record = KeyRecord(
            id=existing.id if existing else uuid4().hex,
            label=clean_label,
            path=resolved_path,
            role=info.role,
            key_size=info.key_size,
            encoding=info.encoding,
            container=info.container,
            encrypted=info.encrypted,
            fingerprint=info.fingerprint,
            added_at=existing.added_at if existing else datetime.now(timezone.utc).isoformat(),
        )

        if existing:
            self._records[self._records.index(existing)] = record
        else:
            self._records.append(record)
        self.save()
        self.changed.emit()
        return record

    def remove(self, record_id: str) -> bool:
        original_count = len(self._records)
        self._records = [record for record in self._records if record.id != record_id]
        if len(self._records) == original_count:
            return False
        self.save()
        self.changed.emit()
        return True

    def rename(self, record_id: str, label: str) -> KeyRecord:
        current = self.get(record_id)
        if current is None:
            raise KeyError("Key reference was not found.")

        clean_label = label.strip()
        if not clean_label:
            raise ValueError("Display name cannot be empty.")

        updated = replace(current, label=clean_label)
        self._records[self._records.index(current)] = updated
        self.save()
        self.changed.emit()
        return updated

    def update_path(self, record_id: str, info: RSAKeyInfo) -> KeyRecord:
        current = self.get(record_id)
        if current is None:
            raise KeyError("Key reference was not found.")
        if current.role != info.role:
            raise ValueError(f"Choose an RSA {current.role} key file.")

        updated = KeyRecord(
            id=current.id,
            label=current.label,
            path=str(Path(info.path).resolve()),
            role=info.role,
            key_size=info.key_size,
            encoding=info.encoding,
            container=info.container,
            encrypted=info.encrypted,
            fingerprint=info.fingerprint,
            added_at=current.added_at,
        )
        self._records[self._records.index(current)] = updated
        self.save()
        self.changed.emit()
        return updated

    def load(self) -> None:
        if not self.storage_path.is_file():
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self._records = [KeyRecord.from_dict(item) for item in data.get("keys", [])]
        except (OSError, ValueError, TypeError):
            self._records = []

    def save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "keys": [asdict(record) for record in self._records]}
        temporary_path = self.storage_path.with_suffix(self.storage_path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary_path.replace(self.storage_path)
