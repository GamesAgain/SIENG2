from pathlib import Path
import struct
import zlib

from PIL import Image
from PIL.PngImagePlugin import PngInfo

# =====================================================================
# Custom Chunk Type: 'stWo' (SIENG Two Workspace Object)
# ออกแบบตามกฎตัวอักษรพิมพ์เล็ก-ใหญ่ (Bit 5) ของมาตรฐาน PNG
# =====================================================================
# 's' (เล็ก)  : Ancillary    -> เป็นส่วนเสริม โปรแกรมที่ไม่รู้จักสามารถข้ามได้ (ภาพไม่พัง)
# 't' (เล็ก)  : Private      -> ระบุว่าสร้างขึ้นเอง (ไม่ชนกับมาตรฐานสากล)
# 'W' (ใหญ่) : Reserved     -> กฎบังคับ PNG: ตัวอักษรที่ 3 "ต้อง" เป็นพิมพ์ใหญ่เสมอ
# 'o' (เล็ก)  : Safe-to-copy -> ข้อมูลไม่สูญหาย แม้ภาพจะถูกนำไปปรับแต่งหรือแก้ไข
# =====================================================================
MAKER_TYPE = "stWo"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class MetadataPNGHandler:
    """
    Metadata 2 ชั้นในไฟล์ PNG:
      - iTXt (มาตรฐาน, ผ่าน PIL) : เก็บค่าจริง {key: value}
      - stWo (custom chunk)      : เก็บ "สารบัญ" รายชื่อ key (comma-separated)
    """

    # ================= PUBLIC API: embed / extract =================

    def embed_metadata(self, file_path: str, data: dict, save_path: str = None) -> str:
        if save_path is None:
            save_path = file_path

        key_string = ",".join(data.keys())

        # 1. เขียนค่าจริงลง iTXt ก่อน (file_path -> save_path)
        self.write_itxt_chunk(file_path, data, save_path)

        # 2. แทรกสารบัญ key ลงใน stWo
        self.inject_custom_chunk(save_path, save_path, MAKER_TYPE, key_string)

        return save_path

    def extract_metadata(self, file_path: str) -> dict:
        """
        Reverse ของ embed_metadata:
          1. อ่าน stWo -> รายชื่อ key ที่ embed ไว้ล่าสุด (สารบัญ)
          2. อ่าน iTXt -> ค่าจริงของ key เหล่านั้น
        คืน {key: value} เฉพาะ key ที่อยู่ใน stWo (= ผลลัพธ์ของ embed_metadata ครั้งล่าสุด)
        """
        keys = self.read_custom_chunk(file_path, MAKER_TYPE)

        if keys is None:
            print(f"[-] ไม่พบ chunk '{MAKER_TYPE}' -> ไฟล์นี้ไม่ได้ผ่าน embed_metadata")
            return {}

        all_text = self.read_itxt_chunk(file_path)

        result = {}
        for key in keys:
            if key in all_text:
                result[key] = all_text[key]
            else:
                print(f"[!] Warning: key '{key}' อยู่ใน stWo แต่ไม่พบใน iTXt")

        return result

    # ================= iTXt: metadata มาตรฐาน (ผ่าน PIL) =================

    def write_itxt_chunk(self, file_path: str, data: dict, save_file_path: str = None, is_compress: bool = True):
        if save_file_path is None:
            save_file_path = file_path

        with Image.open(file_path) as img:
            # รวมค่าเดิม (ถ้ามี) กับค่าใหม่ - key ซ้ำให้ค่าใหม่ทับค่าเดิม
            # (PngInfo() ใหม่เริ่มจากศูนย์เสมอ ถ้าไม่ทำแบบนี้ iTXt/tEXt เดิมจะหายไป)
            merged = dict(img.text)
            merged.update(data)

            metadata = PngInfo()
            for key, value in merged.items():
                metadata.add_itxt(key, value, zip=is_compress)

            img.save(save_file_path, "PNG", pnginfo=metadata)

        print(f"[+] Successfully wrote metadata to: {save_file_path}")

    def read_itxt_chunk(self, file_path: str) -> dict:
        with Image.open(file_path) as img:
            if img.text:
                for key, value in img.text.items():
                    print(f"[+] Found Metadata - Key: '{key}' -> Value: '{value}'")
                return dict(img.text)

            print("[-] No Text Metadata (iTXt/tEXt/zTXt) found in this file.")
            return {}

    # ================= PNG chunk parsing (ใช้ร่วม inject + read custom) =================

    def _parse_chunks(self, raw: bytes) -> list:
        """แตกไฟล์ PNG เป็น list ของ (chunk_type, chunk_data) โดยไล่อ่านทีละ chunk
        ตามสเปกจริง (length 4B + type 4B + data + crc 4B) แทนการเดาตำแหน่งด้วย find()
        """
        if raw[:8] != PNG_SIGNATURE:
            raise ValueError("ไม่ใช่ไฟล์ PNG ที่ถูกต้อง (signature ผิด)")

        chunks = []
        pos = 8  # ข้าม PNG signature 8 ไบต์

        while pos + 8 <= len(raw):
            length = struct.unpack(">I", raw[pos:pos + 4])[0]
            chunk_type = raw[pos + 4:pos + 8]
            chunk_data = raw[pos + 8:pos + 8 + length]

            chunks.append((chunk_type, chunk_data))

            pos += 12 + length  # length(4) + type(4) + data + crc(4)
            if chunk_type == b"IEND":
                break

        return chunks

    def _build_png(self, chunks: list) -> bytes:
        """ประกอบ (chunk_type, chunk_data) list กลับเป็นไฟล์ PNG (CRC คำนวณใหม่ทุก chunk)"""
        parts = [PNG_SIGNATURE]
        for chunk_type, chunk_data in chunks:
            parts.append(self.create_custom_chunk(chunk_type, chunk_data))
        return b"".join(parts)

    def create_custom_chunk(self, chunk_type: bytes, chunk_data: bytes) -> bytes:
        """สร้าง chunk เดียวตาม ISO/IEC 15948: length + type + data + crc
        (generic ใช้ได้กับ chunk ทุกประเภท ไม่ใช่แค่ custom chunk)
        """
        length_bytes = struct.pack(">I", len(chunk_data))
        crc_bytes = struct.pack(">I", zlib.crc32(chunk_type + chunk_data))
        return length_bytes + chunk_type + chunk_data + crc_bytes

    # ================= stWo: custom chunk (low-level) =================

    def inject_custom_chunk(self, file_path: str, save_path: str, chunk_type_str: str, payload_str: str):
        """แทรก custom chunk เข้าไปในไฟล์ PNG
        - วางไว้ถัดจาก IHDR (chunk แรกเสมอตามสเปก)
        - ถ้ามี chunk ประเภทเดียวกันอยู่แล้ว ลบของเก่าออกก่อน (ไม่ให้ซ้ำซ้อน)
        """
        if len(chunk_type_str) != 4:
            raise ValueError("chunk_type ต้องเป็นตัวอักษร 4 ตัวเท่านั้น (ตามสเปก PNG)")

        chunk_type = chunk_type_str.encode("ascii")
        chunk_data = payload_str.encode("utf-8")

        with open(file_path, "rb") as f:
            raw = f.read()

        chunks = self._parse_chunks(raw)

        # ลบ chunk ประเภทเดียวกันที่มีอยู่เดิม (ถ้ามี)
        chunks = [(t, d) for t, d in chunks if t != chunk_type]

        # IHDR เป็น chunk แรก (index 0) เสมอ -> แทรก chunk ใหม่เป็น index 1
        chunks.insert(1, (chunk_type, chunk_data))

        with open(save_path, "wb") as f:
            f.write(self._build_png(chunks))

        print(f"[+] Inject Chunk '{chunk_type_str}' Success !")

    def read_custom_chunk(self, file_path: str, chunk_type_str: str):
        """อ่าน custom chunk แล้วแปลง payload (comma-separated) เป็น list ของ key
        คืน None ถ้าไม่พบ chunk ประเภทนี้ในไฟล์
        """
        if len(chunk_type_str) != 4:
            raise ValueError("chunk_type ต้องเป็นตัวอักษร 4 ตัวเท่านั้น (ตามสเปก PNG)")

        target_type = chunk_type_str.encode("ascii")

        with open(file_path, "rb") as f:
            raw = f.read()

        for chunk_type, chunk_data in self._parse_chunks(raw):
            if chunk_type == target_type:
                try:
                    payload = chunk_data.decode("utf-8")
                except UnicodeDecodeError:
                    return None
                return [k for k in payload.split(",") if k]

        return None
        
