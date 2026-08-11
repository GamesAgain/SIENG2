import shutil
import subprocess

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.core.crypto.asym_encrypt import (
    AES_NONCE_LENGTH,
    AES_TAG_LENGTH,
    AsymmetricEncryption,
    deserialize_private_key,
    deserialize_public_key,
    generate_rsa_keypair,
    generate_rsa_keypair_bytes,
    get_private_bytes,
    get_public_bytes,
    load_private_key,
    load_public_key,
    serialize_private_key,
    serialize_public_key,
    validate_rsa_key_size,
)


OPENSSL_TEST_PASSWORD = "OpenSSL-Test-Password-2026!"


@pytest.fixture(scope="session")
def openssl_rsa_keypair_factory(tmp_path_factory):
    """Generate real OpenSSL PKCS#8/SPKI PEM key pairs for compatibility tests."""
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.fail("OpenSSL is required for external RSA compatibility tests")

    key_directory = tmp_path_factory.mktemp("openssl_rsa_keys")
    generated_keypairs = {}

    def run_openssl(command):
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as error:
            pytest.fail(f"OpenSSL command failed: {error.stderr.strip()}")

    def generate_keypair(key_size: int, encrypted: bool = True):
        cache_key = (key_size, encrypted)
        if cache_key in generated_keypairs:
            return generated_keypairs[cache_key]

        protection = "encrypted" if encrypted else "unencrypted"
        private_key_path = key_directory / f"rsa_{key_size}_{protection}_private.pem"
        public_key_path = key_directory / f"rsa_{key_size}_{protection}_public.pem"

        generate_command = [
            openssl,
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            f"rsa_keygen_bits:{key_size}",
        ]
        if encrypted:
            generate_command.extend(
                ["-aes-256-cbc", "-pass", f"pass:{OPENSSL_TEST_PASSWORD}"]
            )
        generate_command.extend(["-out", str(private_key_path)])
        run_openssl(generate_command)

        public_command = [
            openssl,
            "pkey",
            "-in",
            str(private_key_path),
        ]
        if encrypted:
            public_command.extend(["-passin", f"pass:{OPENSSL_TEST_PASSWORD}"])
        public_command.extend(["-pubout", "-out", str(public_key_path)])
        run_openssl(public_command)

        keypair = private_key_path, public_key_path
        generated_keypairs[cache_key] = keypair
        return keypair

    return generate_keypair


def test_generate_default_rsa_keypair():
    private_key, public_key = generate_rsa_keypair()
    assert isinstance(private_key, rsa.RSAPrivateKey)
    assert isinstance(public_key, rsa.RSAPublicKey)
    assert private_key.key_size == 3072
    assert public_key.key_size == 3072


def test_generate_serialized_encrypted_keypair_roundtrip(tmp_path):
    password = "รหัสผ่านกุญแจส่วนตัว-2026"
    private_pem, public_pem = generate_rsa_keypair_bytes(password=password)
    private_key_path = tmp_path / "private_key.pem"
    public_key_path = tmp_path / "public_key.pem"
    private_key_path.write_bytes(private_pem)
    public_key_path.write_bytes(public_pem)

    assert private_pem.startswith(b"-----BEGIN ENCRYPTED PRIVATE KEY-----")
    assert public_pem.startswith(b"-----BEGIN PUBLIC KEY-----")

    private_key = load_private_key(str(private_key_path), password)
    public_key = load_public_key(str(public_key_path))
    cipher = AsymmetricEncryption()
    plaintext = "ทดสอบ encrypted PKCS#8 PEM".encode("utf-8")

    assert cipher.decrypt(cipher.encrypt(plaintext, public_key), private_key) == plaintext


def test_generate_serialized_unencrypted_keypair_roundtrip(tmp_path):
    private_pem, public_pem = generate_rsa_keypair_bytes(key_size=2048)
    private_key_path = tmp_path / "private_key.pem"
    public_key_path = tmp_path / "public_key.pem"
    private_key_path.write_bytes(private_pem)
    public_key_path.write_bytes(public_pem)

    assert private_pem.startswith(b"-----BEGIN PRIVATE KEY-----")
    assert public_pem.startswith(b"-----BEGIN PUBLIC KEY-----")

    private_key = load_private_key(str(private_key_path))
    public_key = load_public_key(str(public_key_path))
    plaintext = b"Unencrypted PKCS#8 compatibility"
    cipher = AsymmetricEncryption()

    assert cipher.decrypt(cipher.encrypt(plaintext, public_key), private_key) == plaintext


