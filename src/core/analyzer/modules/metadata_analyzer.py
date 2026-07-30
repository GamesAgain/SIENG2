import json
from typing import Dict, Any
from src.core.analyzer.external_tools.exiftool_wrapper import extract_metadata
from datetime import datetime
from src.core.analyzer.utils.text_extractor import extract_base64, extract_binary, extract_hex

class MetadataAnalyzer:
    def __init__(self, raw_exif_data: Dict[str, Any]):
        self.raw_data = raw_exif_data

    def _get_value_by_suffix(self, suffix: str):
        for k, v in self.raw_data.items():
            if k.endswith(suffix):
                return v
        return None

    def analyze(self) -> Dict[str, Any]:
        create_date_str = self._get_value_by_suffix("FileCreateDate")
        modify_date_str = self._get_value_by_suffix("FileModifyDate")
        access_date_str = self._get_value_by_suffix("FileAccessDate")

        time_anomalies = self._check_time_conflict(create_date_str, modify_date_str, access_date_str)
        software_anomalies = self._check_software()
        text_anomalies = self._check_text_fields()

        return {
            "raw_data": self.raw_data,
            "time_anomalies": time_anomalies,
            "software_anomalies": software_anomalies,
            "text_anomalies": text_anomalies
        }

    def _check_time_conflict(self, create_date_str: str, modify_date_str: str, access_date_str: str):
        anomalies = []
    
        create_date = self.parse_exif_date(create_date_str)
        modify_date = self.parse_exif_date(modify_date_str)
        access_date = self.parse_exif_date(access_date_str)
        current_time = datetime.now()
        
        time_tags = [("FileCreateDate", create_date), ("FileModifyDate", modify_date), ("FileAccessDate", access_date)]
        for tag_name, date_obj in time_tags:
            if date_obj and date_obj > current_time:
                anomalies.append({
                    "tag": "Timestamp",
                    "message": f"Future Timestamp: {tag_name} ({date_obj.strftime('%Y:%m:%d %H:%M:%S')}) > Current System Time. Possible timestomping."
                })
                
        if create_date and modify_date: 
            if modify_date < create_date:
                anomalies.append({
                    "tag": "Timestamp",
                    "message": f"Modify Date ({modify_date}) < Create Date ({create_date})."
                })
                
        if create_date and access_date:
            if access_date < create_date:
                anomalies.append({
                    "tag": "Timestamp",
                    "message": f"Access Date ({access_date}) < Create Date ({create_date})."
                })
                
        # Check original/EXIF dates against file creation date
        exif_time_keys = ["EXIF:DateTimeOriginal", "EXIF:CreateDate", "XMP:CreateDate", "QuickTime:CreateDate"]
        for key in exif_time_keys:
            exif_date_str = self.raw_data.get(key)
            if exif_date_str:
                exif_date = self.parse_exif_date(exif_date_str)
                if create_date and exif_date and create_date < exif_date:
                    anomalies.append({
                        "tag": "Timestamp",
                        "message": f"File Create Date ({create_date}) < EXIF/Original Date ({exif_date}) from {key}. Possible timestomping or copy anomaly."
                    })
                
        return anomalies
        
    def _check_software(self):
        anomalies = []
        suspicious_keywords = [
            "photoshop", "gimp", "premiere", "after effects", "exiftool", "ffmpeg", "lavf",
            "steghide", "stegosuite", "opensteg", "outguess", "silenteye", "deepsound", "mp3steg", "jsteg",
            "mat2", "exifpurger", "exiv2"
        ]   
        
        for key, value in self.raw_data.items():
            key_lower = key.lower()
            if any(k in key_lower for k in ['software', 'creator', 'producer', 'tool']):
                val_str = str(value).lower()
                if any(keyword in val_str for keyword in suspicious_keywords):
                    anomalies.append({
                        "tag": f"Software/Creator ({key})",
                        "message": f"Possible manipulation. Editing software detected: {value}"
                    })
        return anomalies
    
    def _check_text_fields(self):
        anomalies = []
        for key, value in self.raw_data.items():
            
            if key in ["SourceFile", "File:Directory"]:
                continue
        
            if not isinstance(value, str):
                continue

            preview_val = value[:50] + "..." if len(value) > 50 else value

            if extract_binary(value):
                anomalies.append({
                    "tag": f"TextFields ({key})",
                    "message": f"Matches Binary stream pattern."
                    })
            elif extract_hex(value):
                anomalies.append({
                    "tag": f"TextFields ({key})",
                    "message": f"Matches Hexadecimal pattern."
                    })
            elif extract_base64(value):
                anomalies.append({
                    "tag": f"TextFields ({key})",
                    "message": f"Matches Base64 pattern."
                    })
                
            if len(value) > 200:
                anomalies.append({
                    "tag": f"TextFields ({key})",
                    "message": f"Unusually long text ({len(value)} characters)."
                    })
                    
        return anomalies
    
    @staticmethod
    def parse_exif_date(date_str):
        if not date_str:
            return None
        try:
            clean_str = str(date_str)[:19]
            return datetime.strptime(clean_str, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            return None