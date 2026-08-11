import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from cryptography.hazmat.primitives import serialization

from src.core.crypto.asym_encrypt import (
    generate_rsa_keypair,
    serialize_private_key,
    serialize_public_key,
)
from src.core.stego.locomotive import Locomotive
from src.core.stego.lsb_pp import LSBPP


TEST_MESSAGE = "SIENG2 integration test: ข้อความลับ 🔐"
SYMMETRIC_PASSWORD = "Strong-Password-2026!"
PRIVATE_KEY_PASSWORD = "Private-Key-Password-2026!"

RSA_CASE_MATRIX = [
    pytest.param("sieng2", 2048, "pem", False, id="sieng2-pem-rsa2048"),
    pytest.param("sieng2", 3072, "pem", True, id="sieng2-pem-rsa3072-encrypted"),
    pytest.param("sieng2", 4096, "der", True, id="sieng2-der-rsa4096-encrypted"),
    pytest.param("openssl", 2048, "pem", False, id="openssl-pem-rsa2048"),
    pytest.param("openssl", 3072, "pem", True, id="openssl-pem-rsa3072-encrypted"),
    pytest.param("openssl", 4096, "der", True, id="openssl-der-rsa4096-encrypted"),
]


@pytest.fixture(scope="session")
def textured_cover_path(tmp_path_factory):
    """Create a repeatable high-texture PNG with enough LSB capacity."""
    output_dir = tmp_path_factory.mktemp("stego_covers")
    cover_path = output_dir / "textured-cover.png"
    random_pixels = np.random.default_rng(2026).integers(
        0,
        256,
        size=(256, 256, 3),
        dtype=np.uint8,
    )
    Image.fromarray(random_pixels).save(cover_path, format="PNG")
    return cover_path


@pytest.fixture(scope="session")
def rsa_key_file_factory(tmp_path_factory):
    """Create and cache SIENG2 or OpenSSL RSA key files for integration tests."""
    key_dir = tmp_path_factory.mktemp("stego_rsa_keys")
    openssl = shutil.which("openssl")
    generated_keys = {}

    def run_openssl(command):
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as error:
            pytest.fail(f"OpenSSL command failed: {error.stderr.strip()}")

    def create_keys(source, key_size, encoding_name, encrypted):
        cache_key = source, key_size, encoding_name, encrypted
        if cache_key in generated_keys:
            return generated_keys[cache_key]

        extension = encoding_name
        prefix = f"{source}-{key_size}-{encoding_name}-{'enc' if encrypted else 'plain'}"
        public_path = key_dir / f"{prefix}-public.{extension}"
        private_path = key_dir / f"{prefix}-private.{extension}"
        password = PRIVATE_KEY_PASSWORD if encrypted else None

        if source == "sieng2":
            private_key, public_key = generate_rsa_keypair(key_size)
            encoding = (
                serialization.Encoding.PEM
                if encoding_name == "pem"
                else serialization.Encoding.DER
            )
            public_path.write_bytes(
                serialize_public_key(public_key, encoding=encoding)
            )
            private_path.write_bytes(
                serialize_private_key(
                    private_key,
                    password,
                    encoding=encoding,
                )
            )
        else:
            if openssl is None:
                pytest.fail("OpenSSL is required for external integration tests")
            base_private_path = key_dir / f"{prefix}-base-private.pem"
            run_openssl(
                [
                    openssl,
                    "genpkey",
                    "-algorithm",
                    "RSA",
                    "-pkeyopt",
                    f"rsa_keygen_bits:{key_size}",
                    "-out",
                    str(base_private_path),
                ]
            )

            public_command = [
                openssl,
                "pkey",
                "-in",
                str(base_private_path),
                "-pubout",
            ]
            if encoding_name == "der":
                public_command.extend(["-outform", "DER"])
            public_command.extend(["-out", str(public_path)])
            run_openssl(public_command)

            private_command = [
                openssl,
                "pkcs8",
                "-topk8",
                "-in",
                str(base_private_path),
            ]
            if encoding_name == "der":
                private_command.extend(["-outform", "DER"])
            if encrypted:
                private_command.extend(
                    [
                        "-v2",
                        "aes-256-cbc",
                        "-passout",
                        f"pass:{PRIVATE_KEY_PASSWORD}",
                    ]
                )
            else:
                private_command.append("-nocrypt")
            private_command.extend(["-out", str(private_path)])
            run_openssl(private_command)

        result = public_path, private_path, password
        generated_keys[cache_key] = result
        return result

    return create_keys


