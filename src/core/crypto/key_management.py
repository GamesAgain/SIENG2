"""RSA key metadata and key-pair management helpers."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.core.crypto.asym_encrypt import (
    generate_rsa_keypair,
    load_private_key,
    load_public_key,
    serialize_private_key,
    serialize_public_key,
)


@dataclass(frozen=True)
class RSAKeyInfo:
    path: str
    role: str
    key_size: int | None
    encoding: str
    container: str
    encrypted: bool
    fingerprint: str | None


def detect_key_format(path: str | Path) -> tuple[str, str, bool]:
    """Return encoding, container name, and encryption state."""
    data = Path(path).read_bytes().lstrip()
    if data.startswith(b"ssh-"):
        return "OpenSSH", "OpenSSH", False
    if not data.startswith(b"-----BEGIN"):
        return "DER", "DER", False

    first_line = data.splitlines()[0]
    formats = {
        b"-----BEGIN PUBLIC KEY-----": ("SPKI", False),
        b"-----BEGIN RSA PUBLIC KEY-----": ("PKCS#1", False),
        b"-----BEGIN PRIVATE KEY-----": ("PKCS#8", False),
        b"-----BEGIN ENCRYPTED PRIVATE KEY-----": ("PKCS#8", True),
        b"-----BEGIN RSA PRIVATE KEY-----": ("PKCS#1", pem_is_encrypted(data)),
    }
    container, encrypted = formats.get(first_line, ("PEM", False))
    return "PEM", container, encrypted


def pem_is_encrypted(data: bytes) -> bool:
    return b"Proc-Type: 4,ENCRYPTED" in data[:512]


def public_key_fingerprint(public_key: rsa.RSAPublicKey) -> str:
    """Create a stable SHA-256 fingerprint from canonical SPKI DER bytes."""
    der = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = sha256(der).hexdigest().upper()
    return ":".join(digest[index:index + 2] for index in range(0, len(digest), 2))


def inspect_public_key_file(path: str | Path) -> RSAKeyInfo:
    key_path = Path(path).resolve()
    public_key = load_public_key(key_path)
    encoding, container, encrypted = detect_key_format(key_path)
    return RSAKeyInfo(
        path=str(key_path),
        role="public",
        key_size=public_key.key_size,
        encoding=encoding,
        container=container,
        encrypted=encrypted,
        fingerprint=public_key_fingerprint(public_key),
    )


def inspect_private_key_file(
    path: str | Path,
    password: str | bytes | None = None,
) -> RSAKeyInfo:
    key_path = Path(path).resolve()
    encoding, container, encrypted = detect_key_format(key_path)

    try:
        private_key = load_private_key(key_path, password)
    except ValueError as error:
        if password is None and "password is required" in str(error).lower():
            return RSAKeyInfo(
                path=str(key_path),
                role="private",
                key_size=None,
                encoding=encoding,
                container=container,
                encrypted=True,
                fingerprint=None,
            )
        raise

    return RSAKeyInfo(
        path=str(key_path),
        role="private",
        key_size=private_key.key_size,
        encoding=encoding,
        container=container,
        encrypted=encrypted or password is not None,
        fingerprint=public_key_fingerprint(private_key.public_key()),
    )


def inspect_key_file(
    path: str | Path,
    password: str | bytes | None = None,
) -> RSAKeyInfo:
    """Inspect a public or private RSA key without trusting its extension."""
    try:
        return inspect_public_key_file(path)
    except ValueError:
        return inspect_private_key_file(path, password)


def verify_key_pair(
    public_path: str | Path,
    private_path: str | Path,
    password: str | bytes | None = None,
) -> bool:
    public_key = load_public_key(public_path)
    private_key = load_private_key(private_path, password)
    return public_key.public_numbers() == private_key.public_key().public_numbers()


def generate_and_save_keypair(
    directory: str | Path,
    name: str,
    *,
    key_size: int = 3072,
    password: str | bytes | None = None,
    encoding: str = "PEM",
) -> tuple[Path, Path]:
    """Generate an SPKI/PKCS#8 pair and save it without overwriting files."""
    clean_name = name.strip()
    if not clean_name or not re.fullmatch(r"[A-Za-z0-9._-]+", clean_name):
        raise ValueError("Key name may only contain letters, numbers, dots, dashes, and underscores.")

    normalized_encoding = encoding.upper()
    if normalized_encoding not in {"PEM", "DER"}:
        raise ValueError("Key encoding must be PEM or DER.")

    output_dir = Path(directory).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    extension = normalized_encoding.lower()
    private_path = output_dir / f"{clean_name}_private.{extension}"
    public_path = output_dir / f"{clean_name}_public.{extension}"

    collisions = [path.name for path in (private_path, public_path) if path.exists()]
    if collisions:
        raise FileExistsError(f"Key file already exists: {', '.join(collisions)}")

    private_key, public_key = generate_rsa_keypair(key_size)
    serialization_encoding = (
        serialization.Encoding.PEM
        if normalized_encoding == "PEM"
        else serialization.Encoding.DER
    )
    private_data = serialize_private_key(
        private_key,
        password,
        encoding=serialization_encoding,
        private_format=serialization.PrivateFormat.PKCS8,
    )
    public_data = serialize_public_key(
        public_key,
        encoding=serialization_encoding,
        public_format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_path.write_bytes(private_data)
    try:
        public_path.write_bytes(public_data)
    except OSError:
        private_path.unlink(missing_ok=True)
        raise

    return private_path, public_path