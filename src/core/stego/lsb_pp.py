from PIL import Image
import cv2
import numpy as np
from skimage.filters.rank import entropy
from skimage.morphology import footprint_rectangle
import hashlib
from pathlib import Path

DEFAULT_CONFIG = {
    'default_seed': 'Default',
    'gradient_analysis':
        {
            'enabled': True,
            'sobel_kernel': 3,
            'weight': 0.5
        },
    'local_entropy':
        {
            'enabled': True,
            'entropy_window': 5,
            'weight': 0.5
        },
    'capacity_threshold': {
        '3bit': 0.7,
        '2bit': 0.4,
        '1bit': 0.1
    }
}

class LSBPP:
    def __init__(self, config: dict = None):
        """
        Initialize LSB++ steganography with configuration
        """
        
        self.set_config(config or DEFAULT_CONFIG)
        
    def set_config(self, config: dict):
        """
        Set configuration for LSB++ steganography
        """
        # set config
        self.config = config
        
        # --- Gradient Analysis Config ---
        self.gradient_analysis = self.config.get('gradient_analysis', DEFAULT_CONFIG['gradient_analysis'])
        self.gradient_enabled = self.gradient_analysis.get('enabled')
        self.sobel_kernel_size = self.gradient_analysis.get('sobel_kernel')
        self.gradient_weight = self.gradient_analysis.get('weight')
        
        # --- Local Entropy Config ---
        self.local_entropy = self.config.get('local_entropy', DEFAULT_CONFIG['local_entropy'])
        self.entropy_enabled = self.local_entropy.get('enabled')
        self.entropy_window_size = self.local_entropy.get('entropy_window')
        self.entropy_weight = self.local_entropy.get('weight')
        
        # set capacity threshold
        self.capacity_threshold = self.config.get('capacity_threshold', DEFAULT_CONFIG['capacity_threshold']) 
       
       # set seed
        self.defalut_seed = self.config.get('default_seed', DEFAULT_CONFIG['default_seed'])
        

    # ==================== Main Public Methods ====================

    def embed(self, cover_image_path: str, message: str, seed: str = None):
        """
        Embed message into cover image using LSB++ algorithm
        """
        # 0. Set seed
        if seed is None:
            seed = self.defalut_seed
        
        # 1. Prepare cover image
        cover_image = self.prepare_image(cover_image_path)
        cover_image_name = Path(cover_image_path).stem

        # 2. Analyze cover image [gradient_map, entropy_map] -> texture_surface
        texture_surface = self.analyze_cover_image(cover_image)

        # 3. Capacity calculation
        capacity_map = self.calcualte_capacity(texture_surface)

        # 4. Get pixel order
        pixel_order = self.get_pixel_order(capacity_map, seed) 
        
        # 5. Embed message
        stego_image = self.message_embedding(cover_image, message, pixel_order, capacity_map)
        
        stego_path = Path(__file__).parent / f"{cover_image_name}_stego.png"
        stego_image.save(stego_path)


    def extract(self, stego_image_path: str, seed: str = None):
        """
        Extract message from stego image using LSB++ algorithm
        """
        # 0. Set seed
        if seed is None:
            seed = self.defalut_seed
            
        # 1. Prepare stego image
        stego_image = self.prepare_image(stego_image_path)

        # 2. Analyze stego image [gradient_map, entropy_map] -> texture_surface
        texture_surface = self.analyze_cover_image(stego_image)

        # 3. Capacity calculation
        capacity_map = self.calcualte_capacity(texture_surface)

        # 4. Get pixel order
        pixel_order = self.get_pixel_order(capacity_map, seed) 
        
        # 5. Extract message
        message = self.message_extraction(stego_image, pixel_order, capacity_map)
        
        return message
    

    # ==================== Image Preparation Methods ====================

    def prepare_image(self, image_path: str) -> Image.Image:
        """
        Prepare image for LSB++ algorithm
        """
            # Check if image exists
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
            return np.ones(cover_image.size) 
        
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
        Convert cover image to grayscale
        """
        # 1. Clean LSB from all pixels
        img_array = np.array(cover_image).copy()
        img_array &= 254
        
        # 2. Convert to grayscale
        clean_img = Image.fromarray(img_array)
        
        gray_img = clean_img.convert('L')
        grey_array = np.array(gray_img)
        return grey_array

    def calculate_gradient(self, gray_array: np.ndarray) -> np.ndarray:
        """
        Calculate gradient map for cover image
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
    
    def calcualte_capacity(self, texture_surface: np.ndarray) -> np.ndarray:
        """
        Calculate capacity map for cover image
        """
        # Get capacity thresholds from config
        threshold_3bit = self.capacity_threshold['3bit']
        threshold_2bit = self.capacity_threshold['2bit']
        threshold_1bit = self.capacity_threshold['1bit']
        
        # Calculate capacity for each pixel
        capacity_map = np.zeros(texture_surface.shape, dtype = np.uint8)
        
        capacity_map[texture_surface > threshold_3bit] = 3
        capacity_map[texture_surface > threshold_2bit] = 2
        capacity_map[texture_surface > threshold_1bit] = 1
        
        return capacity_map.ravel() # Return flattened array
    
    def get_pixel_order(self, capacity_map: np.ndarray, seed: str) -> np.ndarray:
        """
        Get pixel order for embedding
        """
        # Convert string seed to integer
        seed_int = self.seed_from_str(seed)
        
        # Get shuffle index of pixels with capacity > 0
        rng = np.random.default_rng(seed_int)
        flat_idx = np.where(capacity_map > 0)[0] 
        rng.shuffle(flat_idx)
        
        return flat_idx # Return the shuffled indices
    
    def message_embedding(self, cover_image: Image.Image, message: str, pixel_order: np.ndarray, capacity_map: np.ndarray) -> Image.Image:
        """
        Embed message into image
        """
        # 1. Create data bytes (header + payload)
        header = self.create_header(message)
        payload = message.encode('utf-8')
        final_bytes = header + payload
        
        # 2. Embed data into image
        stego_image = self.lsb_replace(cover_image, final_bytes, pixel_order, capacity_map)
        
        return stego_image
    
    def message_extraction(self, stego_image: Image.Image, pixel_order: np.ndarray, capacity_map: np.ndarray) -> str:
        """
        Extract message from stego image
        """
        # 1. Extract bytes from stego image
        extracted_bytes = self.lsb_extract(stego_image, pixel_order, capacity_map)
        message_length, header_length = self.parse_header(extracted_bytes)
        
        # 2. Get data bytes
        total_length = header_length + message_length
        data_bytes = extracted_bytes[header_length:total_length] 
        
        # 3. Decode message
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
            
            for _ in range(capacity):
                if bit_idx < total_bits:
                    bit = message_bits[bit_idx]
                    
                    # เข้าถึงค่าสีแบบ 1D แล้วแทนที่บิต
                    rgb_flat[px] = (rgb_flat[px] & 254) | bit
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
    
    def lsb_extract(self, stego_image: Image.Image, pixel_order: np.ndarray, capacity_map: np.ndarray) -> bytes:
        """
        Extract message from stego image
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
        
        # 3. Extract bits from pixels
        for px in pixel_order:
           capacity = capacity_map[px]
           
           for _ in range(capacity):
               bit = rgb_flat[px] & 1
               extracted_bits.append(bit)
               # Extract LSB from pixel
               pass
        
        # 4. Convert bits to bytes
        bits_array = np.array(extracted_bits, dtype=np.uint8)
        extracted_bytes = np.packbits(bits_array)

        return bytes(extracted_bytes)
    
    # ==================== Utility Methods ====================

    def normalize(self, array: np.ndarray) -> np.ndarray:
        """
        Normalize array to range [0, 1]
        """
        
        # Min-Max Normalization
        max_val = np.max(array)
        if max_val == 0:
            return array
        return array / max_val
    
    def seed_from_str(self, seed: str) -> int:
        """
        Convert string seed to integer
        """
        h = hashlib.sha256(seed.encode("utf-8")).digest()
        return int.from_bytes(h[:8], "big")  # 64-bit
    
    def create_header(self, message: str) -> bytes:
        """
        Create header [MAGIC(3bytes) + LENGTH(4bytes)] = 7 bytes
        """
        magic = b"STG"
        message_bytes = message.encode("utf-8")
        length = len(message_bytes)
        
        # Convert to 4 bytes fixed (support message up to ~4GB)
        length_bytes = length.to_bytes(4, byteorder='big')
        return magic + length_bytes
    
    def parse_header(self, data: bytes) -> tuple[int, int]:
        """
        Parse header from bytes
        """
        magic = data[:3]
        if magic != b"STG":
            raise ValueError("Invalid header")
        
        # Extract length (4 bytes)
        message_length = int.from_bytes(data[3:7], byteorder='big')
        
        header_length = len(magic) + 4 # 4 bytes for message length
        return message_length, header_length
    
if __name__ == "__main__":
    idx_img = 1
    lsb_pp = LSBPP()
    
    lsb_pp.embed(f"img/{idx_img}.png", "Hello")
    
    stego_path = Path(__file__).parent / f"{idx_img}_stego.png"
    message = lsb_pp.extract(stego_path)
    print(f"Message length: {len(message)}")
    print(f"Message : {message}")
