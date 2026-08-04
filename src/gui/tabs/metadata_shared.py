from pathlib import Path


from mutagen.mp3 import MP3, HeaderNotFoundError
from mutagen.id3 import ID3, ID3NoHeaderError
from PIL import Image

from src.core.stego.metadata_handlers.png_handler import MetadataPNGHandler
from src.gui.components.gui_utils import format_file_size, truncate_text_middle

ICON_DIR = Path(__file__).parent.parent / "assets" / "svg"


def get_file_display_info(file_path: str) -> dict:
    """
    สรุปข้อมูลไฟล์ที่เลือกไว้ (icon/name/detail/badges) สำหรับ FileInfoBar
    ใช้ร่วมกันทั้งฝั่ง embed และ extract เพื่อให้ header หน้าตาตรงกันเป๊ะ
    """
    path_obj = Path(file_path)
    size_text = format_file_size(path_obj.stat().st_size)
    display_name = truncate_text_middle(path_obj.name, 110)

    if path_obj.suffix.lower() == ".mp3":
        
        try:
            audio = MP3(file_path)

            # ระยะเวลาเพลง: mutagen ให้เป็นวินาที (float) แปลงเป็น "นาที:วินาที"
            total_seconds = int(audio.info.length)
            duration_text = f"{total_seconds // 60}:{total_seconds % 60:02d}"

            # bitrate: mutagen ให้หน่วยเป็น bps แปลงเป็น kbps
            bitrate_text = f"{audio.info.bitrate // 1000} kbps"

            # เวอร์ชัน ID3 tag เช่น (2, 4, 0) -> "ID3v2.4" ถ้าไฟล์ไม่มี tag เลยให้แจ้งว่า No Tag
            # จำนวน frame: นับ entry ใน ID3 tag ไม่รวม PRIV:S2M (สารบัญภายในของแอปเอง ไม่ใช่ metadata ผู้ใช้)
            tag = ID3(file_path)
            major, minor, _ = tag.version
            id3_version = f"ID3v{major}.{minor}"
            frame_count = sum(
                1 for k, frame in tag.items()
                if not (k.startswith("PRIV:") and getattr(frame, "owner", None) == "S2M")
            )
        except HeaderNotFoundError:
            return {                                                                                                                     
                    "path": file_path,                                                                                                       
                    "icon": str(ICON_DIR / "file-music.svg"),                                                                                
                    "name": display_name,                                                                                                    
                    "detail": "Invalid or Corrupted MP3 file",                                                                               
                    "badges": [("MP3 Header Not Found", "red")],                                                                                            
                }
        except ID3NoHeaderError:
            id3_version = "No Tag"
            frame_count = 0
        except Exception as e:                                                                                                           
                # ดักเผื่อ Error ยิบย่อยอื่นๆ ที่อาจเกิดขึ้นตอนอ่านไฟล์                                                                                    
                return {                                                                                                                     
                    "path": file_path,                                                                                                       
                    "icon": str(ICON_DIR / "file-music.svg"),                                                                                
                    "name": display_name,                                                                                                    
                    "detail": f"Error: {str(e)}",                                                                                            
                    "badges": [("Error", "red")],                                                                                            
                } 

        return {
            "path": file_path,
            "icon": str(ICON_DIR / "file-music.svg"),
            "name": display_name,
            "detail": f"{size_text} · {duration_text} · {bitrate_text} · {id3_version}",
            "badges": [(id3_version, "blue"), (f"{frame_count} frames", "neutral")],
        }
    else:
        # เปิดรูปด้วย Pillow เพื่ออ่านขนาดภาพและโหมดสี
        with Image.open(file_path) as img:
            width, height = img.size

            # จำนวนบิตต่อพิกเซลของแต่ละโหมดสีที่ PNG ใช้บ่อย
            bit_depth = {"1": 1, "L": 8, "P": 8, "RGB": 24, "RGBA": 32}.get(img.mode, 8)

        # นับเฉพาะ text chunk (tEXt/zTXt/iTXt) ที่เก็บ metadata แบบข้อความ - ไม่ใช่ chunk ทั้งไฟล์
        # (stWo เป็น custom chunk ไม่ใช่ text chunk จึงไม่ถูกนับอยู่แล้ว)
        try:
            raw = Path(file_path).read_bytes()
            chunks = MetadataPNGHandler()._parse_chunks(raw)
            text_chunk_types = {b"tEXt", b"zTXt", b"iTXt"}
            text_chunk_count = sum(1 for chunk_type, _ in chunks if chunk_type in text_chunk_types)
            chunk_text = f"{text_chunk_count} text chunks"
        except Exception:
            chunk_text = "-- text chunks"

        return {
            "path": file_path,
            "icon": str(ICON_DIR / "photo.svg"),
            "name": display_name,
            "detail": f"{size_text} · {width} × {height} · {bit_depth}-bit",
            "badges": [("PNG", "blue"), (chunk_text, "neutral")],
        }
