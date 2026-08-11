"""Password-based symmetric encryption using AES-256-GCM and Argon2id.

The encrypted payload layout is::

    Argon2id salt | AES-GCM nonce | AES-GCM ciphertext and tag

A 256-bit AES key is derived from the password using Argon2id with a random
128-bit salt. AES-GCM provides authenticated encryption, allowing incorrect
passwords or modified ciphertext to be detected during decryption.

Supports encryption and decryption of arbitrary bytes using password-derived
AES-256 keys.
"""

import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

# AES-GCM parameters
AES_SALT_LENGTH = 16          # 128 bits
AES_NONCE_LENGTH = 12         # 96 bits, ideal for AES-GCM
AES_TAG_LENGTH = 16           # 128 bits authentication tag
AES_KEY_LENGTH = 32           # 256 bits for AES-256

# Argon2id parameters (RFC 9106 low memory: t=3, m=64MiB, p=4)
ARGON2ID_MEMORY_COST = 65536    # 64 MiB (KiB)
ARGON2ID_ITERATION_COST = 3
ARGON2ID_PARALLELISM = 4

class SymmetricEncryption:
    def __init__(self):
        """
        Symmetric Encryption using AES-GCM and Argon2id
        """
        pass

    def encrypt(self, data: bytes, password: str) -> bytes:
        """
        Encrypt Data With AES-256-GCM: [Salt + Nonce + Ciphertext + Tag]
        """
        # 1. Prepare input [Validate & Convert]
        if not data:
            raise ValueError("Data cannot be empty")
        
        # 2. Random Salt 16 bytes & Nonce 12 bytes (use module constants)
        salt = os.urandom(AES_SALT_LENGTH)
        nonce = os.urandom(AES_NONCE_LENGTH)
        
        # 3. Create Key with Argon2id
        key = self.derive_key(password, salt)
        aesgcm = AESGCM(key)
        
        # 4. Encrypt (ระบบจะแนบ Tag 16 bytes ต่อท้าย Ciphertext ให้เอง)
        ciphertext = aesgcm.encrypt(nonce, data, associated_data=None)
        
        # 5. Pack all components together
        encrypted_data = salt + nonce + ciphertext
        return encrypted_data

    def decrypt(self, encrypted_data: bytes, password: str) -> bytes:
        """
        Decrypt Data With AES-256-GCM: [Salt + Nonce + Ciphertext + Tag]
        """
        # Check minimum length: Salt(16) + Nonce(12) + Tag(16) = 44 bytes
        min_length = AES_SALT_LENGTH + AES_NONCE_LENGTH + AES_TAG_LENGTH
        if len(encrypted_data) < min_length:
            raise ValueError("Ciphertext is too short or corrupted")
            
        # 1. Split data into components [Salt, Nonce, Ciphertext, Tag]
        salt = encrypted_data[:AES_SALT_LENGTH]
        nonce = encrypted_data[AES_SALT_LENGTH:AES_SALT_LENGTH + AES_NONCE_LENGTH]
        ciphertext = encrypted_data[AES_SALT_LENGTH + AES_NONCE_LENGTH:]
        
        # 2. Create Key back to Salt 
        key = self.derive_key(password, salt)
        aesgcm = AESGCM(key)
        
        # 3. Decrypt (หากรหัสผ่านผิด หรือข้อมูลโดนดัดแปลงระหว่างซ่อนในภาพ ระบบจะโยน Exception ทันที)
        try:
            decrypted_data = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
            return decrypted_data
        except Exception as e:
            raise ValueError("Decryption failed: Invalid password or corrupted data") from e
    
    def derive_key(self, password: str, salt: bytes) -> bytes:
        """
        Argon2id สร้างกุญแจ 32 bytes จากรหัสผ่านและ Salt
        """
        
        if not password:
            raise ValueError("Password cannot be empty")
        
        password_bytes = password.encode('utf-8')
        
        kdf = Argon2id(
            salt=salt,
            length=AES_KEY_LENGTH,          # ต้องการ Key 32 bytes สำหรับ AES-256
            iterations=ARGON2ID_ITERATION_COST,       # จำนวนรอบ (ตามมาตรฐาน RFC 9106)
            lanes=ARGON2ID_PARALLELISM,            # จำนวน Thread ที่ใช้ประมวลผล
            memory_cost=ARGON2ID_MEMORY_COST,  # ใช้ RAM 64 MB (ป้องกันการใช้ GPU สร้างฮาร์ดแวร์ถอดรหัสเฉพาะ)
            ad=None,
            secret=None
        )
        return kdf.derive(password_bytes)

# --- ตัวอย่างการเรียกใช้งาน ---
if __name__ == "__main__":
    user_password = "Password2026"
    payload = b"Hello"
    
    cipher = SymmetricEncryption()
    
    # 1. เข้ารหัส -> ได้ Byte Array ก้อนยาวๆ เอาข้อมูลก้อนนี้แหละไปฝัง
    encrypted_payload = cipher.encrypt(payload, user_password)
    print(f"Encrypted ({len(encrypted_payload)} bytes): {encrypted_payload.hex()[:50]}...")
    
    # 2. ถอดรหัส -> สมมติว่าดึงก้อน Byte Array กลับมาจากภาพเรียบร้อยแล้ว
    decrypted_payload = cipher.decrypt(encrypted_payload, user_password)
    print(f"Decrypted: {decrypted_payload.decode('utf-8')}")