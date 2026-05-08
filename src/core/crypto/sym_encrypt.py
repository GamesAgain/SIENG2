import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

# AES-GCM parameters
DEFAULT_SALT_LENGTH = 16          # 128 bits
DEFAULT_NONCE_LENGTH = 12         # 96 bits, ideal for AES-GCM
DEFAULT_TAG_LENGTH = 16           # 128 bits authentication tag
DEFAULT_KEY_LENGTH = 32           # 256 bits for AES-256

# Argon2id parameters (RFC 9106 low memory: t=3, m=64MiB, p=4)
DEFAULT_MEMORY_COST = 65536    # 64 MiB (KiB)
DEFAULT_ITERATION_COST = 3
DEFAULT_PARALLELISM = 4

class SymmetricEncryption:
    def __init__(self):
        """
        Symmetric Encryption using AES-GCM and Argon2id
        """
        self.set_config()
        
    def set_config(self, config: dict = None):
        if config is None:
            config = {}
        
        self.config = config
        
        # AES-GCM
        self.salt_length = config.get('salt_length', DEFAULT_SALT_LENGTH)
        self.nonce_length = config.get('nonce_length', DEFAULT_NONCE_LENGTH)
        self.tag_length = config.get('tag_length', DEFAULT_TAG_LENGTH)  
        self.kdf_length = config.get('kdf_length', DEFAULT_KEY_LENGTH)
        
        # Argon2id
        self.memory_cost = config.get('memory_cost', DEFAULT_MEMORY_COST)
        self.iterations = config.get('iterations', DEFAULT_ITERATION_COST)
        self.parallelism = config.get('parallelism', DEFAULT_PARALLELISM)

    def encrypt(self, data: bytes, password: str) -> bytes:
        """
        Encrypt Data With AES-256-GCM: [Salt + Nonce + Ciphertext + Tag]
        """
        # 1. Prepare input [Validate & Convert]
        if not data:
            raise ValueError("Data cannot be empty")
        
        # 2. Random Salt 16 bytes & Nonce 12 bytes
        salt = os.urandom(self.salt_length)
        nonce = os.urandom(self.nonce_length)
        
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
        min_length = self.salt_length + self.nonce_length + self.tag_length
        if len(encrypted_data) < min_length:
            raise ValueError("Ciphertext is too short or corrupted")
            
        # 1. Split data into components [Salt, Nonce, Ciphertext, Tag]
        salt = encrypted_data[:self.salt_length]
        nonce = encrypted_data[self.salt_length:self.salt_length + self.nonce_length]
        ciphertext = encrypted_data[self.salt_length + self.nonce_length:]
        
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
            length=self.kdf_length,          # ต้องการ Key 32 bytes สำหรับ AES-256
            iterations=self.iterations,       # จำนวนรอบ (ตามมาตรฐาน RFC 9106)
            lanes=self.parallelism,            # จำนวน Thread ที่ใช้ประมวลผล
            memory_cost=self.memory_cost,  # ใช้ RAM 64 MB (ป้องกันการใช้ GPU สร้างฮาร์ดแวร์ถอดรหัสเฉพาะ)
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