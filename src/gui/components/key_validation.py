from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtWidgets import QLabel

from src.core.crypto.asym_encrypt import load_private_key, load_public_key


@dataclass(frozen=True)
class KeyValidationResult:
    state: str
    message: str
    detail: str = ""

    @property
    def valid(self) -> bool:
        return self.state == "valid"

    @property
    def accepted(self) -> bool:
        return self.state in {"valid", "pending"}


def detect_key_encoding(file_path: str) -> str:
    key_data = Path(file_path).read_bytes()
    stripped_data = key_data.lstrip()

    if stripped_data.startswith(b"-----BEGIN"):
        return "PEM"
    if stripped_data.startswith(b"ssh-"):
        return "OpenSSH"
    return "DER"


def inspect_public_key(file_path: str) -> KeyValidationResult:
    try:
        public_key = load_public_key(file_path)
        encoding = detect_key_encoding(file_path)
    except (OSError, TypeError, ValueError) as error:
        return KeyValidationResult("error", str(error))

    detail = f"RSA-{public_key.key_size} • Public Key • {encoding}"
    return KeyValidationResult("valid", "Valid RSA public key", detail)


def inspect_private_key(
    file_path: str,
    password: str | bytes | None = None,
) -> KeyValidationResult:
    try:
        private_key = load_private_key(file_path, password)
        encoding = detect_key_encoding(file_path)
    except (OSError, TypeError, ValueError) as error:
        message = str(error)
        if password is None and "password is required" in message.lower():
            encoding = detect_key_encoding(file_path)
            return KeyValidationResult(
                "pending",
                "Private key password required",
                f"RSA Private Key • {encoding} • Encrypted",
            )
        return KeyValidationResult("error", message)

    protection = "Encrypted" if password is not None else "Unencrypted"
    detail = f"RSA-{private_key.key_size} • Private Key • {encoding} • {protection}"
    return KeyValidationResult("valid", "Valid RSA private key", detail)


class KeyValidationLabel(QLabel):
    def __init__(self):
        super().__init__()
        self.setObjectName("keyValidationLabel")
        self.setWordWrap(True)
        self.clear_result()

    def set_result(self, result: KeyValidationResult) -> None:
        self.setProperty("keyState", result.state)
        self.setText(result.detail or result.message)
        self.setToolTip(result.message)
        self.setVisible(True)
        self._refresh_style()

    def clear_result(self) -> None:
        self.setProperty("keyState", "none")
        self.clear()
        self.setToolTip("")
        self.setVisible(False)
        self._refresh_style()

    def _refresh_style(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)