def test_serialization_helpers_reject_empty_password():
    private_key, _ = generate_rsa_keypair(key_size=2048)

    with pytest.raises(ValueError, match="password cannot be empty"):
        serialize_private_key(private_key, "")


def test_serialization_helpers_use_recommended_pem_formats():
    private_key, public_key = generate_rsa_keypair(key_size=2048)

    private_pem = serialize_private_key(private_key, "Strong-Test-Password")
    public_pem = serialize_public_key(public_key)

    assert private_pem.startswith(b"-----BEGIN ENCRYPTED PRIVATE KEY-----")
    assert public_pem.startswith(b"-----BEGIN PUBLIC KEY-----")


@pytest.mark.parametrize(
    ("encoding", "public_format", "expected_header"),
    [
        pytest.param(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
            b"-----BEGIN PUBLIC KEY-----",
            id="pem-spki",
        ),
        pytest.param(
            serialization.Encoding.PEM,
            serialization.PublicFormat.PKCS1,
            b"-----BEGIN RSA PUBLIC KEY-----",
            id="pem-pkcs1",
        ),
        pytest.param(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
            None,
            id="der-spki",
        ),
        pytest.param(
            serialization.Encoding.DER,
            serialization.PublicFormat.PKCS1,
            None,
            id="der-pkcs1",
        ),
    ],
)
def test_public_key_format_matrix_roundtrip(
    tmp_path,
    encoding,
    public_format,
    expected_header,
):
    _, public_key = generate_rsa_keypair(key_size=2048)
    key_data = serialize_public_key(
        public_key,
        encoding=encoding,
        public_format=public_format,
    )
    key_path = tmp_path / "public-key.external"
    key_path.write_bytes(key_data)

    if expected_header is not None:
        assert key_data.startswith(expected_header)
    else:
        assert not key_data.startswith(b"-----BEGIN")

    loaded_from_bytes = deserialize_public_key(key_data)
    loaded_from_file = load_public_key(key_path)
    assert loaded_from_bytes.public_numbers() == public_key.public_numbers()
    assert loaded_from_file.public_numbers() == public_key.public_numbers()


@pytest.mark.parametrize(
    ("encoding", "private_format", "password", "expected_header"),
    [
        pytest.param(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            None,
            b"-----BEGIN PRIVATE KEY-----",
            id="pem-pkcs8-unencrypted",
        ),
        pytest.param(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            "PKCS8-Password",
            b"-----BEGIN ENCRYPTED PRIVATE KEY-----",
            id="pem-pkcs8-encrypted",
        ),
        pytest.param(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            None,
            b"-----BEGIN RSA PRIVATE KEY-----",
            id="pem-pkcs1-unencrypted",
        ),
        pytest.param(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            "PKCS1-Password",
            b"-----BEGIN RSA PRIVATE KEY-----",
            id="pem-pkcs1-encrypted",
        ),
        pytest.param(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            None,
            None,
            id="der-pkcs8-unencrypted",
        ),
        pytest.param(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            b"DER-PKCS8-Password",
            None,
            id="der-pkcs8-encrypted",
        ),
        pytest.param(
            serialization.Encoding.DER,
            serialization.PrivateFormat.TraditionalOpenSSL,
            None,
            None,
            id="der-pkcs1-unencrypted",
        ),
    ],
)
def test_private_key_format_matrix_roundtrip(
    tmp_path,
    encoding,
    private_format,
    password,
    expected_header,
):
    private_key, _ = generate_rsa_keypair(key_size=2048)
    key_data = serialize_private_key(
        private_key,
        password,
        encoding=encoding,
        private_format=private_format,
    )
    key_path = tmp_path / "private-key.external"
    key_path.write_bytes(key_data)

    if expected_header is not None:
        assert key_data.startswith(expected_header)
    else:
        assert not key_data.startswith(b"-----BEGIN")

    loaded_from_bytes = deserialize_private_key(key_data, password)
    loaded_from_file = load_private_key(key_path, password)
    expected_numbers = private_key.private_numbers()
    assert loaded_from_bytes.private_numbers() == expected_numbers
    assert loaded_from_file.private_numbers() == expected_numbers


