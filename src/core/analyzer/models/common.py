"""Small result models shared by file-format handlers."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FileInfo:
    path: str
    name: str
    extension: str
    size: int
    format: str


@dataclass(frozen=True)
class BitStatisticsResult:
    chi_square: Any | None = None
    rs: Any | None = None
    spa: Any | None = None


@dataclass(frozen=True)
class RSMeasurement:
    """RS group statistics and payload estimate for one analyzed range."""

    rs: Any
    payload: Any
