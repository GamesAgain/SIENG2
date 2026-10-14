"""LSB++: texture-adaptive LSB replacement with OPAP, a keyed embedding order and built-in encryption.

Bit naming: b0 = least significant bit ... b7 = most significant bit. "sample" = one R, G or B value.

Pipeline (embed; extract repeats steps 1-4 on the stego image and reads the bits back):
    1. Prepare      image -> RGB (RGBA keeps alpha untouched; alpha is never used for embedding).
    2. Texture      clear b0-b4 (& 224), BT.601 grayscale, then
                        S = w_g * clip(Sobel3x3 / (2*255*sqrt(2))) + w_e * clip(Entropy5x5 / log2(25)), S in [0, 1]
                    Only b5-b7 feed the analysis, and they are never modified, so the extractor
                    rebuilds exactly the same map from the stego image.
    3. Capacity     k bits per sample from S: k = 0 if S <= t1, 1 if S > t1, 2 if S > t2, 3 if S > t3.
                    Pixels with k = 0 (flat areas) are never touched.
    4. Order        pixels with k >= 1 are shuffled with a 128-bit seed = HKDF-SHA256(info "SIENG2_LSB_SHUFFLE")
                    of the password (password mode) or "Default" (no encryption). In RSA mode the RSA-encrypted
                    session key (key block) is embedded first along the order of the public key bytes, and the
                    remaining pixels are shuffled with the seed of the session key; the extractor reads the key
                    block, decrypts the session key with the private key and rebuilds the same order.
                    The order of the payload is therefore secret in the password and RSA modes. With no
                    encryption the seed is the constant "Default": anyone with SIENG2 can extract the message.
    5. Payload      MAGIC (3 B: SES / SEA / SEN) + LENGTH (4 B) + data encrypted with AES-256-GCM / Argon2id
                    (password) or AES-256-GCM with the session key of step 4 (RSA, nonce + ciphertext + tag;
                    the RSA-OAEP encrypted session key is the key block).
    6. Embed        k-bit LSB replacement, then OPAP (move by +-2^k when that brings the value closer to the
                    original; no effect at k = 1), then the MSB guard (if OPAP would change b5-b7, keep the
                    plain replacement value). Channels are written in R, G, B order.

Default parameters and where they come from (experiments/notes, random 50-image cover set, 2026-10-13):
    Sobel 3x3, entropy 5x5, weights 0.5 / 0.5
        Exp 4 and Exp 6: Sobel only, entropy only and weights 0:100 ... 100:0 were not better than 0.5 / 0.5.
    t1 = 0.1 (about 62 % of the pixels are used)
        Placement is what reduces the traces RS / SPA see (Exp 3, Exp 3b, k <= 1). Exp 7b swept t1 under a
        whole-image and an algorithm-aware detector: fewer pixels look cleaner to the whole-image detector but
        concentrate the payload for the aware one; the best trade-off was t1 = 0.1 - 0.125, and 0.1 keeps
        more capacity.
    t2 = 0.2, t3 = 0.3 (previously 0.4 / 0.7)
        Exp 9: chosen to raise capacity inside the same embedding area (median 0.75 -> 1.24 bits per sample)
        under the rule "100 % extraction and mean PSNR >= 50 dB at payload 0.1 and 0.25"; mean PSNR 56.5 /
        52.5 dB, lowest single image 51.2 dB. k = 2 and 3 are a capacity feature: the classic detectors
        (Chi-square, RS, SPA) only model b0, so they are not evidence that multi-bit embedding is safer.
    Changing any of these values changes the map: images embedded with other values cannot be extracted.
"""
import io
import os
from pathlib import Path
from PIL import Image
import cv2
import numpy as np
from typing import Callable, Optional
from skimage.filters.rank import entropy
from skimage.morphology import footprint_rectangle
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
 
from src.core.crypto.sym_encrypt import (
    AES_KEY_LENGTH,
    AES_NONCE_LENGTH,
    AES_SALT_LENGTH,
    AES_TAG_LENGTH,
    SymmetricEncryption,
)
from src.core.crypto.asym_encrypt import (
    AsymmetricEncryption, 
    load_public_key, 
    load_private_key, 
    get_public_bytes
)

DEFAULT_LSBPP_CONFIG = {
    'default_seed': 'Default',
    'pixel_shuffle': True,
    'gradient_analysis':
        {
            'enabled': True,
            'sobel_kernel': 3, # must be odd number >= 3
            'weight': 0.5
        },
    'local_entropy':
        {
            'enabled': True,
            'entropy_window': 5, # must be odd number >= 3
            'weight': 0.5
        },
    'capacity_threshold': { # see the module docstring (Exp 7b, Exp 9); was 0.7 / 0.4 / 0.1 before 2026-10-13
        '3bit': 0.3,
        '2bit': 0.2,
        '1bit': 0.1
    }
}