def test_canonical_key_bytes_are_stable_across_supported_formats():
    private_key, public_key = generate_rsa_keypair(key_size=2048)
    expected_public_bytes = get_public_bytes(public_key)

    public_pkcs1_pem = serialize_public_key(
        public_key,
        public_format=serialization.PublicFormat.PKCS1,
    )
    private_pkcs1_pem = serialize_private_key(
        private_key,
        private_format=serialization.PrivateFormat.TraditionalOpenSSL,
    )

    assert get_public_bytes(deserialize_public_key(public_pkcs1_pem)) == expected_public_bytes
    loaded_private_key = deserialize_private_key(private_pkcs1_pem)
    assert get_public_bytes(loaded_private_key.public_key()) == expected_public_bytes
    assert get_private_bytes(loaded_private_key) == get_private_bytes(private_key)


def test_unsupported_serialization_combinations_are_rejected():
    private_key, public_key = generate_rsa_keypair(key_size=2048)

    with pytest.raises(ValueError, match="Encrypted PKCS#1.*require PEM"):
        serialize_private_key(
            private_key,
            "Password",
            encoding=serialization.Encoding.DER,
            private_format=serialization.PrivateFormat.TraditionalOpenSSL,
        )

    with pytest.raises(ValueError, match="only be serialized as PEM or DER"):
        serialize_public_key(
            public_key,
            encoding=serialization.Encoding.OpenSSH,
        )

    with pytest.raises(ValueError, match="Unsupported RSA key serialization format"):
        serialize_public_key(
            public_key,
            public_format=serialization.PublicFormat.OpenSSH,
        )


def test_private_key_password_errors_for_der_and_unencrypted_keys():
    private_key, _ = generate_rsa_keypair(key_size=2048)
    encrypted_der = serialize_private_key(
        private_key,
        "Correct-Password",
        encoding=serialization.Encoding.DER,
    )
    unencrypted_der = serialize_private_key(
        private_key,
        encoding=serialization.Encoding.DER,
    )

    with pytest.raises(ValueError, match="password is required"):
        deserialize_private_key(encrypted_der)

    with pytest.raises(ValueError, match="Incorrect private key password"):
        deserialize_private_key(encrypted_der, "Wrong-Password")

    with pytest.raises(ValueError, match="not encrypted.*Remove the password"):
        deserialize_private_key(unencrypted_der, "Unnecessary-Password")


def test_openssh_public_key_remains_loadable_for_backward_compatibility():
    _, public_key = generate_rsa_keypair(key_size=2048)
    openssh_data = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )

    loaded_key = deserialize_public_key(openssh_data)
    assert loaded_key.public_numbers() == public_key.public_numbers()


def test_encrypt_rejects_invalid_plaintext_types_and_empty_data():
    _, public_key = generate_rsa_keypair(key_size=2048)
    cipher = AsymmetricEncryption()

    with pytest.raises(TypeError, match="Data must be bytes"):
        cipher.encrypt("not bytes", public_key)

    with pytest.raises(ValueError, match="Data cannot be empty"):
        cipher.encrypt(b"", public_key)


def test_decrypt_rejects_short_or_tampered_payload():
    private_key, public_key = generate_rsa_keypair(key_size=2048)
    cipher = AsymmetricEncryption()

    with pytest.raises(ValueError, match="too short or corrupted"):
        cipher.decrypt(b"short", private_key)

    encrypted_data = cipher.encrypt(b"Authenticated payload", public_key)
    tampered_data = encrypted_data[:-1] + bytes([encrypted_data[-1] ^ 1])
    with pytest.raises(InvalidTag):
        cipher.decrypt(tampered_data, private_key)


