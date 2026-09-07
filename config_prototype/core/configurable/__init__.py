"""Domain model and execution boundary for configurable pipelines."""

from .step_output import FileSource, StepOutput, StepOutputInfo

__all__ = ["FileSource", "StepOutput", "StepOutputInfo"]