ALLOWED_IMAGE_EXTENSIONS = [
    # 1. กลุ่มที่คนใช้งานเยอะที่สุด (ภาพพื้นใส / ภาพถ่าย / ภาพบนเว็บ)
    ".png", 
    ".jpg", ".jpeg", ".webp",
    
    # 2. กลุ่มนามสกุลย่อยของ JPEG (เจอบ่อยเวลาเซฟรูปจากอินเทอร์เน็ต / Twitter / Facebook)
    ".jpe", ".jfif", 
    
    # 3. กลุ่มภาพมาตรฐานระบบ Windows และงานสแกนเอกสาร/งานพิมพ์
    ".bmp", 
    ".tiff", ".tif", 
    
    # 4. กลุ่มไอคอนมาตรฐาน
    ".ico"
]

# Encrypt Mode constants SIENG2 [SE = Steganography Encryption]
MAGIC_SYM = b"SES" # Symmetric Header
MAGIC_ASYM = b"SEA" # Asymmetric Header
MAGIC_NONE = b"SEN" # None Header
HEADER_BYTES = 7  # MAGIC (3 bytes) + LENGTH (4 bytes)

# IEND chunk เต็ม 12 bytes (length 0 + "IEND" + CRC) = จุดจบไฟล์ PNG จริง
# ใช้แยก bytes ที่ต่อท้ายหลัง IEND ออก (เช่น payload EOF ของ Locomotive)
PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB\x60\x82"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
COLOR_TYPE_DEPENDENT_CHUNKS = (b"PLTE", b"tRNS", b"bKGD", b"sBIT", b"hIST")

# สำหรับใช้ Update Progress Bar, Stats Message
ProgressCallback = Optional[Callable[[int, str], None]]
def update_progress(callBack: ProgressCallback, percent: int, message: str):
    if callBack is not None:
        callBack(percent, message)

def validate_encryption_mode(
    password: str = None,
    public_key_path: str = None,
) -> None:
    """Embed must use either password mode or public-key mode."""
    if password is not None and public_key_path is not None:
        raise ValueError(
            "Choose either password encryption or public-key encryption, not both."
        )

# ลูปเข้าไปอ่าน type chunks, chunk data ภายในภาพ PNG                
def iterate_png_chunks(raw_data_bytes: bytes):
    """ไล่อ่านไฟล์ PNG เป็น (chunk_type, full_chunk_bytes)
    (length 4B + type 4B + data + crc 4B) จนถึง IEND"""
    position = 8  # ข้าม PNG signature
    while position + 8 <= len(raw_data_bytes):
        length = int.from_bytes(raw_data_bytes[position:position + 4], "big")
        chunk_type = raw_data_bytes[position + 4:position + 8]
        end = position + 12 + length
        yield chunk_type, raw_data_bytes[position:end] # Return Chunk Type, Chunk Data
        position = end
        if chunk_type == b"IEND":
            break
        
