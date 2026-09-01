"""Create technique input forms for the prototype step config shell."""

from PyQt6.QtWidgets import QWidget

from config_prototype.gui.components.technique_forms import LSBEmbedInputs
from src.gui.services.key_registry import KeyRegistry


def create_technique_form(
    technique: str,
    *,
    key_registry: KeyRegistry | None = None,
    parent: QWidget | None = None,
) -> QWidget | None:
    if technique == "lsbpp":
        return LSBEmbedInputs(
            key_registry=key_registry,
            parent=parent,
        )

    if technique in {"locomotive", "metadata"}:
        return None

    raise ValueError(f"Unsupported technique: {technique}")
