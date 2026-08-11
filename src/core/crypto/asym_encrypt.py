"""RSA hybrid encryption and RSA key serialization helpers.

The encrypted payload layout SIENG2 data::

    RSA-OAEP encrypted AES key | AES-GCM nonce | AES-GCM ciphertext and tag

Public keys are exported as SPKI PEM and private keys as PKCS#8 PEM by
default. PEM/DER and modern/legacy RSA structures can also be selected for
compatibility with external tools and libraries such as OpenSSL, OpenSSH,
Java JCA/JCE, .NET, Node.js, and Go.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.core.crypto.sym_encrypt import (
    AES_KEY_LENGTH,
    AES_NONCE_LENGTH,
    AES_TAG_LENGTH,
)


SUPPORTED_RSA_KEY_SIZES = (2048, 3072, 4096)
RSA_KEY_SIZE_DEFAULT = 3072
PUBLIC_EXPONENT = 65537

DEFAULT_PUBLIC_ENCODING = serialization.Encoding.PEM
DEFAULT_PUBLIC_FORMAT = serialization.PublicFormat.SubjectPublicKeyInfo
DEFAULT_PRIVATE_ENCODING = serialization.Encoding.PEM
DEFAULT_PRIVATE_FORMAT = serialization.PrivateFormat.PKCS8

SUPPORTED_KEY_ENCODINGS = (
    serialization.Encoding.PEM,
    serialization.Encoding.DER,
)
SUPPORTED_PUBLIC_FORMATS = (
    serialization.PublicFormat.SubjectPublicKeyInfo,
    serialization.PublicFormat.PKCS1,
)
SUPPORTED_PRIVATE_FORMATS = (
    serialization.PrivateFormat.PKCS8,
    serialization.PrivateFormat.TraditionalOpenSSL,
)


def validate_rsa_key_size(key_size: int) -> None:
    """Enforce the RSA key-size policy shared by every entry point."""
    if not isinstance(key_size, int) or isinstance(key_size, bool):
        raise TypeError("RSA key size must be an integer number of bits.")

    if key_size in SUPPORTED_RSA_KEY_SIZES:
        return

    if key_size < min(SUPPORTED_RSA_KEY_SIZES):
        raise ValueError(
            f"RSA-{key_size} is not supported because RSA keys below 2048 bits "
            "are unsafe. Use RSA-2048, RSA-3072 (recommended), or RSA-4096."
        )

    if key_size > max(SUPPORTED_RSA_KEY_SIZES):
        raise ValueError(
            f"RSA-{key_size} is not supported. SIENG2 limits RSA keys to 4096 "
            "bits to control processing time and embedded payload size. Use "
            "RSA-3072 (recommended) or RSA-4096."
        )

    raise ValueError(
        f"RSA-{key_size} is not a supported SIENG2 key size. Use RSA-2048, "
        "RSA-3072 (recommended), or RSA-4096."
    )


def validate_rsa_public_key(public_key: object) -> rsa.RSAPublicKey:
    """Return a supported RSA public key or raise a user-facing error."""
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise ValueError(
            "Selected key is not an RSA public key. Use an RSA-2048, "
            "RSA-3072 (recommended), or RSA-4096 public key."
        )

    validate_rsa_key_size(public_key.key_size)
    return public_key


def validate_rsa_private_key(private_key: object) -> rsa.RSAPrivateKey:
    """Return a supported RSA private key or raise a user-facing error."""
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise ValueError(
            "Selected key is not an RSA private key. Use an RSA-2048, "
            "RSA-3072 (recommended), or RSA-4096 private key."
        )

    validate_rsa_key_size(private_key.key_size)
    return private_key


def require_non_empty_bytes(data: object, label: str) -> bytes:
    if not isinstance(data, bytes):
        raise TypeError(f"{label} must be bytes.")
    if not data:
        raise ValueError(f"{label} cannot be empty.")
    return data


def rsa_oaep_padding() -> padding.OAEP:
    """Build the RSA-OAEP profile used by the SIENG2 payload format."""
    return padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None,
    )


class AsymmetricEncryption:
    """Hybrid encryption using RSA-OAEP-SHA256 and AES-256-GCM."""

    def encrypt(self, data: bytes, public_key: rsa.RSAPublicKey) -> bytes:
        """Encrypt Data With RSA-OAEP-SHA256 + AES-256-GCM: [Encrypted Key + Nonce + Ciphertext + Tag]"""
        plaintext = require_non_empty_bytes(data, "Data")
        validated_key = validate_rsa_public_key(public_key)

        session_key = os.urandom(AES_KEY_LENGTH)
        nonce = os.urandom(AES_NONCE_LENGTH)
        ciphertext = AESGCM(session_key).encrypt(
            nonce,
            plaintext,
            associated_data=None,
        )
        encrypted_session_key = validated_key.encrypt(
            session_key,
            rsa_oaep_padding(),
        )

        return encrypted_session_key + nonce + ciphertext

    def decrypt(self, encrypted_data: bytes, private_key: rsa.RSAPrivateKey) -> bytes:
        """Decrypt a payload created by encrypt(): [Encrypted Key + Nonce + Ciphertext + Tag]"""
        validated_key = validate_rsa_private_key(private_key)
        payload = require_non_empty_bytes(encrypted_data, "Encrypted data")

        encrypted_key_length = validated_key.key_size // 8
        minimum_length = encrypted_key_length + AES_NONCE_LENGTH + AES_TAG_LENGTH
        if len(payload) < minimum_length:
            raise ValueError("Encrypted data is too short or corrupted.")

        encrypted_session_key = payload[:encrypted_key_length]
        nonce_end = encrypted_key_length + AES_NONCE_LENGTH
        nonce = payload[encrypted_key_length:nonce_end]
        ciphertext = payload[nonce_end:]

        session_key = validated_key.decrypt(
            encrypted_session_key,
            rsa_oaep_padding(),
        )
        return AESGCM(session_key).decrypt(
            nonce,
            ciphertext,
            associated_data=None,
        )

    def validate_input(self, data: bytes, public_key: rsa.RSAPublicKey) -> None:
        """Validate encryption input without changing it."""
        require_non_empty_bytes(data, "Data")
        validate_rsa_public_key(public_key)

    def validate_private_key(self, private_key: rsa.RSAPrivateKey) -> None:
        """Validate the RSA private key used for decryption."""
        validate_rsa_private_key(private_key)


def generate_rsa_keypair(
    key_size: int = RSA_KEY_SIZE_DEFAULT,
) -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Generate an RSA key pair; RSA-3072 is the default."""
    validate_rsa_key_size(key_size)
    private_key = rsa.generate_private_key(
        public_exponent=PUBLIC_EXPONENT,
        key_size=key_size,
    )
    return private_key, private_key.public_key()