if __name__ == "__main__":
    png_handler = MetadataPNGHandler()
    
    # คำนวณตำแหน่งไฟล์รูปภาพจำลอง
    sample_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
    img_path = sample_dir / "sample" / "img" / "1.png"
    output_path = sample_dir / "sample" / "img" / "1_edited.png"
    
    print(f"[*] Target Image Path: {img_path}")
    
    # ข้อมูลลับที่จะใช้ทดสอบระบบ (Payload)
    payload = {
        "Author": "SIENG2",
        "Copyright": "Studio 2026",
        "Description": "ทดสอบภาษาไทยผ่าน iTXt",
        "SecretFlag": "FLAG{STEGO_MASTER}"
    }
    
    if img_path.exists():
        print("[*] Metadata PNG Handler Initialized Ready.\n")
        
        # ==========================================================
        # STEP 1: ทดสอบการฝังข้อมูล (Embed) - ทำงาน 2 ชั้น (iTXt + stWo)
        # ==========================================================
        print(f"[*] === STEP 1: Embedding Metadata ===")
        print(f"    Payload ที่ต้องการซ่อน: {list(payload.keys())}")
        
        try:
            saved_file = png_handler.embed_metadata(str(img_path), payload, str(output_path))
            print(f"[+] ฝังข้อมูลสำเร็จ! ไฟล์ถูกบันทึกที่: {saved_file}\n")
        except Exception as e:
            print(f"[-] เกิดข้อผิดพลาดในการ Embed: {e}\n")
            
        # ==========================================================
        # STEP 2: ทดสอบการสกัดข้อมูล (Extract) - อ่านผ่านสารบัญ stWo
        # ==========================================================
        print(f"[*] === STEP 2: Extracting Metadata ===")
        if output_path.exists():
            try:
                print(f"    กำลังอ่านข้อมูลจากไฟล์: {output_path.name}")
                extracted_data = png_handler.extract_metadata(str(output_path))
                
                print("\n[+] สกัดข้อมูลสำเร็จ! ผลลัพธ์ที่ได้:")
                for k, v in extracted_data.items():
                    print(f"    -> {k} : {v}")
                    
                # ตรวจสอบความถูกต้อง (Validation)
                if len(extracted_data) == len(payload):
                    print("\n[✔] ยืนยันความถูกต้อง: ข้อมูลที่สกัดได้ตรงกับต้นฉบับ 100%")
                else:
                    print("\n[!] คำเตือน: ข้อมูลสูญหายหรือไม่ครบถ้วน")
                    
            except Exception as e:
                print(f"[-] เกิดข้อผิดพลาดในการ Extract: {e}")
        else:
            print(f"[-] Error: ไม่พบไฟล์ผลลัพธ์ {output_path.name} สำหรับทำการทดสอบ Extract")
            
    else:
        print(f"[-] Error: หาไฟล์ภาพไม่เจอในตำแหน่ง: {img_path}")
        print("    แนะนำ: โปรดตรวจสอบ Path ของรูปภาพต้นฉบับอีกครั้ง")
        
    print("\n[*] Script finished execution.")