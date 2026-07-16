import io
from pathlib import Path
from PIL import Image
import cv2
import numpy as np
from skimage.filters.rank import entropy
from skimage.morphology import footprint_rectangle
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
 
from src.core.crypto.sym_encrypt import SymmetricEncryption
from src.core.crypto.asym_encrypt import AsymmetricEncryption, load_public_key, load_private_key, get_public_bytes

DEFAULT_LSBPP_CONFIG = {
    'default_seed': 'Default',
    'pixel_shuffle': True,
    'embedding_mode': 'matching',  # 'replace' | 'matching'
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
    'capacity_threshold': {
        '3bit': 0.7,
        '2bit': 0.4,
        '1bit': 0.1
    }
}

# Encrypt Mode constants SIENG2 [SE = Steganography Encryption]
MAGIC_SYM = b"SES" # Steganography Encryption Symmetric
MAGIC_ASYM = b"SEA" # Steganography Encryption Asymmetric
MAGIC_NONE = b"SEN" # Steganography Encryption None
HEADER_BYTES = 7  # MAGIC (3 bytes) + LENGTH (4 bytes)

# IEND chunk เต็ม 12 bytes (length 0 + "IEND" + CRC) = จุดจบไฟล์ PNG จริง
# ใช้แยก bytes ที่ต่อท้ายหลัง IEND ออก (เช่น payload EOF ของ Locomotive)
PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB\x60\x82"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
COLOR_TYPE_DEPENDENT_CHUNKS = (b"PLTE", b"tRNS", b"bKGD", b"sBIT", b"hIST")


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
        self.default_seed = self.config.get('default_seed', DEFAULT_LSBPP_CONFIG['default_seed']) # set defalut seed
        self.pixel_shuffle = self.config.get('pixel_shuffle', DEFAULT_LSBPP_CONFIG['pixel_shuffle']) # set pixel order
        self.embedding_mode = self.config.get('embedding_mode', DEFAULT_LSBPP_CONFIG['embedding_mode']) # set embedding algorithm


    # ==================== Main Public Methods ====================

    def embed(self, cover_image_path: str, message: str, public_key_path: str = None, password: str = None) -> tuple[bytes, str]:
        """
        Embed payload message into cover image using LSB++ algorithm
        """
        
        # 1. Prepare cover image
        cover_image = self.prepare_image(cover_image_path)
        base_file_name = Path(cover_image_path).stem

        # 2. Analyze cover image [gradient_map, entropy_map] -> texture_surface
        texture_surface = self.analyze_cover_image(cover_image)

        # 3. Capacity calculation
        capacity_map = self.calculate_capacity(texture_surface)
        
        # 4. Get seed
        seed = self.get_seed(password, public_key_path)
            
        # 5. Get pixel order
        pixel_order = self.get_pixel_order(capacity_map, seed) 
        
        # 6. Encode message and pack payload (Header + Payload)
        raw_payload = message.encode('utf-8')
        packed_payload = self.pack_data(raw_payload, public_key_path, password)
        
        # 7. Validate capacity before embed
        self.validate_capacity(packed_payload, capacity_map)

        # 8. Embed message
        if self.embedding_mode == 'matching':
            stego_image = self.lsb_matching(cover_image, packed_payload, pixel_order, capacity_map)
        else:
            stego_image = self.lsb_replace(cover_image, packed_payload, pixel_order, capacity_map)
        
        # 9. Merge Stego Image bytes
        stego_image_bytes = self.merge_stego_bytes(cover_image_path, stego_image)
        
        # 10. Export File name (always .png)
        stego_file_name = f"{base_file_name}_stego.png"

        return stego_image_bytes, stego_file_name
    

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


    def extract(self, stego_image_path: str, private_key_path: str = None, password: str = None) -> str:
        """
        Extract payload message from stego image using LSB++ algorithm
        """
            
        # 1. Prepare stego image
        stego_image = self.prepare_image(stego_image_path)

        # 2. Analyze stego image [gradient_map, entropy_map] -> texture_surface
        texture_surface = self.analyze_cover_image(stego_image)

        # 3. Capacity calculation
        capacity_map = self.calculate_capacity(texture_surface)
        
        # 4. Get seed
        seed = self.get_seed(password, private_key_path)
        
        # 5. Get pixel order
        pixel_order = self.get_pixel_order(capacity_map, seed) 
        
        # 6. Extract message
        extracted_message = self.message_extraction(stego_image, pixel_order, capacity_map, private_key_path, password)
        
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
        # 1. Clean LSB from all pixels
        img_array = np.array(cover_image).copy()
        img_array &= 254
        
        # 2. Convert to grayscale
        grey_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        
        return grey_array

    def calculate_gradient(self, gray_array: np.ndarray) -> np.ndarray:
        """
        Calculate gradient map for cover image by Sobel operator
        """
        
        # Calculate Gradient
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
        Calculate surface map for cover image
        """
        #  set weights
        weight_gradient = self.gradient_weight
        weight_entropy = self.entropy_weight
        
        # set surface map to zero
        surface = np.zeros_like(entropy_map if entropy_map is not None else gradient_map)
        
        # calculate gradient part
        if gradient_map is not None and weight_gradient > 0:
            grad_norm = self.normalize(gradient_map)
            surface += weight_gradient * grad_norm

        # calculate entropy part
        if entropy_map is not None and weight_entropy > 0:
            ent_norm = self.normalize(entropy_map)
            surface += weight_entropy * ent_norm
        
        # normalize surface map to range [0, 1]
        surface_normalized = self.normalize(surface)
        return surface_normalized
    
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
    
    def get_pixel_order(self, capacity_map: np.ndarray, seed: int) -> np.ndarray:
        """
        Get pixel order for embedding
        """
        # Get shuffle index of pixels with capacity > 0
        rng = np.random.default_rng(seed)
        flat_idx = np.where(capacity_map > 0)[0] 
        
        if self.pixel_shuffle:
            rng.shuffle(flat_idx)
        
        return flat_idx 
    
    def message_extraction(self, stego_image: Image.Image, pixel_order: np.ndarray, capacity_map: np.ndarray, private_key_path: str = None, password: str = None) -> str:
        """
        Extract message from stego image
        """
        total_capacity_bits = int(np.sum(capacity_map))
        header_bits = HEADER_BYTES * 8

        if header_bits > total_capacity_bits:
            raise ValueError("Extraction failed: image capacity too small to contain a valid header.")

        # 1. Read the header first (magic + length) to find the total message size
        header_bytes = self.lsb_extract(stego_image, pixel_order, capacity_map, max_bits=header_bits)

        if header_bytes[:3] not in (MAGIC_SYM, MAGIC_ASYM, MAGIC_NONE):
            raise ValueError("Extraction failed: Invalid SIENG2 signature. Please verify your image and password.")

        message_length = int.from_bytes(header_bytes[3:HEADER_BYTES], byteorder='big')
        required_bits = (HEADER_BYTES + message_length) * 8

        # 2. Validate the extracted length
        if required_bits > total_capacity_bits:
            raise ValueError("Extraction failed: decoded length exceeds image capacity. Please verify your image and password.")

        # 3. Perform a second read for the exact required bits (header + payload)
        extracted_bytes = self.lsb_extract(stego_image, pixel_order, capacity_map, max_bits=required_bits)
        data_bytes = self.unpack_data(extracted_bytes, private_key_path, password)

        # Decode message
        try:
            message_extracted = data_bytes.decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError("Failed to decode message. The extracted data is not valid UTF-8 text.")

        return message_extracted
    
    def lsb_replace(self, cover_image: Image.Image, data: bytes, pixel_order: np.ndarray, capacity_map: np.ndarray) -> Image.Image:
        """
        Replace LSB of pixels with message bits
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
            
            capacity = capacity_map[px]
            
            for channel in range(capacity):
                if bit_idx < total_bits:
                    idx = px * 3 + channel
                    rgb_flat[idx] = (rgb_flat[idx] & 254) | message_bits[bit_idx]
                    bit_idx += 1
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

    def lsb_matching(self, cover_image: Image.Image, data: bytes, pixel_order: np.ndarray, capacity_map: np.ndarray, max_passes: int = 8) -> Image.Image:
        """
        Embed using LSB Matching (+-1)
        """
        # 1. Prepare cover array, same as lsb_replace
        img_array = np.array(cover_image)
        channels = img_array.shape[2]
        image_height, image_width = img_array.shape[0], img_array.shape[1]

        # 2. Separate RGB and Alpha channels
        if channels == 4:
            rgb_chanel = img_array[:, :, :3]
            alpha_channel = img_array[:, :, 3]
        else:
            rgb_chanel = img_array
            alpha_channel = None

        # 3. Keep an untouched copy of the original pixel values.
        original_flat = rgb_chanel.ravel().copy()
        working_flat = rgb_chanel.ravel().copy()

        # 4. Convert message bytes to bits
        byte_array = np.frombuffer(data, dtype=np.uint8)
        message_bits = np.unpackbits(byte_array)
        total_bits = len(message_bits)

        # 5. Walk embed following the pixel_order and , and record every
        # (pixel, flat_index, target_bit) position the message actually uses
        embed_positions = []
        bit_idx = 0
        for px in pixel_order:
            if bit_idx >= total_bits:
                break
            capacity = capacity_map[px]
            for channel in range(capacity):
                if bit_idx >= total_bits:
                    break
                idx = px * 3 + channel
                embed_positions.append((px, idx, int(message_bits[bit_idx])))
                bit_idx += 1

        # 6. calculate_gradient()/calculate_local_entropy() look at a window of pixels
        # around each pixel, so a changed pixel can affect its neighbors' capacity too.
        neighbor_radius = 0 # neighbor_radius is how far that influence can reach.
        if self.gradient_enabled:
            neighbor_radius = max(neighbor_radius, self.sobel_kernel_size // 2)
        if self.entropy_enabled:
            neighbor_radius = max(neighbor_radius, self.entropy_window_size // 2)

        # 7. Embeds one bit position, either with a random +-1 direction, or with the
        # deterministic "safe" direction that lsb_replace would also use.
        random_number_generator = np.random.default_rng()

        def embed_one_position(flat_index: int, target_bit: int, force_safe_direction: bool) -> None:
            original_value = int(original_flat[flat_index])
            if (original_value & 1) == target_bit:
                working_flat[flat_index] = original_value
                return
            if force_safe_direction or original_value == 0 or original_value == 255:
                # even value -> going up (+1) keeps convert_to_grayscale's masked value unchanged; 
                # odd value -> going down (-1) does. Same direction lsb_replace uses.
                if original_value % 2 == 0:
                    direction = 1
                else:
                    direction = -1
            else:
                direction = int(random_number_generator.choice([-1, 1]))
            working_flat[flat_index] = original_value + direction

        # 8. Embed every position with a genuinely random direction first
        for px, idx, target_bit in embed_positions:
            embed_one_position(idx, target_bit, force_safe_direction=False)

        # 9. Verify: rebuild the image and re-run the exact same analysis extract()
        # will run later. If any pixel's capacity now disagrees with capacity_map,
        # embed() and extract() would read a different number of bits at that pixel
        corrected_indexes = set()  # flat indexes already forced to the safe direction

        for current_pass in range(max_passes):
            stego_rgb = working_flat.reshape(rgb_chanel.shape)
            
            if alpha_channel is not None:
                stego_array = np.dstack((stego_rgb, alpha_channel)) # Merge alpha channel back to image
            else:
                stego_array = stego_rgb

            stego_image = Image.fromarray(stego_array)

            recomputed_capacity_map = self.calculate_capacity(self.analyze_cover_image(stego_image))
            mismatched_pixels = set(np.where(recomputed_capacity_map != capacity_map)[0].tolist())

            if not mismatched_pixels:
                return stego_image

            # widen the mismatch to include neighboring pixels too, since the analysis
            # window means a neighbor's random step can be the real cause
            if neighbor_radius > 0:
                mismatched_array = np.fromiter(mismatched_pixels, dtype=np.int64)
                mismatched_rows = mismatched_array // image_width
                mismatched_cols = mismatched_array % image_width
                for row_offset in range(-neighbor_radius, neighbor_radius + 1):
                    for col_offset in range(-neighbor_radius, neighbor_radius + 1):
                        neighbor_rows = np.clip(mismatched_rows + row_offset, 0, image_height - 1)
                        neighbor_cols = np.clip(mismatched_cols + col_offset, 0, image_width - 1)
                        mismatched_pixels.update((neighbor_rows * image_width + neighbor_cols).tolist())

            positions_to_fix = [
                (px, idx, target_bit) for px, idx, target_bit in embed_positions
                if px in mismatched_pixels and idx not in corrected_indexes
            ]

            # if the mismatch isn't explained by anything nearby, it must be from
            # calculate_surface()'s min-max normalization, which looks at the WHOLE
            # image, not just a window -- fall back to correcting every position left
            if not positions_to_fix:
                positions_to_fix = [
                    (px, idx, target_bit) for px, idx, target_bit in embed_positions
                    if idx not in corrected_indexes
                ]

            for px, idx, target_bit in positions_to_fix:
                corrected_indexes.add(idx)
                embed_one_position(idx, target_bit, force_safe_direction=True)

        raise RuntimeError(
            f"LSB Matching did not converge after {max_passes} passes. This should not "
            f"normally happen -- forcing every remaining position to the safe direction "
            f"always converges. Switch embedding_mode to 'replace' if this keeps happening."
        )

    def lsb_extract(self, stego_image: Image.Image, pixel_order: np.ndarray, capacity_map: np.ndarray, max_bits: int = None) -> bytes:
        """
        Extract message from stego image.
        max_bits: Bits to read (None = read all supported by pixel_order).
        """
        # 1. Convert image to numpy array
        img_array = np.array(stego_image)
        channels = img_array.shape[2]

        # 2. Separate RGB and Alpha channels
        if channels == 4:
            rgb_flat = img_array[:, :, :3].ravel()
        else:
            rgb_flat = img_array.ravel()

        extracted_bits = []

        # 3. Extract bits from pixels (stop at max_bits)
        for px in pixel_order:
            if max_bits is not None and len(extracted_bits) >= max_bits:
                break

            capacity = capacity_map[px]

            for channel in range(capacity):
                if max_bits is not None and len(extracted_bits) >= max_bits:
                    break
                bit = rgb_flat[px * 3 + channel] & 1
                extracted_bits.append(bit)

        # 4. Convert bits to bytes
        bits_array = np.array(extracted_bits, dtype=np.uint8)
        extracted_bytes = np.packbits(bits_array)

        return bytes(extracted_bytes)
    
    # ==================== Utility Methods ====================

    def validate_capacity(self, data_package: bytes, capacity_map: np.ndarray) -> None:
        """
        Raise ValueError if data_package exceeds the image's embeddable capacity.
        """
        total_capacity_bits = int(np.sum(capacity_map))
        required_bits = len(data_package) * 8 # bits length
        if required_bits > total_capacity_bits:
            raise ValueError(
                f"Message too large to embed: "
                f"requires {required_bits} bits ({len(data_package)} bytes), "
                f"but image only supports {total_capacity_bits} bits "
                f"({total_capacity_bits // 8} bytes)."
            )

    def get_seed(self, password: str = None, key_path: str = None) -> int:
        """
        Generate seed from password or public key
        """
        
        if password is not None and key_path is None:
            seed = password.encode()
            
        elif key_path is not None: 
            # Check if encrypt private key with password
            key_password = password if password else None
                
            with open(key_path, "rb") as f:
                key_data = f.read()
                
            if b"PRIVATE KEY" in key_data:                
                private_key = load_private_key(key_path, key_password)
                public_key = private_key.public_key()
                
            elif b"PUBLIC KEY" in key_data:
                public_key = load_public_key(key_path)
                
            else:
                raise ValueError("Invalid key file format")
            
            seed = get_public_bytes(public_key)
            
        else:
            seed = self.default_seed.encode()
            
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=16,   # 128-bit seed
            salt=None,
            info=b"SIENG2_LSB_SHUFFLE",
        )

        seed_bytes = hkdf.derive(seed)
        
        return int.from_bytes(seed_bytes, "big")

    def normalize(self, array: np.ndarray) -> np.ndarray:
        """
        Normalize array to range [0, 1]
        """
        
        # Min-Max Normalization
        min_val = np.min(array)
        max_val = np.max(array)
        if max_val == min_val:
            return np.zeros_like(array)
        return (array - min_val) / (max_val - min_val)
    
    def pack_data(self, data: bytes, public_key_path: str = None, password: str = None) -> bytes:
        """
        Build complete payload: [MAGIC (3 bytes) + LENGTH (4 bytes) + ENCRYPTED_DATA]
        Returns: (header_bytes, encrypted_data_bytes)
        """
        # 1. Process message based on encryption mode
        if password is not None:
            magic = MAGIC_SYM  # SES: Symmetric encryption
            encryptor = SymmetricEncryption()
            data_bytes = encryptor.encrypt(data, password)
        elif public_key_path is not None:
            magic = MAGIC_ASYM  # SEA: Asymmetric encryption
            encryptor = AsymmetricEncryption()
            public_key = load_public_key(public_key_path)
            data_bytes = encryptor.encrypt(data, public_key)
        else:
            magic = MAGIC_NONE  # SEN: No encryption
            data_bytes = data
            
        # 2. Create header with message length
        message_length = len(data_bytes)
        length_bytes = message_length.to_bytes(4, byteorder='big')
        header = magic + length_bytes
        
        data_package = header + data_bytes
        
        return data_package
    
    def unpack_data(self, data: bytes, private_key_path: str = None, password: str = None) -> bytes:
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
            if not private_key_path:
                raise ValueError("Private key required for asymmetric decryption")
                
            decryptor = AsymmetricEncryption()
            private_key = load_private_key(private_key_path, password)
            plaintext  = decryptor.decrypt(extracted_data, private_key) 
            return plaintext  
        elif magic == MAGIC_NONE:  # SEN: No encryption
            return extracted_data
            
        else:
            raise ValueError("Extraction failed: Invalid SIENG2 signature. Please verify your image and password.")
            
    def get_total_capacity_bits(self, cover_image_path: str) -> int:
        cover_image = self.prepare_image(cover_image_path)
        texture_surface = self.analyze_cover_image(cover_image)
        capacity_map = self.calculate_capacity(texture_surface)
        return int(np.sum(capacity_map))

# --- External function ---    
def estimate_overhead_bytes(password: str = None, public_key_path: str = None) -> int:
    """
    Estimate the pack_data() byte overhead for the selected encryption mode.
    """
    if password is not None:
        # Symmetric: HEADER + salt(16) + nonce(12) + tag(16)
        return HEADER_BYTES + 16 + 12 + 16  # = 51

    if public_key_path is not None:
        # Asymmetric: HEADER + RSA-encrypted session key (actual key size) + nonce(12) + tag(16)
        # Load the actual key to determine size dynamically, supporting various RSA key sizes.
        public_key = load_public_key(public_key_path)
        encrypted_key_length = public_key.key_size // 8
        return HEADER_BYTES + encrypted_key_length + 12 + 16

    # No encryption: Header only
    return HEADER_BYTES
    
def get_max_message_bytes(total_capacity_bits: int, password: str = None, public_key_path: str = None) -> int:
    total_capacity_bytes = total_capacity_bits // 8
    overhead = estimate_overhead_bytes(password, public_key_path)
    return max(0, total_capacity_bytes - overhead)

 # --- ตัวอย่างการเรียกใช้งาน ---   
if __name__ == "__main__":
    
    lsb_pp = LSBPP()
    
    idx_img = 1 # รูปที่ 1
    
    # -- Embed Symmetric --
    lsb_pp.embed(
        cover_image_path=f"img/{idx_img}.png", 
        message="Hello Password",
        password="SuperSecretPassword123"
    )
    
    # -- Extract Symmetric --
    stego_path = Path(__file__).parent / f"{idx_img}_stego.png"
    message = lsb_pp.extract(
        stego_image_path=stego_path, 
        password="SuperSecretPassword123"
    )
    
    print(f"Case 1 - Symmetric Message length: {len(message)}")
    print(f"Case 1 - Symmetric Message : {message}")
    
    idx_img = 2 # รูปที่ 2
    
    # -- Embed Asymmetric --
    lsb_pp.embed(
        cover_image_path=f"img/{idx_img}.png", 
        message="Hello Public Key",
        public_key_path="public_key_e.pem"
    )
    
    # -- Extract Asymmetric --
    stego_path = Path(__file__).parent / f"{idx_img}_stego.png"
    message = lsb_pp.extract(
        stego_image_path=stego_path, 
        private_key_path="private_key_e.pem",
        password="Password123"
    )
    
    print(f"Case 2 - Asymmetric Message length: {len(message)}")
    print(f"Case 2 - Asymmetric Message : {message}")
    
    idx_img = 3 # รูปที่ 3
    
    # -- Embed No Encryption --
    lsb_pp.embed(
        cover_image_path=f"img/{idx_img}.png", 
        message="Hello",
    )
    
    # -- Extract No Encryption --
    stego_path = Path(__file__).parent / f"{idx_img}_stego.png"
    message = lsb_pp.extract(
        stego_image_path=stego_path
    )
    
    print(f"Case 3 - Message length: {len(message)}")
    print(f"Case 3 - Message : {message}")