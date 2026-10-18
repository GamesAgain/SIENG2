"""Top-level result envelope returned by file-format handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from src.core.analyzer.parameters import AnalysisParameters

from .common import BitStatisticsResult, FileInfo
from .wav import WAVMediaInfo

if TYPE_CHECKING:
    from .avi import AVIMediaInfo
    from .png import PNGMediaInfo


@dataclass(frozen=True)
class AnalysisResult:
    """Common result envelope returned by PNG, WAV and AVI handlers."""

    file: FileInfo
    media_info: PNGMediaInfo | WAVMediaInfo | AVIMediaInfo
    parameters: AnalysisParameters
    structure: dict[str, Any] | None
    metadata: dict[str, Any] | None
    bit_statistics: BitStatisticsResult

    @property
    def file_path(self) -> str:
        """Compatibility shortcut used by the previous GUI."""
        return self.file.path

    @property
    def image_info(self) -> dict[str, Any]:
        """Return the PNG shape expected by the previous GUI exporter."""
        if self.file.format != "PNG":
            return {}

        return {
            "name": self.file.name,
            "width": self.media_info.width,
            "height": self.media_info.height,
            "mode": self.media_info.mode,
            "format": self.file.format,
        }

    @property
    def audio_info(self) -> WAVMediaInfo | None:
        """Convenience access to WAV technical information."""
        if isinstance(self.media_info, WAVMediaInfo):
            return self.media_info
        return None

    @property
    def chi_square(self) -> Any | None:
        return self.bit_statistics.chi_square

    @property
    def rs(self) -> Any | None:
        return self.bit_statistics.rs

    @property
    def spa(self) -> Any | None:
        return self.bit_statistics.spa