class LSBPP:
    def __init__(self, config: dict = None):
        """
        Initialize LSB++ steganography with configuration
        """
        
        self.set_config(config or DEFAULT_LSBPP_CONFIG)
        
    def set_config(self, config: dict):
        """
        Set configuration for LSB++ steganography
        """
        self.config = config
        
        # --- Gradient Analysis Config ---
        self.gradient_analysis = self.config.get('gradient_analysis', DEFAULT_LSBPP_CONFIG['gradient_analysis'])
        self.gradient_enabled = self.gradient_analysis.get('enabled')
        self.sobel_kernel_size = self.gradient_analysis.get('sobel_kernel')
        self.gradient_weight = self.gradient_analysis.get('weight')
        
        # --- Local Entropy Config ---
        self.local_entropy = self.config.get('local_entropy', DEFAULT_LSBPP_CONFIG['local_entropy'])
        self.entropy_enabled = self.local_entropy.get('enabled')
        self.entropy_window_size = self.local_entropy.get('entropy_window')
        self.entropy_weight = self.local_entropy.get('weight')
        
       # --- Other settings ---
        self.capacity_threshold = self.config.get('capacity_threshold', DEFAULT_LSBPP_CONFIG['capacity_threshold'])  # set capacity threshold
        self.default_seed = self.config.get('default_seed', DEFAULT_LSBPP_CONFIG['default_seed']) # set default seed
        self.pixel_shuffle = self.config.get('pixel_shuffle', DEFAULT_LSBPP_CONFIG['pixel_shuffle']) # set pixel order
        
    # ==================== Main Public Methods ====================

    def embed(
        self,
        cover_image_path: str,
        message: str,
        public_key_path: str = None,
        password: str = None,
        progress_callback: ProgressCallback = None
        ) -> tuple[str, bytes]:
        """
        Embed payload message and return (PNG filename, image bytes).
        """
        # 0. Validate encryption mode
        validate_encryption_mode(password, public_key_path)
        
        # 1. Prepare cover image
        update_progress(progress_callback, 5, "Preparing cover image...")
        cover_image = self.prepare_image(cover_image_path)
        base_file_name = Path(cover_image_path).stem
        
        # 2. Analyze cover image [gradient_map, entropy_map] -> texture_surface
        update_progress(progress_callback, 10, "Analyzing texture surface...")
        texture_surface = self.analyze_cover_image(cover_image)
        
        # 3. Capacity calculation
        update_progress(progress_callback, 40, "Calculating capacity map...")
        capacity_map = self.calculate_capacity(texture_surface)
        
        # 4. Get seed
        update_progress(progress_callback, 45, "Deriving seed...")
        seed = self.get_seed(password=password, public_key_path=public_key_path)
            
        # 5. Get pixel order
        update_progress(progress_callback, 50, "Pixel ordering...")
        pixel_order = self.get_pixel_order(capacity_map, seed) 
        
        # 6. Encode message and pack payload (Key block + Header + Payload)
        update_progress(progress_callback, 55, "Encrypting & packing payload...")
        raw_payload = message.encode('utf-8')
        session_key = os.urandom(AES_KEY_LENGTH) if public_key_path is not None else None
        key_block, packed_payload = self.pack_data(raw_payload, password, public_key_path, session_key)

        # 7. Validate capacity before embed (key block + 1 byte: it ends on a whole pixel)
        update_progress(progress_callback, 57, "Validating capacity...")
        key_block_bytes = len(key_block) + 1 if key_block else 0
        self.validate_capacity(packed_payload, capacity_map, password, public_key_path, extra_bytes=key_block_bytes)

        # 8. RSA mode: key block takes the first pixels, the payload is shuffled by the session key
        key_order = None
        if key_block:
            update_progress(progress_callback, 58, "Ordering key block...")
            key_order, _ = self.split_pixel_order(pixel_order, capacity_map, len(key_block) * 8)
            seed = self.get_seed(session_key=session_key)
            pixel_order = self.get_pixel_order(capacity_map, seed, exclude=key_order)

        # 9. Embed message (key block first, then header + payload)
        update_progress(progress_callback, 60, "Embedding message bits...")
        stego_image = cover_image
        if key_block:
            stego_image = self.lsb_replacement_OPAP(stego_image, key_block, key_order, capacity_map)
        stego_image = self.lsb_replacement_OPAP(stego_image, packed_payload, pixel_order, capacity_map)

        # 10. Merge Stego Image bytes
        update_progress(progress_callback, 92, "Merging with original PNG structure...")
        stego_image_bytes = self.merge_stego_bytes(cover_image_path, stego_image)

        # 11. Export File name (always .png)
        stego_file_name = f"{base_file_name}_stego.png"
        update_progress(progress_callback, 100, "Embedding complete.")

        return stego_file_name, stego_image_bytes
    

    def merge_stego_bytes(self, cover_image_path: str, stego_image: Image) -> bytes:
        """ Merge Stego Image (LSB++) กับ Original Cover Image เพื่อรักษาของเดิมของ cover ไว้ครับ:
        1) สำหรับ PNG: รักษา ancillary chunks เดิม (tEXt/iTXt + custom chunks) และ EOF payload
            ยกเว้น chunk ที่ผูกกับ color type เดิม ถ้า prepare_image แปลง mode ไปแล้ว
        2) สำหรับรูปแบบอื่น: return PNG ใหม่ที่ได้จากการ embed โดยตรง
        """
        
        # 1. Create a buffer to store the new PNG stego image
        buffer = io.BytesIO()
        stego_image.save(buffer, format="PNG")
        new_png_bytes = buffer.getvalue()

        # 2. Check if original is PNG
        original_ext = Path(cover_image_path).suffix.lower()
        if original_ext == '.png':
            new_chunks = list(iterate_png_chunks(new_png_bytes))
            original_raw = Path(cover_image_path).read_bytes()

            # Check if prepare_image changed the color mode (=> IHDR color type) from the original.
            with Image.open(cover_image_path) as original_image:
                original_mode = original_image.mode
            color_type_changed = original_mode != stego_image.mode

            excluded_types = {b"IHDR", b"IDAT", b"IEND"}
            if color_type_changed:
                excluded_types |= set(COLOR_TYPE_DEPENDENT_CHUNKS)

            # Keep the original non-pixel chunks
            kept_chunks = [
                chunk_data for chunk_type, chunk_data in iterate_png_chunks(original_raw)
                if chunk_type not in excluded_types
            ]
            IEND_idx = original_raw.find(PNG_IEND)
            tail = original_raw[IEND_idx + len(PNG_IEND):] if IEND_idx != -1 else b""

            # Merge: signature + IHDR + [kept chunks] + New IDAT + IEND + tail
            PNG_bytes = bytearray(PNG_SIGNATURE)
            inserted = False
            for chunk_type, chunk in new_chunks:
                if chunk_type == b"IDAT" and not inserted:
                    PNG_bytes += b"".join(kept_chunks)
                    inserted = True
                PNG_bytes += chunk
            PNG_bytes += tail
            return bytes(PNG_bytes)

        # 3. If not PNG, just return the new PNG bytes
        return new_png_bytes


    def extract(
        self,
        stego_image_path: str,
        private_key_path: str = None,
        password: str = None,
        progress_callback: ProgressCallback = None
        ) -> str:
        """
        Extract payload message from stego image using LSB++ algorithm
        """

        # 1. Prepare stego image
        update_progress(progress_callback, 5, "Preparing stego image...")
        stego_image = self.prepare_image(stego_image_path)

        # 2. Analyze stego image [gradient_map, entropy_map] -> texture_surface
        update_progress(progress_callback, 10, "Analyzing texture surface...")
        texture_surface = self.analyze_cover_image(stego_image)

        # 3. Capacity calculation
        update_progress(progress_callback, 40, "Calculating capacity map...")
        capacity_map = self.calculate_capacity(texture_surface)

        # 4. Get seed
        update_progress(progress_callback, 50, "Deriving seed...")
        seed = self.get_seed(password=password, private_key_path=private_key_path)

        # 5. Get pixel order
        update_progress(progress_callback, 55, "Pixel ordering...")
        pixel_order = self.get_pixel_order(capacity_map, seed)

        # 6. RSA mode: read the key block, then switch to the session key order
        key_block = None
        if private_key_path is not None:
            update_progress(progress_callback, 58, "Reading key block...")
            key_block, pixel_order = self.read_key_block(stego_image, pixel_order, capacity_map, private_key_path, password)

        # 7. Extract message
        update_progress(progress_callback, 60, "Extracting & decrypting message...")
        extracted_message = self.message_extraction(stego_image, pixel_order, capacity_map, private_key_path, password, key_block)
        update_progress(progress_callback, 100, "Extraction complete.")

        return extracted_message
    

    # ==================== Image Preparation Methods ====================

    def prepare_image(self, image_path: str) -> Image.Image:
        """
        Prepare image for LSB++ algorithm
        """
        
        # Check if image exists
        if image_path is None:
            raise ValueError("Image path is required")
        
        if not Path(image_path).exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        # 1. Open image with Pillow
        with Image.open(image_path) as img:
            
            # 2. List of modes that have Alpha Channel
            # RGBA, LA (Grayscale+Alpha), PA (Palette+Alpha), 
            # RGBa (Premultiplied), La (L+Premultiplied)
            alpha_modes = ('RGBA', 'LA', 'PA', 'RGBa', 'La')
            
            has_alpha = False
            
            # Check if image has alpha channel
            if img.mode in alpha_modes:
                has_alpha = True
            elif img.mode == 'P' and 'transparency' in img.info:
                # Palette mode with transparency info
                has_alpha = True
            elif img.mode.startswith('I;16') or img.mode in ('I', 'F'):
                # Numeric modes (Integer/Float) normally don't have Alpha
                has_alpha = False
            
            # 3. Conversion Logic
            if has_alpha:
                # If original has Alpha, convert to RGBA (4x8-bit)
                new_img = img.convert('RGBA')
            else:
                # If no Alpha (1, L, P, RGB, CMYK, YCbCr, LAB, HSV, I, F)
                # Convert to RGB (3x8-bit)
                new_img = img.convert('RGB')
            
        return new_img

    # ==================== Analysis Methods ====================

    def analyze_cover_image(self, cover_image: Image.Image) -> np.ndarray:
        """
        Analyze cover image and return gradient map and entropy map
        
        Returns:
            texture_surface: Combined texture surface (gradient + entropy)
        """
        gradient_enabled = self.gradient_enabled
        entropy_enabled = self.entropy_enabled
        
        # If both gradient and entropy are disabled, use maximum capacity of each pixel
        if not gradient_enabled and not entropy_enabled:
            w, h = cover_image.size
            return np.ones((h, w))  # Embed 3 bits per pixel
         
        # 1. Convert to grayscale
        gray_array = self.convert_to_grayscale(cover_image)

        # 2. Calculate gradient map if enabled
        gradient_map = self.calculate_gradient(gray_array) if gradient_enabled else None

        # 3. Calculate entropy map if enabled
        entropy_map = self.calculate_local_entropy(gray_array) if entropy_enabled else None
        
        # 4. Calculate texture surface
        texture_surface = self.calculate_surface(gradient_map, entropy_map)

        return texture_surface
    
    def convert_to_grayscale(self, cover_image: Image.Image) -> np.ndarray:
        """
        Convert cover image to grayscale [BT.601].
        """
        # Clean LSB from all pixels
        rgb_image = cover_image.convert('RGB')
        img_array = np.array(rgb_image).copy()
        img_array &= 224
        
        # Convert to grayscale
        return cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

    def calculate_gradient(self, gray_array: np.ndarray) -> np.ndarray:
        """
        Calculate gradient map for cover image by Sobel operator
        """
        
        # Calculate X & Y Gradient
        grad_x = cv2.Sobel(gray_array, cv2.CV_64F, 1, 0, ksize=self.sobel_kernel_size)
        grad_y = cv2.Sobel(gray_array, cv2.CV_64F, 0, 1, ksize=self.sobel_kernel_size)  
        
        # Calculate Gradient Magnitude
        magnitude = np.sqrt(grad_x**2 + grad_y**2)
        
        return magnitude

    def calculate_local_entropy(self, gray_array: np.ndarray) -> np.ndarray:
        """
        Calculate local entropy map for cover image
        """
        # Create window default 5x5
        size = (self.entropy_window_size, self.entropy_window_size)
        window_size = footprint_rectangle(size)
        
        # Calculate Local Entropy
        entropy_map = entropy(gray_array, window_size)
        
        return entropy_map
    
    def calculate_surface(
        self,
        gradient_map: np.ndarray | None,
        entropy_map: np.ndarray | None,
    ) -> np.ndarray:
        """
        Calculate surface map for cover image.
        """
        # Dynamic Weight
        if gradient_map is not None and entropy_map is not None:
            weight_gradient = self.gradient_weight
            weight_entropy = self.entropy_weight
        elif gradient_map is not None:
            weight_gradient = 1.0
            weight_entropy = 0.0
        elif entropy_map is not None:
            weight_gradient = 0.0
            weight_entropy = 1.0
        else:
            weight_gradient = 0.0
            weight_entropy = 0.0

        # set surface map to zero
        surface = np.zeros_like(entropy_map if entropy_map is not None else gradient_map)

        if gradient_map is not None and weight_gradient > 0:
            grad_max = 2 * 255 * np.sqrt(2)
            grad_norm = np.clip(gradient_map / grad_max, 0.0, 1.0)
            surface += weight_gradient * grad_norm
            
        if entropy_map is not None and weight_entropy > 0:
            window = self.entropy_window_size
            ent_max = np.log2(window * window)
            ent_norm = np.clip(entropy_map / ent_max, 0.0, 1.0)
            surface += weight_entropy * ent_norm
            
        return np.clip(surface, 0.0, 1.0)
    
    def calculate_capacity(self, texture_surface: np.ndarray) -> np.ndarray:
        """
        Calculate capacity map for cover image
        """
        # Get capacity thresholds from config
        threshold_3bit = self.capacity_threshold['3bit']
        threshold_2bit = self.capacity_threshold['2bit']
        threshold_1bit = self.capacity_threshold['1bit']
        
        # Calculate capacity for each pixel
        capacity_map = np.zeros(texture_surface.shape, dtype = np.uint8)
        
        capacity_map[texture_surface > threshold_1bit] = 1
        capacity_map[texture_surface > threshold_2bit] = 2
        capacity_map[texture_surface > threshold_3bit] = 3
        
        return capacity_map.ravel() # Return flattened array
    
    def get_pixel_order(self, capacity_map: np.ndarray, seed: int, exclude: np.ndarray = None) -> np.ndarray:
        """
        Get pixel order for embedding
        exclude: pixels already used by the key block (RSA mode)
        """
        # Get shuffle index of pixels with capacity > 0
        rng = np.random.default_rng(seed)
        flat_idx = np.where(capacity_map > 0)[0]

        if exclude is not None:
            flat_idx = np.setdiff1d(flat_idx, exclude) # sorted like np.where, so the order stays reproducible

        if self.pixel_shuffle:
            rng.shuffle(flat_idx)

        return flat_idx

    def split_pixel_order(self, pixel_order: np.ndarray, capacity_map: np.ndarray, bits: int) -> tuple[np.ndarray, np.ndarray]:
        """
        Split pixel order into the first pixels that hold `bits` bits and the rest.
        The split is on a whole pixel, so the key block never shares a pixel with the payload.
        """
        pixel_bits = np.cumsum(capacity_map[pixel_order].astype(np.int64) * 3) # 3 channels, each uses k bits

        if len(pixel_bits) == 0 or bits > pixel_bits[-1]:
            raise ValueError("Image capacity is too small to contain the key block.")

        count = int(np.searchsorted(pixel_bits, bits)) + 1 # first pixel where the running total reaches bits
        return pixel_order[:count], pixel_order[count:]

    def message_extraction(self, stego_image: Image.Image, pixel_order: np.ndarray, capacity_map: np.ndarray, private_key_path: str = None, password: str = None, key_block: bytes = None) -> str:
        """
        Extract message from stego image
        """
        total_capacity_bits = int(np.sum(capacity_map[pixel_order])) * 3 # pixels left for header + payload
        header_bits = HEADER_BYTES * 8

        if header_bits > total_capacity_bits:
            raise ValueError("Extraction failed: image capacity too small to contain a valid header.")

        # 1. Read the header first (magic + length) to find the total message size
        header_bytes = self.lsb_extract(stego_image, pixel_order, capacity_map, max_bits=header_bits, total_bits=None)

        if header_bytes[:3] not in (MAGIC_SYM, MAGIC_ASYM, MAGIC_NONE):
            raise ValueError("Extraction failed: Invalid SIENG2 signature. Please verify your image and password.")

        message_length = int.from_bytes(header_bytes[3:HEADER_BYTES], byteorder='big')
        required_bits = (HEADER_BYTES + message_length) * 8

        # 2. Validate the extracted length
        if required_bits > total_capacity_bits:
            raise ValueError("Extraction failed: decoded length exceeds image capacity. Please verify your image and password.")

        # 3. Perform a second read for the exact required bits (header + payload)
        extracted_bytes = self.lsb_extract(stego_image, pixel_order, capacity_map, max_bits=required_bits, total_bits=required_bits)
        data_bytes = self.unpack_data(extracted_bytes, private_key_path, password, key_block)

        # Decode message
        try:
            message_extracted = data_bytes.decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError("Failed to decode message. The extracted data is not valid UTF-8 text.")

        return message_extracted

    def read_key_block(self, stego_image: Image.Image, pixel_order: np.ndarray, capacity_map: np.ndarray, private_key_path: str, password: str = None) -> tuple[bytes, np.ndarray]:
        """
        Read the RSA-encrypted session key (key block) and return it with the payload pixel order
        """
        # 1. Key block length = RSA key size (256 / 384 / 512 bytes)
        private_key = load_private_key(private_key_path, password)
        key_bits = (private_key.key_size // 8) * 8

        # 2. Read the key block along the public key order
        try:
            key_order, _ = self.split_pixel_order(pixel_order, capacity_map, key_bits)
        except ValueError:
            raise ValueError("Extraction failed: image capacity too small to contain a valid key block.")
        key_block = self.lsb_extract(stego_image, key_order, capacity_map, max_bits=key_bits, total_bits=key_bits)

        # 3. Decrypt the session key (wrong key or no message -> RSA-OAEP fails)
        try:
            session_key = AsymmetricEncryption().decrypt_session_key(key_block, private_key)
        except ValueError:
            raise ValueError("Extraction failed: Invalid SIENG2 signature. Please verify your image and private key.")

        # 4. Payload order from the session key, without the key block pixels
        seed = self.get_seed(session_key=session_key)
        return key_block, self.get_pixel_order(capacity_map, seed, exclude=key_order)

    def lsb_replacement_OPAP(self, cover_image: Image.Image, data: bytes, pixel_order: np.ndarray, capacity_map: np.ndarray):
        """
        Executes Adaptive LSB embedding across RGB channels using LSB Replacement + OPAP (Optimal Pixel Adjustment Process). 
        Dynamically adjusts the embedded bits (k) based on image texture surface
        """
        # 1. Prepare cover array 1D
        img_array = np.array(cover_image)
        channels = img_array.shape[2] 
        
        # 2. Separate RGB and Alpha channels
        if channels == 4:
            rgb_chanel = img_array[:, :, :3]
            alpha_channel = img_array[:, :, 3]
        else:
            rgb_chanel = img_array
            alpha_channel = None  
            
        rgb_flat = rgb_chanel.ravel()
        
        # 3. Convert bytes to numpy array (0 - 255, zero-copy)
        byte_array = np.frombuffer(data, dtype=np.uint8)
        message_bits = np.unpackbits(byte_array) # Unpack bytes to bits
        
        bit_idx = 0
        total_bits = len(message_bits)
        
        # 4. Embed Bits
        for px in pixel_order:
            if bit_idx >= total_bits:
                break
            
            # Get embedded bits (k)
            k = int(capacity_map[px])
            
            # Iterate through R, G, B channels
            for channel in range(3):
                if bit_idx < total_bits:
                    
                    idx = px * 3 + channel
                    px_origin = rgb_flat[idx]
                    
                    actual_k = min(k, total_bits - bit_idx) # trap in case there are less than k
                    
                    # Extract bits to integer (bits_value)
                    chunk = message_bits[bit_idx : bit_idx + actual_k]
                    bits_value = 0
                    for bit in chunk:
                        bits_value = (bits_value << 1) | bit
                    
                    # --- LSB Replacement ---
                    clear_mask = 255 - ((1 << actual_k) - 1) # create mask with bitwise shift (2^k - 1)
                    px_replace = int((px_origin & clear_mask) | bits_value)
                    
                    # --- OPAP (Optimal Pixel Adjustment Process) ---
                    delta = px_replace - int(px_origin)
                    threshold = int(1 << (actual_k - 1)) # 2^(k-1)
                    shift_value = int(1 << actual_k)     # 2^k
                    
                    optimal_px = px_replace
                    if delta > threshold and (px_replace - shift_value) >= 0:
                        optimal_px = px_replace - shift_value
                    elif delta < -threshold and (px_replace + shift_value) <= 255:
                        optimal_px = px_replace + shift_value
                        
                    # --- MSB Guard Check ---
                    # 224 คือ Mask ล็อค 3 บิตบนสุด (1110 0000)
                    if (optimal_px & 224) != (px_origin & 224):
                        rgb_flat[idx] = px_replace 
                    else:
                        rgb_flat[idx] = optimal_px
                        
                    bit_idx += actual_k
                else:
                    break
                
        # 5. Rebuild Image
        stego_rgb = rgb_flat.reshape(rgb_chanel.shape)
        
        if alpha_channel is not None:
            stego_array = np.dstack((stego_rgb, alpha_channel))
        else:
            stego_array = stego_rgb
            
        # 6. Convert back to Image
        stego_image = Image.fromarray(stego_array)
        
        return stego_image

    def lsb_extract(self, stego_image: Image.Image, pixel_order: np.ndarray, capacity_map: np.ndarray, max_bits: int = None, total_bits: int = None) -> bytes:
        """
        Extract message from stego image.
        Dynamically adjusts the extraction bits (k) based on image texture surface
        max_bits: Bits to read (None = read all supported by pixel_order).
        total_bits: Total length of payload. If None, won't shrink chunk at end.
        """
        # 1. Convert image to numpy array
        img_array = np.array(stego_image)
        channels = img_array.shape[2]

        # 2. Separate RGB and Alpha channels
        if channels == 4:
            rgb_flat = img_array[:, :, :3].ravel()
        else:
            rgb_flat = img_array.ravel()
        
        if max_bits is None:
            sum_k = int(np.sum(capacity_map))
            max_bits = sum_k * 3  # worst case: 3 channels, each uses k bits
            
        extracted_bits = np.zeros(max_bits, dtype=np.uint8)
        bit_count = 0
            
        # 3. Extract bits from pixels (stop at max_bits)
        for px in pixel_order:
            if max_bits is not None and bit_count >= max_bits:
                break
            
            # Get extraction bits (k)
            k = int(capacity_map[px])
        
            # Iterate through R, G, B channels
            for channel in range(3):
                if bit_count >= max_bits:
                    break
                
                idx = px * 3 + channel
                value = rgb_flat[idx]
                
                # If total_bits is known (end of payload), shrink k. Otherwise read full k.
                actual_k = k if total_bits is None else min(k, total_bits - bit_count)
                
                # Extract embedding bits
                extraction_mask = (1 << actual_k) - 1
                extracted_value = value & extraction_mask
                
                # Convert the extracted integer back into an array of bits (0, 1)
                # Extract from MSB down to LSB to preserve the original embedded sequence (chunk). 
                for i in range(actual_k - 1, -1, -1):
                    if bit_count < max_bits:
                        extracted_bits[bit_count] = (extracted_value >> i) & 1
                        bit_count += 1

        # 4. Convert bits to bytes
        extracted_bytes = np.packbits(extracted_bits)

        return bytes(extracted_bytes)
    
    # ==================== Utility Methods ====================

    def validate_capacity(self, data_package: bytes, capacity_map: np.ndarray, password: str = None, public_key_path: str = None, extra_bytes: int = 0) -> None:
        """
        Raise ValueError if data_package exceeds the image's embeddable capacity.
        extra_bytes: bytes embedded outside data_package (RSA key block + 1 byte for its last pixel)
        """
        total_capacity_bits = int(np.sum(capacity_map)) * 3
        required_bytes = len(data_package) + extra_bytes
        required_bits = required_bytes * 8 # bits length

        if required_bits > total_capacity_bits:
            supported_bytes = total_capacity_bits // 8
            excess_bytes = required_bytes - supported_bytes
            
            # ตรวจสอบ Magic Bytes เพื่อระบุสาเหตุของ Overhead ให้ชัดเจน
            magic = data_package[:3]
            overhead_bytes = estimate_overhead_bytes(password, public_key_path)
            if magic == MAGIC_SYM:
                overhead_info = "password encryption overhead"
            elif magic == MAGIC_ASYM:
                overhead_info = "public key encryption overhead"
            else:
                overhead_info = "header overhead"

            # โยน Error เป็น Multi-line String เพื่อให้ Dialog นำไปแสดงผลได้สวยงามและอ่านง่าย
            raise ValueError(
                f"Image capacity is {supported_bytes} bytes, but data requires {required_bytes} bytes.\n"
                f"(Your data is over limit by {excess_bytes} bytes)\n\n"
                f"Why is this happening?\n"
                f"The required size includes:\n- your secret message ({required_bytes - overhead_bytes} bytes)\n- {overhead_info} ({overhead_bytes} bytes).\n\n"
                f"Action Required (Choose one):\n"
                f"1. Reduce your message size by at least {excess_bytes} bytes.\n"
                f"2. Disable encryption to free up overhead space.\n"
                f"3. Select a cover image with a larger capacity."
            )

    def get_seed(
        self,
        password: str = None,
        public_key_path: str = None,
        private_key_path: str = None,
        session_key: bytes = None,
    ) -> int:
        """Generate the pixel seed from the selected encryption credential (or the RSA session key)."""
        validate_encryption_mode(password, public_key_path)
        if public_key_path is not None and private_key_path is not None:
            raise ValueError("Choose either a public key or a private key, not both.")

        if session_key is not None:
            seed = session_key
        elif public_key_path is not None:
            public_key = load_public_key(public_key_path)
            seed = get_public_bytes(public_key)
        elif private_key_path is not None:
            private_key = load_private_key(private_key_path, password)
            seed = get_public_bytes(private_key.public_key())
        elif password is not None:
            seed = password.encode("utf-8")
        else:
            seed = self.default_seed.encode("utf-8")
            
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=16,   # 128-bit seed
            salt=None,
            info=b"SIENG2_LSB_SHUFFLE",
        )

        seed_bytes = hkdf.derive(seed)
        
        return int.from_bytes(seed_bytes, "big")

    def pack_data(self, data: bytes, password: str = None, public_key_path: str = None, session_key: bytes = None) -> tuple[bytes, bytes]:
        """
        Build complete payload: [MAGIC (3 bytes) + LENGTH (4 bytes) + ENCRYPTED_DATA]
        Returns: (key_block, data_package); key_block is the RSA-encrypted session key (b"" if not RSA mode)
        """
        validate_encryption_mode(password, public_key_path)
        key_block = b""

        # 1. Process message based on encryption mode
        if password is not None:
            magic = MAGIC_SYM  # SES: Symmetric encryption
            encryptor = SymmetricEncryption()
            data_bytes = encryptor.encrypt(data, password)
        elif public_key_path is not None:
            magic = MAGIC_ASYM  # SEA: Asymmetric encryption
            encryptor = AsymmetricEncryption()
            public_key = load_public_key(public_key_path)
            encrypted = encryptor.encrypt(data, public_key, session_key)

            # Split [Encrypted Key | Nonce + Ciphertext + Tag]; the key is embedded as the key block
            key_length = public_key.key_size // 8
            key_block, data_bytes = encrypted[:key_length], encrypted[key_length:]
        else:
            magic = MAGIC_NONE  # SEN: No encryption
            data_bytes = data
            
        # 2. Create header with message length
        message_length = len(data_bytes)
        length_bytes = message_length.to_bytes(4, byteorder='big')
        header = magic + length_bytes
        
        data_package = header + data_bytes

        return key_block, data_package

    def unpack_data(self, data: bytes, private_key_path: str = None, password: str = None, key_block: bytes = None) -> bytes:
        """
        Parse header and decrypt the payload.
        Returns: Decrypted plaintext bytes.
        """
        # 1. Extract header components
        magic = data[:3]  # 3 bytes: SES, SEA, or SEN
        message_length = int.from_bytes(data[3:7], byteorder='big')  # 4 bytes length
        header_length = len(magic) + 4  # Total header size
        
        # 2. Extract encrypted message data
        total_length = header_length + message_length
        extracted_data = data[header_length:total_length]
        
        # 3.Handle different encryption modes 
        if magic == MAGIC_SYM:  # SES: Symmetric encryption
            if password is None:
                raise ValueError("Password required for symmetric encryption")

            decryptor = SymmetricEncryption()
            data_bytes = decryptor.decrypt(extracted_data, password)
            return data_bytes
        elif magic == MAGIC_ASYM:
            if not private_key_path or not key_block:
                raise ValueError("Private key required for asymmetric decryption")

            decryptor = AsymmetricEncryption()
            private_key = load_private_key(private_key_path, password)
            plaintext  = decryptor.decrypt(key_block + extracted_data, private_key) # [Encrypted Key | Nonce + Ciphertext + Tag]
            return plaintext  
        elif magic == MAGIC_NONE:  # SEN: No encryption
            return extracted_data
            
        else:
            raise ValueError("Extraction failed: Invalid SIENG2 signature. Please verify your image and password.")
            
    def get_total_capacity_bits(self, cover_image_path: str) -> int:
        cover_image = self.prepare_image(cover_image_path)
        texture_surface = self.analyze_cover_image(cover_image)
        capacity_map = self.calculate_capacity(texture_surface)
        return int(np.sum(capacity_map)) * 3