@pytest.fixture(scope="session")
def mismatched_key_paths(tmp_path_factory):
    key_dir = tmp_path_factory.mktemp("mismatched_rsa_keys")
    _, public_key = generate_rsa_keypair(2048)
    wrong_private_key, _ = generate_rsa_keypair(2048)
    public_path = key_dir / "public.pem"
    private_path = key_dir / "wrong-private.pem"
    public_path.write_bytes(serialize_public_key(public_key))
    private_path.write_bytes(serialize_private_key(wrong_private_key))
    return public_path, private_path


def save_locomotive_outputs(output_dir: Path, outputs):
    paths = []
    for output_name, output_data in outputs:
        output_path = output_dir / output_name
        output_path.write_bytes(output_data)
        paths.append(str(output_path))
    return paths


def test_lsbpp_password_mode_roundtrip(tmp_path, textured_cover_path):
    stego_bytes, output_name = LSBPP().embed(
        str(textured_cover_path),
        TEST_MESSAGE,
        password=SYMMETRIC_PASSWORD,
    )
    stego_path = tmp_path / output_name
    stego_path.write_bytes(stego_bytes)

    extracted_message = LSBPP().extract(
        str(stego_path),
        password=SYMMETRIC_PASSWORD,
    )
    assert extracted_message == TEST_MESSAGE


@pytest.mark.parametrize(
    ("source", "key_size", "encoding_name", "encrypted"),
    RSA_CASE_MATRIX,
)
def test_lsbpp_rsa_mode_roundtrip(
    tmp_path,
    textured_cover_path,
    rsa_key_file_factory,
    source,
    key_size,
    encoding_name,
    encrypted,
):
    public_path, private_path, key_password = rsa_key_file_factory(
        source,
        key_size,
        encoding_name,
        encrypted,
    )
    stego_bytes, output_name = LSBPP().embed(
        str(textured_cover_path),
        TEST_MESSAGE,
        public_key_path=str(public_path),
    )
    stego_path = tmp_path / output_name
    stego_path.write_bytes(stego_bytes)

    extracted_message = LSBPP().extract(
        str(stego_path),
        private_key_path=str(private_path),
        password=key_password,
    )
    assert extracted_message == TEST_MESSAGE


def test_lsbpp_wrong_password_cannot_extract(tmp_path, textured_cover_path):
    stego_bytes, output_name = LSBPP().embed(
        str(textured_cover_path),
        TEST_MESSAGE,
        password=SYMMETRIC_PASSWORD,
    )
    stego_path = tmp_path / output_name
    stego_path.write_bytes(stego_bytes)

    with pytest.raises(ValueError):
        LSBPP().extract(str(stego_path), password="Wrong-Password")


def test_lsbpp_wrong_private_key_cannot_extract(
    tmp_path,
    textured_cover_path,
    mismatched_key_paths,
):
    public_path, wrong_private_path = mismatched_key_paths
    stego_bytes, output_name = LSBPP().embed(
        str(textured_cover_path),
        TEST_MESSAGE,
        public_key_path=str(public_path),
    )
    stego_path = tmp_path / output_name
    stego_path.write_bytes(stego_bytes)

    with pytest.raises(ValueError):
        LSBPP().extract(
            str(stego_path),
            private_key_path=str(wrong_private_path),
        )


