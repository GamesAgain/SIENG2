import io
import zipfile
from PIL import Image
from pathlib import Path
import random
import sys
import os
import math
import struct
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.core.crypto.sym_encrypt import SymmetricEncryption
from src.core.crypto.asym_encrypt import AsymmetricEncryption
from src.core.crypto.asym_encrypt import load_public_key, load_private_key

# Encrypt Mode constants SIENG2
MAGIC_NONE = b"0x00" # Steganography Encryption None
MAGIC_SYM = b"0x01" # Steganography Encryption Symmetric
MAGIC_ASYM = b"0x02" # Steganography Encryption Asymmetric

PNG_EOF_SIG = b'\x00\x00\x00\x00IEND\xaeB`\x82'  # PNG End-of-File marker
MAGIC_SIG = b'LOCO'                              # Fragment signature 
    
class Locomotive:
    def __init__(self):
        pass
    
    # ==================== Main Public Methods ====================
    
    def embed(self, cover_image_paths: list[str], file_paths: list[str] = None, raw_text: str = None, public_key_path: str = None, password: str = None) -> list[tuple[str, bytes]]:
        """
        Embed payload file into cover image using Locomotive algorithm
        """       
        # 1. Read File data    
        if raw_text is not None:
            file_data = raw_text.encode('utf-8')
            payload_package = self.pack_payload("secret_message.txt", file_data)
        else:
            if not file_paths:
                raise ValueError("No payload provided (neither file nor text).")
            file_data, out_file_paths = self.read_file(file_paths)
            payload_package = self.pack_payload(out_file_paths, file_data)
        
        
        # 2. Encrypt data
        encrypted_payload = self.encrypt_data(payload_package, public_key_path, password)
        
        # 3. Calculate number of parts and chunk size
        payload_length = len(encrypted_payload)
        num_parts, chunk_size = self.get_chunk_size(payload_length, cover_image_paths)
        
        # 4. Create session ID and blocks
        payload_blocks = self.create_session_block(num_parts, chunk_size, encrypted_payload, payload_length)
            
        # 5. Embed payload into cover images
        output_files = []
        if len(cover_image_paths) > 1:
            output_files = self.append_multifile(cover_image_paths, payload_blocks)
        else:
            output_files = self.append_onefile(cover_image_paths[0], payload_blocks)
            
        return output_files
    
    def extract(self, stego_image_paths: tuple[str], private_key_path: str = None, password: str = None) -> tuple[str, bytes]:
        """
        Extract payload file from stego images using Locomotive algorithm
        """
        
        all_sessions = {}
        session_order = []
        
        # Extract from each stego image
        for path in stego_image_paths:
            
            # 1. Read Image Data
            img_data = self.read_file(path)
            
            # 2. Extract encrypted payload from end of file
            eof_idx = img_data.find(PNG_EOF_SIG)
            encrypted_payload = img_data[eof_idx+len(PNG_EOF_SIG):]
            
            # 3. Extract payload blocks
            cursor = 0
            header_size = len(MAGIC_SIG) + 16  # 16 bytes =  session_id [4 bytes] +  part_index [4 bytes] +  total_parts [4 bytes] +  chunk_size [4 bytes]
            while True:
                
                # 4. Find magic signature 'LOCO'
                sig_idx = encrypted_payload.find(MAGIC_SIG, cursor)
                if sig_idx == -1: break # No more magic signatures found
                
                cursor = sig_idx
                if cursor + header_size > len(encrypted_payload): break # Not enough data for header
                
                # 5. Extract session ID, part index, total parts, and chunk size
                session_id, part_index, total_parts, chunk_size = struct.unpack('>IIII', encrypted_payload[cursor+len(MAGIC_SIG):cursor+header_size])
                cursor += header_size
                
                if cursor + chunk_size > len(encrypted_payload): break # Not enough data for chunk
                
                # 6. Extract chunk data
                chunk_data = encrypted_payload[cursor:cursor+chunk_size]
                
                # 7. Store chunk data
                if session_id not in all_sessions:
                    all_sessions[session_id] = { 'total_parts': total_parts, 'data': {} }
                    session_order.append(session_id) 
                all_sessions[session_id]['data'][part_index] = chunk_data
                
                cursor += chunk_size
                
        if not all_sessions:
            raise ValueError("No valid payload found. Are you sure these are stego images ?")
        
        # 8. Get the latest session
        latest_session_id = session_order[-1]
        expected_total_parts = all_sessions[latest_session_id]['total_parts']
        extracted_data = all_sessions[latest_session_id]['data']
        
        # Data Validation
        if len(extracted_data) != expected_total_parts:
            raise ValueError(f"Missing parts for the payload! Found {len(extracted_data)} of {expected_total_parts}.")
        
        # 9. Reconstruct the encrypted payload
        final_encrypted_payload = b"".join(extracted_data[i] for i in range(expected_total_parts))    
        
        # 10. Decrypt payload package
        payload_package = self.decrypt_data(final_encrypted_payload, private_key_path, password)
        
        output_path, extracted_file_data = self.unpack_payload(payload_package)
        
        return output_path, extracted_file_data
        
    def pack_payload(self, file_path: str, data: bytes) -> bytes:
        """
        Pack the payload with filename and data
        """
        file_name = os.path.basename(file_path).encode('utf-8')
        filename_length = len(file_name).to_bytes(2, 'big') # 2 bytes for filename length
        payload_package = filename_length + file_name + data
        
        return payload_package
    
    def unpack_payload(self, payload: bytes) -> tuple[str, bytes]:
        """
        Unpack the payload to get filename and data
        """
        filename_length = int.from_bytes(payload[:2], 'big')
        filename_ext = payload[2 : 2 + filename_length].decode('utf-8')
        file_data = payload[2 + filename_length :]
 
        file_name, ext = os.path.splitext(filename_ext)
        output_path = f"{file_name}_extracted{ext}"
        
        return output_path, file_data
    
    def get_chunk_size(self, payload_length: int, cover_image_path: tuple[str]) -> tuple[int, int]:
        """
        Calculate the number of parts and chunk size for embedding
        """
        num_parts = max(1, min(payload_length, 10)) if len(cover_image_path) == 1 else len(cover_image_path)
        chunk_size = math.ceil(payload_length / num_parts)
        
        return num_parts, chunk_size
    
    def create_session_block(self, num_parts: int, chunk_size: int, payload: bytes, payload_length: int) -> list[bytes]:
        """
        Create session blocks for embedding
        """
        session_id = random.getrandbits(32) # Session ID 4 bytes
        blocks = []
        for part_idx in range(num_parts):
            start_idx = part_idx * chunk_size
            end_idx = min(start_idx + chunk_size, payload_length)
            part_data = payload[start_idx:end_idx]
            part_size = len(part_data)
            
            header = struct.pack('>IIII', session_id, part_idx, num_parts, part_size) # 16 bytes
            blocks.append(MAGIC_SIG + header + part_data) # 20 bytes + data(part_size)
        return blocks
        
    def append_onefile(self, cover_path: str, blocks: list[bytes]) -> list[tuple[str, bytes]]:
        """
        Append PNG EOF marker to the end of the image data
        """
        random.shuffle(blocks)
        final_payload = b"".join(blocks)
        with open(cover_path, 'rb') as f:
            cover_img = f.read()
        stego_img =  cover_img + final_payload
        
        filename, ext = os.path.splitext(os.path.basename(cover_path))
                
        return [(f'{filename}_loco{ext}', stego_img)]
    
    def append_multifile(self, cover_image_path: list[str], blocks: list[bytes]) -> list[tuple[str, bytes]]:
        """
        Append PNG EOF marker to the end of each image data
        """
        
        output_files = []
        for i, path in enumerate(cover_image_path):
            with open(path, 'rb') as f:
                cover_img = f.read()
            stego_img =  cover_img + blocks[i]
            
            
            filename, ext = os.path.splitext(os.path.basename(path))
            output_files.append((f'{filename}_loco{ext}', stego_img))
                
        return output_files
    
    def encrypt_data(self, data: bytes, public_key_path: str = None, password: str = None):
        """
        Encrypt the data using either symmetric or asymmetric encryption
        """
        if password is not None and public_key_path is None:
            magic = MAGIC_SYM  # 0x01: Symmetric encryption
            encryptor = SymmetricEncryption()
            data_bytes = encryptor.encrypt(data, password)
        elif public_key_path is not None:
            magic = MAGIC_ASYM  # 0x02: Asymmetric encryption
            encryptor = AsymmetricEncryption()
            public_key = load_public_key(public_key_path)
            data_bytes = encryptor.encrypt(data, public_key)
        else:
            magic = MAGIC_NONE  # 0x00: No encryption
            data_bytes = data
            
        encrypted_data = magic + data_bytes
        return encrypted_data
    
    def decrypt_data(self, data: bytes, private_key_path: str = None, password: str = None):
        """
        Decrypt the data using either symmetric or asymmetric decryption
        """
        magic = data[:4]    
        header_length = len(magic)
        
        extracted_data = data[header_length:]
        if magic == MAGIC_SYM:
            if password is None:
                raise ValueError("Password required for symmetric encryption")

            decryptor = SymmetricEncryption()
            data_bytes = decryptor.decrypt(extracted_data, password)
            return data_bytes
        elif magic == MAGIC_ASYM:
            if not private_key_path:
                raise ValueError("Private key required for asymmetric decryption")
            
            # Check if encrypt private key with password
            password = password if password is not None else None
                
            decryptor = AsymmetricEncryption()
            private_key = load_private_key(private_key_path, password)
            data = decryptor.decrypt(extracted_data, private_key) 
            return data  
        elif magic == MAGIC_NONE:  # SEN: No encryption
            return extracted_data
            
        else:
            raise ValueError("Extraction failed: Invalid SIENG2 signature. Please verify your image and password.")
    
    # ==================== Utility Methods ====================
    def read_file(self, file_paths: list[str] | str) -> tuple[bytes, str] | bytes:
        
        if isinstance(file_paths, str):
            with open(file_paths, 'rb') as f:
                return f.read()

        if len(file_paths) == 1:
            path = file_paths[0]
            with open(path, 'rb') as f:
                return f.read(), path  # คืนค่า (ข้อมูลไฟล์แบบ bytes, path)
        else:
            zip_buffer = io.BytesIO()

            with zipfile.ZipFile(
                zip_buffer,
                'w',
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6
            ) as zipf:

                for path in file_paths:
                    path_obj = Path(path)
                    zipf.write(
                        path,
                        arcname=path_obj.name
                    )
            return zip_buffer.getvalue(), "secret_files.zip"  # คืนค่า (ข้อมูล zip แบบ bytes, ชื่อไฟล์ zip)
            
        
    def write_file(self, file_path: str, file_data: bytes) -> bytes:
        with open(file_path, 'wb') as f:
            return f.write(file_data)

# --- ตัวอย่างการเรียกใช้งาน ---       
if __name__ == "__main__":
    img = Image.new('RGB', (10, 10), (255, 0, 0))
    img.save('test0.png')
    img = Image.new('RGB', (10, 10), (255, 0, 0))
    img.save('test1.png')
    img = Image.new('RGB', (10, 10), (0, 255, 0))
    img.save('test2.png')
    img = Image.new('RGB', (10, 10), (0, 0, 255))
    img.save('test3.png')
    
    # --- Locomotive one cover image
    locomotive = Locomotive()
    locomotive.embed(["test0.png"], ["test.txt"], public_key_path="public_key.pem")
    locomotive.extract(["test0_loco.png"], private_key_path="private_key.pem", password="Password123")
    
    # --- Locomotive multiple cover images
    locomotive = Locomotive()
    locomotive.embed(["test1.png", "test2.png", "test3.png"], ["test.txt"], public_key_path="public_key.pem")
    locomotive.extract(["test1_loco.png", "test2_loco.png", "test3_loco.png"], private_key_path="private_key.pem", password="Password123")
    
