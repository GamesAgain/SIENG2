from dataclasses import dataclass
from math import isfinite


def _validate_integer(name: str, value: int, minimum: int, maximum: int | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer.")
    if value < minimum or (maximum is not None and value > maximum):
        if maximum is None:
            raise ValueError(f"{name} must be at least {minimum}.")
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")

@dataclass(frozen=True)
class AnalysisParameters:
    min_expected: float = 5.0
    prefix_step: int = 10
    segment_percent: int = 10
    segment_step: int = 5
    spa_j: int = 30
    spa_min_pairs: int = 100

    def validate(self) -> None:
        try:
            valid_min_expected = isfinite(self.min_expected)
        except TypeError as exc:
            raise ValueError(
                "Chi-square min expected must be at least 5."
            ) from exc
        if not valid_min_expected or self.min_expected < 5:
            raise ValueError(
                "Chi-square min expected must be at least 5."
            )

        _validate_integer("Prefix step", self.prefix_step, 1, 100)
        _validate_integer("Segment length", self.segment_percent, 1, 100)
        _validate_integer("Segment step", self.segment_step, 1, 100)

        if self.segment_step > self.segment_percent:
            raise ValueError(
                "Segment step must not exceed segment length."
            )

        _validate_integer("SPA pooling j", self.spa_j, 0, 126)
        _validate_integer("SPA min pairs", self.spa_min_pairs, 1)