def password_to_bytes(password: str | bytes | None) -> bytes | None:
    """Normalize a GUI string or caller-supplied bytes password."""
    if password is None:
        return None

    if isinstance(password, str):
        password_bytes = password.encode("utf-8")
    elif isinstance(password, bytes):
        password_bytes = password
    else:
        raise TypeError("Private key password must be a string, bytes, or None.")

    if not password_bytes:
        raise ValueError(
            "Private key password cannot be empty. Use None for an unencrypted key."
        )

    return password_bytes


def validate_serialization_choice(
    encoding: serialization.Encoding,
    key_format: serialization.PublicFormat | serialization.PrivateFormat,
    supported_formats: tuple,
) -> None:
    if encoding not in SUPPORTED_KEY_ENCODINGS:
        raise ValueError("RSA keys can only be serialized as PEM or DER.")
    if key_format not in supported_formats:
        raise ValueError("Unsupported RSA key serialization format.")


def serialize_private_key(
    private_key: rsa.RSAPrivateKey,
    password: str | bytes | None = None,
    *,
    encoding: serialization.Encoding = DEFAULT_PRIVATE_ENCODING,
    private_format: serialization.PrivateFormat = DEFAULT_PRIVATE_FORMAT,
) -> bytes:
    """Serialize an RSA private key.

    PKCS#8 PEM is the default. TraditionalOpenSSL represents the legacy
    RSA-specific PKCS#1 structure accepted for external compatibility.
    """
    validated_key = validate_rsa_private_key(private_key)
    validate_serialization_choice(
        encoding,
        private_format,
        SUPPORTED_PRIVATE_FORMATS,
    )
    password_bytes = password_to_bytes(password)

    if (
        encoding == serialization.Encoding.DER
        and private_format == serialization.PrivateFormat.TraditionalOpenSSL
        and password_bytes is not None
    ):
        raise ValueError("Encrypted PKCS#1 private keys require PEM encoding.")

    encryption = (
        serialization.NoEncryption()
        if password_bytes is None
        else serialization.BestAvailableEncryption(password_bytes)
    )
    return validated_key.private_bytes(
        encoding=encoding,
        format=private_format,
        encryption_algorithm=encryption,
    )


