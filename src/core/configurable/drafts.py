"""Plain data of the technique inputs and of a pipeline step (no GUI code, so core and GUI can both use it)."""
from dataclasses import dataclass, field

from src.core.configurable.step_output import FileSource

# Display names of the techniques (the GUI reuses them for its cards)
TECHNIQUE_LABELS = {"lsbpp": "LSB++", "locomotive": "Locomotive", "metadata": "Metadata"}

@dataclass
class LSBInputsDraft:
    "LSB++ inputs draft for saving/loading state of the form."
    cover: FileSource | None = None  # a file path (Manual) or an earlier step's output (Previous Output)
    payload_text: str = ""
    encryption_enabled: bool = True
    encryption_mode: str = "password"
    password: str = field(default="", repr=False) # ไม่แสดง password ตอน print/debug object
    public_key_path: str | None = None

    def encryption_args(self) -> tuple[str | None, str | None]:
        """Return (password, public_key_path); only the active mode is non-None."""
        if not self.encryption_enabled:
            return None, None
        if self.encryption_mode == "password":
            return self.password, None
        if self.encryption_mode == "public_key":
            return None, self.public_key_path
        raise ValueError("Unsupported encryption mode.")

@dataclass
class LocomotiveInputsDraft:
    "Locomotive inputs draft; payload_mode selects which payload field is used."
    covers: list[FileSource] = field(default_factory=list)  # all paths (Manual) or all step outputs (Previous Output)
    payload_mode: str = "files"  # "files" | "text"
    payload_files: list[FileSource] = field(default_factory=list)  # all paths (Manual) or all step outputs (Previous Output)
    payload_text: str = ""
    encryption_enabled: bool = True
    encryption_mode: str = "password"
    password: str = field(default="", repr=False) # ไม่แสดง password ตอน print/debug object
    public_key_path: str | None = None

    def encryption_args(self) -> tuple[str | None, str | None]:
        """Return (password, public_key_path); only the active mode is non-None."""
        if not self.encryption_enabled:
            return None, None
        if self.encryption_mode == "password":
            return self.password, None
        if self.encryption_mode == "public_key":
            return None, self.public_key_path
        raise ValueError("Unsupported encryption mode.")

@dataclass
class MetadataInputsDraft:
    """
    Metadata inputs. Saving the step only keeps these values; the file is written when the pipeline runs
    (the hidden-field list is worked out then, against the real target file).
    """
    target: FileSource | None = None  # PNG/MP3 path (Manual) or a PNG output of an earlier step (Previous Output)
    entries: dict = field(default_factory=dict)  # every value the file should have: PNG {keyword: text}, MP3 {key: MP3Field}
    payload_keys: list[str] = field(default_factory=list)  # keys added/modified when the step was saved (card display only)
    removed_frames: list[str] = field(default_factory=list)  # MP3 frames ID3v2.3 cannot keep: removed when the pipeline runs

@dataclass
class StepDraft:
    "Saved configuration of one pipeline step (shared by the page and the runner)."
    key: str
    technique: str
    description: str
    guidenote: str = ""
    technique_inputs: LSBInputsDraft | LocomotiveInputsDraft | MetadataInputsDraft | None = None
