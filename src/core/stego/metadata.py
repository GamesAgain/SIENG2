from src.core.stego.metadata_handlers.mp3_handler import MetadataMP3Handler
from src.core.stego.metadata_handlers.png_handler import MetadataPNGHandler

class MetadataEmbedder:
    """
    Class MetadataEmbed สำหรับการจัดการ metadata ของไฟล์ MP3, PNG
    """
    
    def get_handler(self, file_path: str):
        """
        สร้าง instance ของ MP3Handler, PNGHandler สำหรับการจัดการ metadata
        """
        ext = file_path.lower()
        if ext.endswith(".mp3"):
            return MetadataMP3Handler()
        elif ext.endswith(".png"):
            return MetadataPNGHandler()
        else:
            raise ValueError("Invalid file format")

    def embed(self, file_path: str, data: dict, save_path: str = None) -> str:
        "Embed Data in metadata Module"

        # get handler [PNG, MP3]
        handler = self.get_handler(file_path)

        return handler.embed_metadata(file_path, data, save_path)

    def extract(self, stego_file_path: str):
        "Extract Data from metadata Module"

        # get handler [PNG, MP3]
        handler = self.get_handler(stego_file_path)

        return handler.extract_metadata(stego_file_path)