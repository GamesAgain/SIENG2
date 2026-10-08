"""Plain data of the technique inputs and of a pipeline step (no GUI code, so core and GUI can both use it)."""
from dataclasses import dataclass, field

# Display names of the techniques (the GUI reuses them for its cards)
TECHNIQUE_LABELS = {"lsbpp": "LSB++", "locomotive": "Locomotive", "metadata": "Metadata"}

@dataclass
class LSBInputsDraft:
    "LSB++ inputs draft for saving/loading state of the form."
    cover: str | None = None
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
    covers: list[str] = field(default_factory=list)
    payload_mode: str = "files"  # "files" | "text"
    payload_files: list[str] = field(default_factory=list)
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
class StepDraft:
    "Saved configuration of one pipeline step (shared by the page and the runner)."
    key: str
    technique: str
    description: str
    guidenote: str = ""
    technique_inputs: LSBInputsDraft | LocomotiveInputsDraft | None = None
