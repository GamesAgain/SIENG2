"""References to files supplied manually or produced by an earlier step."""

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class StepOutput:
    """Identify one output from a pipeline step."""

    step_key: str
    output_key: str


@dataclass(frozen=True, slots=True)
class StepOutputInfo:
    """Describe a step output before the pipeline has run."""

    reference: StepOutput
    step_number: int
    technique: str
    media_type: str | None
    preview_path: str | None = None
    display_name: str | None = None


FileSource: TypeAlias = str | StepOutput
