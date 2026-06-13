from pathlib import Path
from pprint import pprint
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
        if file_path.endswith(".mp3"):
            return MetadataMP3Handler()
        elif file_path.endswith(".png"):
            return MetadataPNGHandler()
        else:
            raise ValueError("Invalid file format")
        
    def embed(self, file_path: str, data: dict, save_path: str = None) -> str:
        "Embed Data in metadata Module"
        
        # get handler [PNG, MP3]
        handler = self.get_handler(file_path)
        
        # Hiding data into metadata 
        stego_file_path = handler.embed_metadata(file_path, data, save_path)
        
        return stego_file_path
    
    def extract(self, stego_file_path: str):
        "Extract Data from metadata Module"
        
        # get handler [PNG, MP3]
        handler = self.get_handler(stego_file_path)
        
        # Extract the hidden data from the metadata
        extracted_data = handler.extract_metadata(stego_file_path)
        
        return extracted_data
        
def test_png():
    # อินสแตนซ์ตัวรวมจัดการ Metadata (Facade)
    stego_manager = MetadataEmbedder()
    
    # 1. Setup Paths สำหรับ PNG (อ้างอิงโฟลเดอร์ sample/img ตามโครงสร้างของคุณ)
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    png_dir = project_root / "sample" / "img"
    src_png = png_dir / "1.png"
    out_png = png_dir / "1_stego.png"  # แยกไฟล์เอาไว้ไม่ให้ทับตัวดั้งเดิม
    
    # 2. เตรียมชุดข้อมูล Payload (Dict) สำหรับฝังลงในภาพ PNG (iTXt / stWo)
    png_payload = {
        "Author": "ผู้พัฒนา SIENG2",
        "Copyright": "Copyright Studio 2026",
        "Description": "ข้อความลับสุดยอดที่ถูกซ่อนภายในโครงสร้างภาพไฟล์ PNG",
        "Project_Name": "SIENG2 Metadata Hiding Suite"
    }
    
    print("=" * 60)
    print("[*] ระบบทดสอบโมดูลซ่อนข้อมูล PNG Metadata (SIENG2 Tool)")
    print("=" * 60)
    print(f"[*] ไฟล์ภาพต้นฉบับ: {src_png}")
    
    # 3. เริ่มขั้นตอนการทดสอบการฝังข้อมูล (Embed)
    if src_png.exists():
        print("\n--- [ขั้นตอนที่ 1: กำลังดำเนินการฝังข้อมูลลับ] ---")
        
        # ส่งค่าออกไปฝัง และรับพาธไฟล์ปลายทางกลับมา
        stego_file = stego_manager.embed(
            file_path=str(src_png), 
            data=png_payload, 
            save_path=str(out_png)
        )
        print(f"[+] การฝังข้อมูลเสร็จสิ้น! บันทึกไฟล์ที่: {stego_file}")
        
        # 4. เริ่มขั้นตอนการทดสอบการถอดข้อมูลกลับ (Extract)
        print("\n--- [ขั้นตอนที่ 2: กำลังอ่านและถอดข้อมูลจากไฟล์ภาพ] ---")
        if Path(stego_file).exists():
            
            extracted_data = stego_manager.extract(stego_file)
            print("[+] ถอดรหัสข้อมูลสำเร็จ! ผลลัพธ์ข้อมูลที่ซ่อนอยู่คือ:")
            
            # ใช้ pprint แสดงผล Dict สวยงามเป็นบรรทัดๆ
            print("-" * 40)
            pprint(extracted_data)
            print("-" * 40)
            
        else:
            print(f"[-] ไม่พบไฟล์ผลลัพธ์ {stego_file} ในระบบ")
            
    else:
        print(f"[-] ข้อผิดพลาด: ไม่พบไฟล์ภาพตัวอย่าง '1.png' ในตำแหน่ง: {src_png}")
        print("[!] กรุณาตรวจสอบว่ามีโฟลเดอร์ sample/img/1.png อยู่จริงในโปรเจกต์")
        
    print("\n[*] สคริปต์ทำงานเสร็จสิ้นสมบูรณ์.")
    
    
def test_mp3():
    # 1. Setup Paths
    base_dir = Path(__file__).resolve().parent.parent.parent.parent / "sample" / "mp3"
    src_mp3 = base_dir / "sample-3s.mp3"
    
    # 2. Test Data
    test_data = {
        "TIT2": "เพลงทดสอบ2 - ระบบ Metadata Hiding",
        "TPE1": "ผู้พัฒนา SIENG2",
        "TALB": "SIENG2 Development Album",
        "COMM": [{"lang": "tha", "desc": "Secret Note", "text": "นี่คือข้อมูลลับที่ถูกซ่อน"}]
    }
    
    # 3. Test Embed
    if src_mp3.exists():
        stego_writer = MetadataEmbedder()
        out_mp3 = stego_writer.embed(str(src_mp3), test_data)
        print("Embedded successfully.")
        
    # 4. Test Extract
    if Path(out_mp3).exists():
        stego_reader = MetadataEmbedder()
        data = stego_reader.extract(str(out_mp3))
        print("Extracted Data:", data)
    else:
        print("Output file not found for extraction.")
        
if __name__ == "__main__":
    test_png()
    test_mp3()