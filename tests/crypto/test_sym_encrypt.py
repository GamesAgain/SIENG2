import pytest

from src.core.crypto.sym_encrypt import SymmetricEncryption


def test_encrypt_decrypt_roundtrip():
    cipher = SymmetricEncryption()

    original_data = b"Hello SIENG2"
    password = "Password2026"

    encrypted_data = cipher.encrypt(original_data, password)
    decrypted_data = cipher.decrypt(encrypted_data, password)

    assert decrypted_data == original_data


def test_encrypt_binary_data_roundtrip():
    cipher = SymmetricEncryption()
    
    with open("tests/crypto/images.jpg", "rb") as file:
        image_binary_data = file.read()
    
    original_data = image_binary_data
    password = "Password2026"

    encrypted_data = cipher.encrypt(original_data, password)
    decrypted_data = cipher.decrypt(encrypted_data, password)

    assert decrypted_data == original_data


def test_encrypt_thai_text_roundtrip():
    cipher = SymmetricEncryption()

    original_data = "ทดสอบระบบเข้ารหัส SIENG2".encode("utf-8")
    password = "รหัสผ่าน2026"

    encrypted_data = cipher.encrypt(original_data, password)
    decrypted_data = cipher.decrypt(encrypted_data, password)

    assert decrypted_data == original_data


def test_encrypt_empty_data_raises_error():
    cipher = SymmetricEncryption()

    with pytest.raises(ValueError) as exc_info:
        cipher.encrypt(b"", "Password2026")
    print(str(exc_info.value))


def test_encrypt_empty_password_raises_error():
    cipher = SymmetricEncryption()

    with pytest.raises(ValueError) as exc_info:
        cipher.encrypt(b"Hello SIENG2", "")
    print(str(exc_info.value))


def test_decrypt_wrong_password_raises_error():
    cipher = SymmetricEncryption()

    encrypted_data = cipher.encrypt(
        b"Secret SIENG2 data",
        "CorrectPassword"
    )

    with pytest.raises(ValueError) as exc_info:
        cipher.decrypt(
            encrypted_data,  
            "WrongPassword"
        )
    print(str(exc_info.value))


def test_decrypt_corrupted_data_raises_error():
    cipher = SymmetricEncryption()

    encrypted_data = cipher.encrypt(
        b"Secret SIENG2 data",
        "Password2026"
    )

    corrupted_data = bytearray(encrypted_data)
    corrupted_data[-1] ^= 0x01

    with pytest.raises(ValueError) as exc_info:
        cipher.decrypt(
            bytes(corrupted_data),
            "Password2026"
        )
    print(str(exc_info.value))