def test_locomotive_password_mode_roundtrip(tmp_path, textured_cover_path):
    outputs = Locomotive().embed(
        [str(textured_cover_path)],
        raw_text=TEST_MESSAGE,
        password=SYMMETRIC_PASSWORD,
    )
    stego_paths = save_locomotive_outputs(tmp_path, outputs)

    output_name, output_data = Locomotive().extract(
        stego_paths,
        password=SYMMETRIC_PASSWORD,
    )
    assert output_name == "secret_message.txt"
    assert output_data.decode("utf-8") == TEST_MESSAGE


@pytest.mark.parametrize(
    ("source", "key_size", "encoding_name", "encrypted"),
    RSA_CASE_MATRIX,
)
def test_locomotive_rsa_mode_roundtrip(
    tmp_path,
    textured_cover_path,
    rsa_key_file_factory,
    source,
    key_size,
    encoding_name,
    encrypted,
):
    public_path, private_path, key_password = rsa_key_file_factory(
        source,
        key_size,
        encoding_name,
        encrypted,
    )
    outputs = Locomotive().embed(
        [str(textured_cover_path)],
        raw_text=TEST_MESSAGE,
        public_key_path=str(public_path),
    )
    stego_paths = save_locomotive_outputs(tmp_path, outputs)

    output_name, output_data = Locomotive().extract(
        stego_paths,
        private_key_path=str(private_path),
        password=key_password,
    )
    assert output_name == "secret_message.txt"
    assert output_data.decode("utf-8") == TEST_MESSAGE


def test_locomotive_multiple_covers_binary_file_roundtrip(
    tmp_path,
    textured_cover_path,
):
    cover_paths = []
    cover_data = textured_cover_path.read_bytes()
    for index in range(3):
        cover_path = tmp_path / f"cover-{index}.png"
        cover_path.write_bytes(cover_data)
        cover_paths.append(str(cover_path))

    payload_path = tmp_path / "payload.bin"
    expected_data = bytes(range(256)) + b"\x00SIENG2-binary-payload\xff"
    payload_path.write_bytes(expected_data)

    outputs = Locomotive().embed(
        cover_paths,
        file_paths=[str(payload_path)],
        password=SYMMETRIC_PASSWORD,
    )
    stego_paths = save_locomotive_outputs(tmp_path, outputs)

    output_name, output_data = Locomotive().extract(
        stego_paths,
        password=SYMMETRIC_PASSWORD,
    )
    assert output_name == payload_path.name
    assert output_data == expected_data


def test_locomotive_wrong_password_cannot_extract(tmp_path, textured_cover_path):
    outputs = Locomotive().embed(
        [str(textured_cover_path)],
        raw_text=TEST_MESSAGE,
        password=SYMMETRIC_PASSWORD,
    )
    stego_paths = save_locomotive_outputs(tmp_path, outputs)

    with pytest.raises(ValueError):
        Locomotive().extract(stego_paths, password="Wrong-Password")


def test_locomotive_wrong_private_key_cannot_extract(
    tmp_path,
    textured_cover_path,
    mismatched_key_paths,
):
    public_path, wrong_private_path = mismatched_key_paths
    outputs = Locomotive().embed(
        [str(textured_cover_path)],
        raw_text=TEST_MESSAGE,
        public_key_path=str(public_path),
    )
    stego_paths = save_locomotive_outputs(tmp_path, outputs)

    with pytest.raises(ValueError):
        Locomotive().extract(
            stego_paths,
            private_key_path=str(wrong_private_path),
        )


def test_lsbpp_rejects_password_and_public_key_together(textured_cover_path):
    with pytest.raises(ValueError, match="either password encryption or public-key"):
        LSBPP().embed(
            str(textured_cover_path),
            TEST_MESSAGE,
            public_key_path="unused-public-key.pem",
            password=SYMMETRIC_PASSWORD,
        )


def test_locomotive_rejects_password_and_public_key_together(textured_cover_path):
    with pytest.raises(ValueError, match="either password encryption or public-key"):
        Locomotive().embed(
            [str(textured_cover_path)],
            raw_text=TEST_MESSAGE,
            public_key_path="unused-public-key.pem",
            password=SYMMETRIC_PASSWORD,
        )