# --- External function ---    
def estimate_overhead_bytes(password: str = None, public_key_path: str = None) -> int:
    """
    Estimate the pack_data() byte overhead for the selected encryption mode.
    """
    validate_encryption_mode(password, public_key_path)

    if password is not None:
        # Symmetric: HEADER + salt(16) + nonce(12) + tag(16)
        return HEADER_BYTES + AES_SALT_LENGTH + AES_NONCE_LENGTH + AES_TAG_LENGTH

    if public_key_path is not None:
        # Asymmetric: HEADER + RSA-encrypted session key (key block, actual key size) + nonce(12) + tag(16)
        #             + 1 byte: the key block ends on a whole pixel, which can leave up to 8 bits unused
        # Load the actual key to determine size dynamically, supporting various RSA key sizes.
        public_key = load_public_key(public_key_path)
        encrypted_key_length = public_key.key_size // 8
        return HEADER_BYTES + encrypted_key_length + AES_NONCE_LENGTH + AES_TAG_LENGTH + 1

    # No encryption: Header only
    return HEADER_BYTES
    
def get_max_message_bytes(total_capacity_bits: int, password: str = None, public_key_path: str = None) -> int:
    total_capacity_bytes = total_capacity_bits // 8
    overhead = estimate_overhead_bytes(password, public_key_path)
    return max(0, total_capacity_bytes - overhead)