def serialize_public_key(
    public_key: rsa.RSAPublicKey,
    *,
    encoding: serialization.Encoding = DEFAULT_PUBLIC_ENCODING,
    public_format: serialization.PublicFormat = DEFAULT_PUBLIC_FORMAT,
) -> bytes:
    """Serialize an RSA public key; SPKI PEM is the default."""
    validated_key = validate_rsa_public_key(public_key)
    validate_serialization_choice(
        encoding,
        public_format,
        SUPPORTED_PUBLIC_FORMATS,
    )
    return validated_key.public_bytes(
        encoding=encoding,
        format=public_format,
    )


def generate_rsa_keypair_bytes(
    key_size: int = RSA_KEY_SIZE_DEFAULT,
    password: str | bytes | None = None,
) -> tuple[bytes, bytes]:
    """Generate a PKCS#8/SPKI PEM key pair using the recommended defaults."""
    private_key, public_key = generate_rsa_keypair(key_size)
    return (
        serialize_private_key(private_key, password),
        serialize_public_key(public_key),
    )


def get_private_bytes(private_key: rsa.RSAPrivateKey) -> bytes:
    """Return canonical unencrypted PKCS#8 DER bytes for internal use."""
    return serialize_private_key(
        private_key,
        encoding=serialization.Encoding.DER,
        private_format=serialization.PrivateFormat.PKCS8,
    )


def get_public_bytes(public_key: rsa.RSAPublicKey) -> bytes:
    """Return canonical SPKI DER bytes for a stable steganography seed."""
    return serialize_public_key(
        public_key,
        encoding=serialization.Encoding.DER,
        public_format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def deserialize_public_key(key_data: bytes) -> rsa.RSAPublicKey:
    """Parse and validate an RSA public key from PEM or DER bytes.

    OpenSSH public key input remains accepted for backward compatibility, but
    it is not used as the default SIENG2 export format.
    """
    data = require_non_empty_bytes(key_data, "Public key data")
    loaders = (
        serialization.load_pem_public_key,
        serialization.load_der_public_key,
        serialization.load_ssh_public_key,
    )

    for loader in loaders:
        try:
            public_key = loader(data)
        except (TypeError, ValueError, UnsupportedAlgorithm):
            continue
        return validate_rsa_public_key(public_key)

    raise ValueError("Failed to load public key: unsupported format or corrupted data.")


def deserialize_private_key(
    key_data: bytes,
    password: str | bytes | None = None,
) -> rsa.RSAPrivateKey:
    """Parse and validate an RSA private key from PEM or DER bytes."""
    data = require_non_empty_bytes(key_data, "Private key data")
    password_bytes = password_to_bytes(password)
    password_usage_error = False

    for loader in (
        serialization.load_pem_private_key,
        serialization.load_der_private_key,
    ):
        try:
            private_key = loader(data, password=password_bytes)
        except TypeError:
            password_usage_error = True
            continue
        except (ValueError, UnsupportedAlgorithm):
            continue
        return validate_rsa_private_key(private_key)

    if password_usage_error:
        if password_bytes is None:
            raise ValueError("Private key is encrypted. A password is required.")
        raise ValueError("Private key is not encrypted. Remove the password.")

    if password_bytes is not None:
        raise ValueError("Incorrect private key password or corrupted private key.")

    raise ValueError("Failed to load private key: unsupported format or corrupted data.")


def read_key_file(file_path: str | os.PathLike[str], key_role: str) -> bytes:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"{key_role} key file not found: {path}")
    return path.read_bytes()


def load_public_key(file_path: str | os.PathLike[str]) -> rsa.RSAPublicKey:
    """Load an RSA public key from a PEM, DER, or OpenSSH public-key file."""
    key_data = read_key_file(file_path, "Public")
    try:
        return deserialize_public_key(key_data)
    except ValueError as error:
        raise ValueError(f"{error} File: {file_path}") from error


def load_private_key(
    file_path: str | os.PathLike[str],
    password: str | bytes | None = None,
) -> rsa.RSAPrivateKey:
    """Load an RSA private key from a PEM or DER file."""
    key_data = read_key_file(file_path, "Private")
    try:
        return deserialize_private_key(key_data, password)
    except ValueError as error:
        raise ValueError(f"{error} File: {file_path}") from error