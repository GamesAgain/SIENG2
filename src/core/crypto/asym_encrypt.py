import os
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import serialization

# RSA Configuration
RSA_KEY_SIZE = 3072 # 3072 bits
ENCRYPTED_KEY_LENGTH = RSA_KEY_SIZE // 8  # 3072 bits = 384 bytes
PUBLIC_EXPONENT = 65537

# Default values for AES-GCM
AES_SALT_LENGTH = 16          # 128 bits
AES_NONCE_LENGTH = 12         # 96 bits for AES-GCM
AES_TAG_LENGTH = 16           # 128 bits authentication tag
AES_KEY_LENGTH = 32           # 256 bits for AES-256
    
class AsymmetricEncryption:
    def __init__(self):
        """
        Asymmetric Encryption using RSA-3072
        """
        pass

    def encrypt(self, plaintext: bytes, public_key) -> bytes:
        """
        Hybrid Encryption (RSA-3072 + AES-256-GCM)
        Return: [Encrypted AES Key (384 bytes)] + [Nonce (12 bytes)] + [Ciphertext + Tag]
        """
        # 1. Prepare input [Validate & Convert]
        if not plaintext:
            raise ValueError("Plaintext cannot be empty")
        
        # 2. Generate Master Key and derive sub-keys using HKDF (Session key + PRNG seed)
        session_key = os.urandom(AES_KEY_LENGTH)
        nonce = os.urandom(AES_NONCE_LENGTH)

        # 3. Encrypt with AES-256-GCM
        aesgcm = AESGCM(session_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)

        # 4. Encrypt Session Key with RSA Public Key (Use OAEP Padding)
        encrypted_session_key = public_key.encrypt(
            session_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        # 5. Combine Byte Array
        encrypted_data = encrypted_session_key + nonce + ciphertext
        return encrypted_data

    def decrypt(self, encrypted_data: bytes, private_key) -> bytes:
        """
        Hybrid Decryption (RSA-3072 + AES-256-GCM)
        Return: decrypted plaintext
        """
        # Check Minimum Length (Encrypted Key 384 + Nonce 12 + Tag 16 = 412 bytes)
        min_length = ENCRYPTED_KEY_LENGTH + AES_NONCE_LENGTH + AES_TAG_LENGTH
        if len(encrypted_data) < min_length:
            raise ValueError("Data is too short or corrupted")

        # 1. Split data structure
        encrypted_session_key = encrypted_data[:ENCRYPTED_KEY_LENGTH]
        nonce = encrypted_data[ENCRYPTED_KEY_LENGTH : ENCRYPTED_KEY_LENGTH + AES_NONCE_LENGTH]
        ciphertext = encrypted_data[ENCRYPTED_KEY_LENGTH + AES_NONCE_LENGTH:]

        # 2. Decrypt Session Key with RSA Private Key
        session_key = private_key.decrypt(
            encrypted_session_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        
        # 3. Use Session Key from RSA to decrypt with AES-GCM
        aesgcm = AESGCM(session_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)

        return plaintext



# ============================================
# Public Helper Functions
# ============================================

def generate_rsa_keypair():
    """Generate RSA Key Pair 3072-bit"""
    private_key = rsa.generate_private_key(
        public_exponent=PUBLIC_EXPONENT,
        key_size=RSA_KEY_SIZE,
    )
    public_key = private_key.public_key()
    return private_key, public_key

def get_private_bytes(private_key):
    """Get private key bytes in DER format"""
    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

def get_public_bytes(public_key):
    """Get public key bytes in DER format (เหมาะสำหรับเอาไปทำ Seed)"""
    return public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

def load_public_key(file_path: str):
    """Load public key from a file (Supports PEM, OpenSSH, DER)."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Public key file not found: {file_path}")
    
    with open(file_path, "rb") as key_file:
        key_data = key_file.read()
        
    # Try PEM format
    try:
        return serialization.load_pem_public_key(key_data)
    except ValueError:
        pass
        
    # Try OpenSSH format
    try:
        return serialization.load_ssh_public_key(key_data)
    except ValueError:
        pass
        
    # Try DER format
    try:
        return serialization.load_der_public_key(key_data)
    except ValueError:
        pass
        
    raise ValueError(f"Failed to load public key. Unsupported format or corrupted file: {file_path}")

def load_private_key(file_path: str, password: str = None):
    """Load private key from a file (Supports PEM, DER with optional string password)."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Private key file not found: {file_path}")
    
    password_bytes = password.encode('utf-8') if password else None

    with open(file_path, "rb") as key_file:
        key_data = key_file.read()
        
    # Try PEM format
    try:
        return serialization.load_pem_private_key(key_data, password=password_bytes)
    except TypeError as e:
        if "Password was not given" in str(e):
            raise ValueError("Private key is encrypted. A password is required.")
    except ValueError as e:
        if "Bad decrypt" in str(e) or "Incorrect password" in str(e):
            raise ValueError("Incorrect private key password.")
        pass
        
    # Try DER format
    try:
        return serialization.load_der_private_key(key_data, password=password_bytes)
    except TypeError as e:
        if "Password was not given" in str(e):
            raise ValueError("Private key (DER format) is encrypted. A password is required.")
    except ValueError as e:
        if "Bad decrypt" in str(e) or "Incorrect password" in str(e):
            raise ValueError("Incorrect private key password.")
        pass
        
    raise ValueError(f"Failed to load private key. Unsupported format or corrupted file: {file_path}")



# --- ตัวอย่างการเรียกใช้งาน ---
if __name__ == "__main__":
    hybrid = AsymmetricEncryption()
    user_private_password = b"Password123"
    # สมมติว่าผู้รับ(หรือระบบ) สร้างกุญแจเตรียมไว้
    print("Generating RSA-3072 Keys...")
    private_key, public_key = generate_rsa_keypair()
    
    # ถ้าผู้ใช้มีรหัสผ่านสำหรับกุญแจส่วนตัว
    if user_private_password:
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(user_private_password)
        )
    else:
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
    
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    # Save keys to files
    with open("private_key.pem", "wb") as f:
        f.write(private_bytes)
    with open("public_key.pem", "wb") as f:
        f.write(public_bytes)
        
    # ข้อมูลที่ต้องการซ่อน (อาจจะเป็นไฟล์ขนาดใหญ่ก็ได้ เพราะ AES รับไหวสบายๆ)
    payload = b"Hello"
    
    # ฝั่งส่ง: เข้ารหัสข้อมูลด้วย Public Key ของผู้รับ
    encrypted_payload = hybrid.encrypt(payload, public_key)
    print(f"\nEncrypted Package Size: {len(encrypted_payload)} bytes")
    # นำ encrypted_payload ไปโยนเข้าโมดูล LSB-Plus-Plus ของคุณได้เลยครับ!

    # ฝั่งรับ: ถอดรหัสด้วย Private Key ของตัวเอง
    decrypted_payload = hybrid.decrypt(encrypted_payload, private_key)
    print(f"Decrypted: {decrypted_payload.decode('utf-8')}")