import sys
import os
import json
import subprocess
from datetime import datetime

# ==========================================
# EXTRACTION
# ==========================================

def get_exif_data(file_path: str) -> dict:
    """Extract EXIF data using exiftool."""
    try:
        result = subprocess.run(
            ['exiftool', '-json', file_path],
            capture_output=True, text=True, check=True
        )
        exif_data = json.loads(result.stdout)
        return exif_data[0] if exif_data else {}
        
    except FileNotFoundError:
        print("ไม่พบ ExifTool")
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error running exiftool: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return None

def get_native_metadata(file_path: str) -> dict:
    file_info = os.stat(file_path)
    
    return {
        "SourceFile": file_path,
        "FileName": os.path.basename(file_path),
        "FileSize": file_info.st_size,
        "FileModifyDate": file_info.st_mtime,
        "FileAccessDate": file_info.st_atime,
        "FileCreateDate": file_info.st_ctime
    }

def extract_metadata(file_path: str) -> dict:
    data = get_exif_data(file_path)
    
    if data is None:
        data = get_native_metadata(file_path)
        
    return data

# ==========================================
# ANALYSIS
# ==========================================
    
def check_timestamps(data: dict) -> dict:
    """Check file timestamps"""
    
    os_create = parse_time(data.get("FileCreateDate"))
    os_modify = parse_time(data.get("FileModifyDate"))
    os_access = parse_time(data.get("FileAccessDate"))
    internal_create = parse_time(data.get("DateTimeOriginal"))
    
    now = datetime.now()
    
    msg = ""

    if (os_create and os_create > now) or \
       (os_modify and os_modify > now) or \
       (internal_create and internal_create > now):
        msg += "[พบเวลาในอนาคต] "
        
    if os_modify and os_create and (os_modify < os_create):
        msg += "[เวลาแก้ไขเกิดก่อนเวลาสร้าง] "
        
    if internal_create and os_create and (internal_create > os_create):
        msg += "[เวลากด Shutter เกิดหลังไฟล์ถูกสร้าง] "
        
    if os_create and os_modify and os_access and (os_create == os_modify == os_access):
        msg += "[เวลา Create/Modify/Access เท่ากัน] "

    if msg != "":
        return {
            "status": "WARNING", 
            "details": msg.strip()
        }
        
    return {
        "status": "OK",
        "details": "ไม่พบความสอดคล้องของเวลาที่ผิดปกติ"
    }
    
def check_software(data: dict) -> dict:
    """Check file software"""
    result = {"status": "OK", "details": "ไม่พบซอฟต์แวร์ที่น่าสงสัย"}
    
    software = data.get("Software", "").lower()
    if "photoshop" in software or "gimp" in software:
         result = {"status": "WARNING", "details": f"พบการใช้โปรแกรมแต่งภาพ: {software}"}
         
    return result

def check_unnormal(data: dict) -> dict:
    """Check file unnormal"""
    result = {"status": "OK", "details": "โครงสร้างปกติ"}
    return result

def run_all_checks(data: dict) -> dict:
    return {
        "Timestamps": check_timestamps(data),
        "Software": check_software(data),
        "Anomalies": check_unnormal(data)
    }
    
# ==========================================
# Helper Functions
# ==========================================    
    
def parse_time(time_val):
    """ฟังก์ชันช่วยแปลงเวลาทั้งจาก OS และ ExifTool ให้เป็น datetime"""
    if not time_val:
        return None
        
    # กรณีใช้ระบบสำรอง (Native) เวลาจะมาเป็นตัวเลข Float
    if isinstance(time_val, (int, float)):
        return datetime.fromtimestamp(time_val)
        
    # กรณีใช้ ExifTool เวลาจะมาเป็นข้อความ String
    if isinstance(time_val, str):
        clean_str = time_val.split("+")[0].split("-")[0].strip()
        try:
            return datetime.strptime(clean_str, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            return None
            
    return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
        
    target_file = sys.argv[1]
    raw_metadata = extract_metadata(target_file)
    print(raw_metadata)
    
    analysis_results = run_all_checks(raw_metadata)
    
    print("\n--- ผลการวิเคราะห์ ---")
    for check_name, result in analysis_results.items():
        status_icon = "[✓]" if result["status"] == "OK" else "[!]"
        print(f"{status_icon} {check_name}: {result['details']}")