def test_existing_rsa3072_payload_layout_remains_decryptable():
    private_key, public_key = generate_rsa_keypair(key_size=3072)
    session_key = bytes(range(32))
    nonce = bytes(range(AES_NONCE_LENGTH))
    plaintext = b"Existing SIENG2 RSA-3072 payload"
    ciphertext = AESGCM(session_key).encrypt(nonce, plaintext, None)
    encrypted_session_key = public_key.encrypt(
        session_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    legacy_payload = encrypted_session_key + nonce + ciphertext

    assert AsymmetricEncryption().decrypt(legacy_payload, private_key) == plaintext


def test_encrypt_below_size_minimum_raises_error():
    cipher = AsymmetricEncryption()
    original_data = b"Test data for encryption"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    public_key = private_key.public_key()

    with pytest.raises(ValueError, match="below 2048 bits are unsafe") as exc_info:
        cipher.encrypt(original_data, public_key)

    assert "RSA-1024" in str(exc_info.value)


@pytest.mark.parametrize(
    ("key_size", "expected_message"),
    [
        (1024, "below 2048 bits are unsafe"),
        (2560, "not a supported SIENG2 key size"),
        (8192, "limits RSA keys to 4096 bits"),
    ],
)
def test_unsupported_rsa_key_size_messages(key_size, expected_message):
    with pytest.raises(ValueError, match=expected_message):
        validate_rsa_key_size(key_size)


def test_generate_unsupported_rsa_keypair_rejected():
    with pytest.raises(ValueError, match="RSA-1024"):
        generate_rsa_keypair(key_size=1024)


def test_non_rsa_keys_rejected():
    ec_private_key = ec.generate_private_key(ec.SECP256R1())
    cipher = AsymmetricEncryption()

    with pytest.raises(ValueError, match="not an RSA public key"):
        cipher.encrypt(b"RSA mode only", ec_private_key.public_key())

    with pytest.raises(ValueError, match="not an RSA private key"):
        cipher.decrypt(b"invalid payload", ec_private_key)


def test_loaders_reject_non_rsa_keys(tmp_path):
    ec_private_key = ec.generate_private_key(ec.SECP256R1())
    public_key_path = tmp_path / "ec_public.pem"
    private_key_path = tmp_path / "ec_private.pem"
    public_key_path.write_bytes(
        ec_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    private_key_path.write_bytes(
        ec_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    with pytest.raises(ValueError, match="not an RSA public key"):
        load_public_key(str(public_key_path))

    with pytest.raises(ValueError, match="not an RSA private key"):
        load_private_key(str(private_key_path))


@pytest.mark.parametrize("key_size", [2048, 3072, 4096])
def test_encrypt_decrypt_with_supported_rsa_key_sizes(key_size):
    cipher = AsymmetricEncryption()
    original_data = b"Test data for encryption"
    private_key, public_key = generate_rsa_keypair(key_size=key_size)

    encrypted_data = cipher.encrypt(original_data, public_key)
    expected_length = (
        key_size // 8
        + AES_NONCE_LENGTH
        + len(original_data)
        + AES_TAG_LENGTH
    )

    assert isinstance(encrypted_data, bytes)
    assert len(encrypted_data) == expected_length

    decrypted_data = cipher.decrypt(encrypted_data, private_key)
    assert decrypted_data == original_data


def test_wrong_private_key_rejected():
    first_private_key, first_public_key = generate_rsa_keypair(key_size=2048)
    second_private_key, _ = generate_rsa_keypair(key_size=2048)
    cipher = AsymmetricEncryption()
    encrypted_data = cipher.encrypt(b"Secret for the first recipient", first_public_key)

    with pytest.raises(ValueError):
        cipher.decrypt(encrypted_data, second_private_key)


@pytest.mark.parametrize("key_size", [2048, 3072, 4096])
def test_external_openssl_encrypted_rsa_roundtrip(
    openssl_rsa_keypair_factory,
    key_size,
):
    private_key_path, public_key_path = openssl_rsa_keypair_factory(
        key_size,
        encrypted=True,
    )

    private_pem = private_key_path.read_bytes()
    public_pem = public_key_path.read_bytes()
    assert private_pem.startswith(b"-----BEGIN ENCRYPTED PRIVATE KEY-----")
    assert public_pem.startswith(b"-----BEGIN PUBLIC KEY-----")

    private_key = load_private_key(
        str(private_key_path),
        OPENSSL_TEST_PASSWORD,
    )
    public_key = load_public_key(str(public_key_path))
    cipher = AsymmetricEncryption()
    plaintext = f"External OpenSSL RSA-{key_size}".encode("utf-8")

    assert private_key.key_size == key_size
    assert public_key.key_size == key_size

    encrypted_data = cipher.encrypt(plaintext, public_key)
    assert cipher.decrypt(encrypted_data, private_key) == plaintext


def test_external_openssl_unencrypted_rsa_roundtrip(openssl_rsa_keypair_factory):
    private_key_path, public_key_path = openssl_rsa_keypair_factory(
        3072,
        encrypted=False,
    )

    assert private_key_path.read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----")
    private_key = load_private_key(str(private_key_path))
    public_key = load_public_key(str(public_key_path))
    cipher = AsymmetricEncryption()
    plaintext = b"External unencrypted OpenSSL PKCS#8"

    assert cipher.decrypt(cipher.encrypt(plaintext, public_key), private_key) == plaintext


def test_external_openssl_pem_der_and_pkcs1_compatibility(
    tmp_path,
    openssl_rsa_keypair_factory,
):
    openssl = shutil.which("openssl")
    private_key_path, _ = openssl_rsa_keypair_factory(2048, encrypted=False)
    expected_private_key = load_private_key(private_key_path)
    expected_public_numbers = expected_private_key.public_key().public_numbers()

    generated_files = {
        "public_spki_der": tmp_path / "public-spki.der",
        "public_pkcs1_pem": tmp_path / "public-pkcs1.pem",
        "public_pkcs1_der": tmp_path / "public-pkcs1.der",
        "private_pkcs1_pem": tmp_path / "private-pkcs1.pem",
        "private_pkcs8_der": tmp_path / "private-pkcs8.der",
        "private_pkcs8_encrypted_der": tmp_path / "private-pkcs8-encrypted.der",
    }
    commands = [
        [
            openssl,
            "pkey",
            "-in",
            str(private_key_path),
            "-pubout",
            "-outform",
            "DER",
            "-out",
            str(generated_files["public_spki_der"]),
        ],
        [
            openssl,
            "rsa",
            "-in",
            str(private_key_path),
            "-RSAPublicKey_out",
            "-out",
            str(generated_files["public_pkcs1_pem"]),
        ],
        [
            openssl,
            "rsa",
            "-in",
            str(private_key_path),
            "-RSAPublicKey_out",
            "-outform",
            "DER",
            "-out",
            str(generated_files["public_pkcs1_der"]),
        ],
        [
            openssl,
            "pkey",
            "-in",
            str(private_key_path),
            "-traditional",
            "-out",
            str(generated_files["private_pkcs1_pem"]),
        ],
        [
            openssl,
            "pkcs8",
            "-topk8",
            "-in",
            str(private_key_path),
            "-outform",
            "DER",
            "-nocrypt",
            "-out",
            str(generated_files["private_pkcs8_der"]),
        ],
        [
            openssl,
            "pkcs8",
            "-topk8",
            "-in",
            str(private_key_path),
            "-outform",
            "DER",
            "-v2",
            "aes-256-cbc",
            "-passout",
            f"pass:{OPENSSL_TEST_PASSWORD}",
            "-out",
            str(generated_files["private_pkcs8_encrypted_der"]),
        ],
    ]

    for command in commands:
        subprocess.run(command, check=True, capture_output=True, text=True)

    for name in ("public_spki_der", "public_pkcs1_pem", "public_pkcs1_der"):
        loaded_public_key = load_public_key(generated_files[name])
        assert loaded_public_key.public_numbers() == expected_public_numbers

    loaded_pkcs1_private_key = load_private_key(generated_files["private_pkcs1_pem"])
    loaded_pkcs8_der_key = load_private_key(generated_files["private_pkcs8_der"])
    loaded_encrypted_der_key = load_private_key(
        generated_files["private_pkcs8_encrypted_der"],
        OPENSSL_TEST_PASSWORD,
    )
    expected_private_numbers = expected_private_key.private_numbers()
    assert loaded_pkcs1_private_key.private_numbers() == expected_private_numbers
    assert loaded_pkcs8_der_key.private_numbers() == expected_private_numbers
    assert loaded_encrypted_der_key.private_numbers() == expected_private_numbers


def test_external_openssl_encrypted_private_key_requires_correct_password(
    openssl_rsa_keypair_factory,
):
    private_key_path, _ = openssl_rsa_keypair_factory(2048, encrypted=True)

    with pytest.raises(ValueError, match="password is required"):
        load_private_key(str(private_key_path))

    with pytest.raises(ValueError, match="Incorrect private key password"):
        load_private_key(str(private_key_path), "WrongPassword")
