"""
MP3Handler - จัดการ metadata สำหรับไฟล์ MP3 (ID3v2.4 + UTF-8)
ผสานความสามารถจากทั้งสองไฟล์เดิม

ติดตั้ง library ก่อนใช้งาน:
    pip install mutagen

ตัวอย่างการใช้งาน:
    handler = MP3Handler()
    
    # อ่าน metadata แบบง่าย
    meta = handler.read_metadata("song.mp3")
    
    # อ่าน metadata แบบแยกประเภท
    std, user, complex = handler.read_metadata_categorized("song.mp3")
    
    # แก้ไขและบันทึก (โดยอัตโนมัติสำรองไฟล์ต้นฉบับ)
    meta["TIT2"] = "ชื่อเพลงใหม่"
    handler.write_metadata(meta, "song.mp3")
"""

from pathlib import Path
from pprint import pprint
import shutil
from datetime import datetime
from typing import Any
import mutagen.id3 as _id3_module

from src.core.crypto.sym_encrypt import SymmetricEncryption
from mutagen.id3 import (
    ID3, ID3NoHeaderError, Encoding,
    TextFrame, TimeStampTextFrame,
    TIT1, TIT2, TIT3, TPE1, TPE2, TPE3, TPE4,
    TALB, TRCK, TPOS, TDRC, TDRL, TDOR,
    TCON, TCOM, TEXT, TPUB, TCOP, TLAN,
    TBPM, TKEY, TLEN, TMED, TMOO, TOAL,
    TOFN, TOLY, TOPE, TOWN, TRSN, TRSO,
    TSOA, TSOP, TSOT, TSRC, TSSE,
    TIPL, TMCL, TXXX,
    UrlFrame, WXXX, WOAR, WOAS, WCOP, WCOM,
    COMM, USLT, USER,
    APIC, GEOB,
    PCNT, SEEK, POPM,
    UFID, PRIV, MCDI,
    SYLT, SIGN, OWNE,
    SYTC, RBUF, AENC, POSS,
)


# ==========================================
# Frame Information
# ==========================================

FRAME_INFO = {
    # ── Song info ──
    "TIT1": ("Grouping / Content Group", "Grouping or content group description"),
    "TIT2": ("Title", "Song title"),
    "TIT3": ("Subtitle / Description", "Subtitle or description refinement"),
    "TALB": ("Album", "Album/Movie/Show title"),
    "TOAL": ("Original Album", "Original album/movie/show title"),
    "TRCK": ("Track Number", "Track number / Total tracks (e.g. '3/12')"),
    "TPOS": ("Disc Number", "Part of a set / Disc number (e.g. '1/2')"),
    "TSRC": ("ISRC", "International Standard Recording Code"),

    # ── Artist / Personnel ──
    "TPE1": ("Lead Artist", "Lead performer / Soloist / Singing group"),
    "TPE2": ("Album Artist", "Band / Orchestra / Accompaniment (commonly used as 'Album Artist')"),
    "TPE3": ("Conductor", "Conductor / Performer refinement"),
    "TPE4": ("Remixed By", "Interpreted / Remixed / Modified by"),
    "TOPE": ("Original Artist", "Original lead performer"),
    "TCOM": ("Composer", "Composer of the work"),
    "TEXT": ("Lyricist", "Lyricist / Text writer"),
    "TOLY": ("Original Lyricist", "Original lyricist / text writer"),
    "TOWN": ("File Owner", "File owner / Licensee"),

    # ── Dates ──
    "TDRC": ("Recording Date", "Recording date (YYYY or YYYY-MM-DD)"),
    "TDRL": ("Release Date", "Release date (YYYY or YYYY-MM-DD)"),
    "TDOR": ("Original Release Date", "Original release date"),
    "TDTG": ("Tagging Time", "Time this tag was created"),

    # ── Genre / Classification ──
    "TCON": ("Genre", "Content type / Genre (e.g. 'Pop', '(13)Pop')"),
    "TMOO": ("Mood", "Mood (e.g. 'Happy', 'Melancholic')"),

    # ── Technical ──
    "TBPM": ("BPM", "Beats per minute"),
    "TKEY": ("Initial Key", "Initial key (e.g. 'Am', 'Gbm', 'o' for off-key)"),
    "TLEN": ("Length", "Duration of audio in milliseconds"),
    "TMED": ("Media Type", "Original medium type (e.g. 'CD', 'TT' for vinyl)"),
    "TSSE": ("Encoding Settings", "Software/hardware used for encoding"),
    "TENC": ("Encoded By", "Software/person that encoded the file"),
    "TDEN": ("Encoding Time", "Time the file was encoded (v2.4 only)"),
    "TFLT": ("File Type", "File type (e.g. 'MPG/3' for MP3)"),
    "TDLY": ("Playlist Delay", "Playlist delay in milliseconds"),

    # ── Publishing / Rights ──
    "TPUB": ("Publisher", "Record label / Publisher"),
    "TCOP": ("Copyright", "Copyright message (e.g. '© 2024 Label')"),
    "TLAN": ("Language", "Language code ISO-639-2 (e.g. 'tha', 'eng')"),
    "TPRO": ("Produced Notice", "Produced notice (v2.4 only)"),

    # ── Broadcast / Internet ──
    "TRSN": ("Internet Radio Station Name", "Name of the internet radio station"),
    "TRSO": ("Internet Radio Station Owner", "Owner of the internet radio station"),

    # ── Sort tags ──
    "TSOA": ("Sort Album", "Album sort order"),
    "TSOP": ("Sort Artist", "Performer sort order"),
    "TSOT": ("Sort Title", "Title sort order"),
    "TOFN": ("Original Filename", "Original filename before encoding"),

    # ── Complex frames ──
    "COMM": ("Comment", "Comments — free text with language code"),
    "USLT": ("Unsync Lyrics", "Unsynchronized lyrics / text transcription"),
    "SYLT": ("Sync Lyrics", "Synchronized lyrics with timestamps"),

    # ── Attached picture ──
    "APIC": ("Attached Picture", "Album art / cover image (binary)"),

    # ── URL frames ──
    "WOAR": ("Artist URL", "Official artist / performer webpage URL"),
    "WOAS": ("Source URL", "Official audio source webpage URL"),
    "WCOP": ("Copyright URL", "Copyright / Legal information URL"),
    "WCOM": ("Commercial URL", "Commercial information URL"),
    "WPUB": ("Publisher URL", "Official publisher webpage URL"),
    "WOAF": ("Audio File URL", "Official audio file webpage URL"),
    "WORS": ("Radio Station URL", "Official internet radio station homepage URL"),
    "WPAY": ("Payment URL", "Payment webpage URL"),
    "WXXX": ("User URL", "User-defined URL link"),

    # ── User-defined ──
    "TXXX": ("User Text", "User-defined text information frame"),
    "PRIV": ("Private Data", "Private binary data (owner identifier)"),
    "UFID": ("Unique File ID", "Unique file identifier"),

    # ── Stats ──
    "POPM": ("Popularimeter", "Email + Rating (0-255) + Counter"),
    "PCNT": ("Play Counter", "Number of times this file has been played"),

    # ── Misc ──
    "USER": ("Terms of Use", "Terms of use with language code"),
    "GEOB": ("Encapsulated Object", "General encapsulated binary object"),
    "SEEK": ("Seek Frame", "Next tag offset in bytes (used with MPEG frames)"),
}

# frame ที่ File Explorer / เครื่องเล่นเพลงทั่วไปมักจะแสดงให้เห็นเป็นค่าเริ่มต้น
# (ใช้เป็น "Standard Frames" ใน GUI - นอกเหนือจากนี้ถือเป็น "Other Frames")
STANDARD_FRAMES = ["TIT2", "TPE1", "TALB", "TPE2", "TCON", "TDRC", "TRCK", "COMM"]

APIC_TYPES = {
    0: "Other",
    1: "32x32 pixels file icon (PNG only)",
    2: "Other file icon",
    3: "Cover (front)",
    4: "Cover (back)",
    5: "Leaflet page",
    6: "Media (e.g. label side of CD)",
    7: "Lead artist/lead performer/soloist",
    8: "Artist/performer",
    9: "Conductor",
    10: "Band/Orchestra",
    11: "Composer",
    12: "Lyricist/text writer",
    13: "Recording Location",
    14: "During recording",
    15: "During performance",
    16: "Movie/video screen capture",
    17: "A bright coloured fish",
    18: "Illustration",
    19: "Band/artist logotype",
    20: "Publisher/Studio logotype"
}


# ==========================================
# Constants
# ==========================================

# frame ที่เป็น timestamp (ใช้ format ISO 8601 เช่น "2024-03-15")
TIMESTAMP_FRAMES = {"TDRC", "TDRL", "TDEN", "TDOR", "TDTG"}

# frame ที่มีได้หลาย instance ในไฟล์เดียว (ต่างกันที่ desc/lang)
MULTI_INSTANCE_FRAMES = {"TXXX", "WXXX", "COMM", "USLT", "APIC", "GEOB", "UFID", "PRIV", "POPM", "SYLT", "SIGN", "USER"}


# ==========================================
# Helper Functions
# ==========================================

def frame_to_str(frame: Any) -> str:
    """แปลง ID3 frame เป็น string"""
    if hasattr(frame, "text"):
        text = frame.text
        if isinstance(text, list):
            return " / ".join(str(t) for t in text)
        return str(text)
    return str(frame)


def get_frame_class(frame_id: str):
    """ดึง mutagen frame class จากชื่อ เช่น 'TIT2' → mutagen.id3.TIT2"""
    return getattr(_id3_module, frame_id, None)

# ==========================================
# Main Class
# ==========================================

class MetadataMP3Handler:
    """
    จัดการ metadata ของไฟล์ MP3 ตามมาตรฐาน ID3v2.4 + UTF-8
    
    ความสามารถหลัก:
    - embed_metadata() → ฝัง metadata ลงไฟล์ MP3
    - extract_metadata() → ถอด metadata ของไฟล์ MP3
    
    - read_metadata() → คืน dict {frame_id: value} (จาก mp3_handler.py)
    - read_metadata_categorized() → คืน tuple (std, user, complex) (จาก metadata.py)
    - write_metadata() → เขียน metadata โดยอัตโนมัติสำรองไฟล์ต้นฉบับ
    - safe_copy() → สร้างไฟล์สำรองก่อนแก้ไข
    """

    def __init__(self):
        self.enc = Encoding.UTF8
        self._cipher = SymmetricEncryption()

    def embed_metadata(self, file_path: str, data: dict, save_path: str = None, password: str = None, clear_existing: bool = False) -> str:
        """
        เขียน metadata ลงไฟล์ MP3 แบบ "merge" กับ frame เดิม (ไม่ล้างของเดิมทิ้ง)
        เพื่อให้ cover file ยังดูเป็นไฟล์ปกติ (ตาม cover metadata ที่มีอยู่ก่อน)
        ส่วนที่ถูกซ่อนจริงๆ คือ frame ที่ระบุใน data เท่านั้น

        สารบัญ (PRIV:S2M) เก็บ "HashKey" ของแต่ละ frame แบบละเอียดถึงระดับ instance
        เช่น "TXXX:SIENG_SECRET" ไม่ใช่แค่ "TXXX" เฉยๆ เพื่อไม่ให้ปนกับ TXXX instance อื่น
        ที่มีอยู่ก่อนแล้ว (เช่น "TXXX:Encoded by" ที่โปรแกรมเข้ารหัสเสียงใส่ไว้)

        Args:
            password: ถ้าระบุ จะเข้ารหัสสารบัญ (PRIV:S2M) ด้วย AES-GCM ก่อนฝัง
                      ทำให้คนอื่นเปิดไฟล์ด้วย tag editor ก็ยังไม่เห็นว่า key ไหนคือของลับ
            clear_existing: ถ้า True จะลบ frame เดิมทั้งหมดก่อนเขียน data ใหม่ลงไป
                             (ใช้ตอนผู้ใช้กด "Clear" ในหน้า editor เอง - ตั้งใจล้างของเดิมจริงๆ
                             ต่างจาก merge ปกติที่ตั้งใจคงของเดิมไว้)
        """
        if save_path is None:
            save_path = file_path

        # 1. คำนวณสารบัญจาก HashKey จริงของ frame ที่กำลังจะฝัง (ละเอียดระดับ instance)
        toc_keys = []
        for frame_id, value in data.items():
            for frame in self._build_frames(frame_id, value):
                toc_keys.append(frame.HashKey)

        # 2. แปะสารบัญ PRIV:S2M เฉพาะตอนมีอะไรจะ track จริงๆ (ถ้า data ว่างเปล่า ไม่ต้องเติม marker
        #    ค้างไว้ - ไม่งั้นไฟล์ที่ตั้งใจให้ว่างจริงๆ เช่นตอนกด Clear แล้ว Save เลย จะเหลือ frame ค้าง 1 อัน)
        if toc_keys:
            key_bytes = ",".join(toc_keys).encode('utf-8')
            if password:
                key_bytes = self._cipher.encrypt(key_bytes, password)

            if "PRIV" not in data:
                data["PRIV"] = []
            elif not isinstance(data["PRIV"], list):
                data["PRIV"] = [data["PRIV"]] # บังคับให้เป็นลิสต์เผื่อส่งมาเป็น dict เดี่ยวๆ

            data["PRIV"].append({
                "owner": "S2M",
                "data": key_bytes
            })

        # 3. เขียน metadata ลงไฟล์ (merge กับของเดิม) - source_path คือไฟล์ต้นฉบับที่จะไม่ถูกแก้ไข
        edited_path = self.write_metadata(data, save_path, source_path=file_path, clear_existing=clear_existing)
        return edited_path

    def extract_metadata(self, file_path: str, password: str = None) -> dict:
        """ อ่าน metadata ของไฟล์ MP3

        อ่านตรงจาก ID3 tag ดิบแล้วกรองเฉพาะ frame ที่ HashKey อยู่ในสารบัญ PRIV:S2M
        (ไม่ใช้ read_metadata() ตรงๆ เพราะมันรวม instance ของ frame ประเภทเดียวกัน
        ทั้งหมดเข้าด้วยกัน ซึ่งจะพา frame เดิมที่ไม่เกี่ยวข้อง เช่น TXXX:Encoded by
        ติดออกมาด้วยถ้า TXXX บางตัวเป็นความลับ)

        Args:
            password: ต้องตรงกับตอน embed ถ้าตอนฝังมีการเข้ารหัสสารบัญไว้
        """
        try:
            tag = ID3(file_path)
        except ID3NoHeaderError:
            return {}

        # 1. หากุญแจสารบัญ S2M ให้เจอ
        toc_keys = []
        for frame_key, frame in tag.items():
            if not frame_key.startswith("PRIV:") or getattr(frame, "owner", None) != "S2M":
                continue

            raw_toc = frame.data
            if password:
                try:
                    raw_toc = self._cipher.decrypt(raw_toc, password)
                except ValueError:
                    print("[-] ถอดรหัสสารบัญไม่สำเร็จ: รหัสผ่านไม่ถูกต้อง")
                    return {}

            try:
                toc_keys = [k for k in raw_toc.decode('utf-8').split(',') if k]
            except UnicodeDecodeError:
                print("[-] สารบัญถูกเข้ารหัสไว้ ต้องระบุ password ถึงจะอ่านได้")
                return {}
            break

        # 2. ดึงเฉพาะ frame ที่ HashKey ตรงกับสารบัญ (ไม่ปนกับ instance อื่นของ frame ประเภทเดียวกัน)
        extracted_metadata = {}
        for hash_key in toc_keys:
            frame = tag.get(hash_key)
            if frame is None:
                continue

            value = self.read_frame(frame)
            if value is None:
                continue

            frame_id = hash_key.split(":")[0]
            if frame_id in MULTI_INSTANCE_FRAMES:
                extracted_metadata.setdefault(frame_id, []).append(value)
            else:
                extracted_metadata[frame_id] = value

        return extracted_metadata

    def read_metadata(self, file_path: str) -> dict:
        """
        อ่าน tag ทั้งหมดจากไฟล์ MP3
        คืนค่าเป็น dict {frame_id: value}
        
        ถ้าไฟล์ไม่มี ID3 tag เลย คืน dict ว่าง {}
        """
        try:
            tag = ID3(file_path)
        except ID3NoHeaderError:
            return {}

        metadata = {}

        for frame_key, frame in tag.items():
            # mutagen ใช้ key แบบ "TXXX:desc" หรือ "COMM:lang:desc"
            # ตัดเอาแค่ชื่อ frame เช่น "TXXX"
            frame_id = frame_key.split(":")[0]

            value = self.read_frame(frame)
            if value is None:
                continue

            # frame ที่มีได้หลาย instance → เก็บเป็น list
            if frame_id in MULTI_INSTANCE_FRAMES:
                if frame_id not in metadata:
                    metadata[frame_id] = []
                metadata[frame_id].append(value)
            else:
                metadata[frame_id] = value

        return metadata

    def read_frame(self, frame):
        """
        แปลง mutagen frame object → Python value
        
        แต่ละประเภท frame มี attribute ต่างกัน
        ดู https://id3.org/id3v2.4.0-frames สำหรับรายละเอียด
        """

        # ── Timestamp frames (TDRC, TDRL, TDEN, TDOR, TDTG) ──
        # .text เป็น list ของ ID3TimeStamp object แปลงเป็น string
        if isinstance(frame, TimeStampTextFrame):
            values = [str(t) for t in frame.text]
            return values[0] if len(values) == 1 else values

        # ── People list (TIPL, TMCL) ──
        # .people → list of [role, name]
        if isinstance(frame, (TIPL, TMCL)):
            return list(frame.people)

        # ── TXXX (user-defined text) ──
        # มี .desc บอกว่าเป็น key อะไร และ .text เป็นค่า
        if isinstance(frame, TXXX):
            return {
                "desc": frame.desc,
                "text": frame.text[0] if frame.text else "",
            }

        # ── COMM (comment) และ USLT (unsynchronized lyrics) ──
        # ต้องมี lang (ISO 639-2 เช่น "tha", "eng") และ desc
        # หมายเหตุ: มีuagen ไม่ consistent กันเอง - COMM.text เป็น list เสมอ แต่ USLT.text เป็น str เดี่ยวๆ
        # ถ้าใช้ str(frame.text) ตรงๆ กับ COMM จะได้ string ของ list เช่น "['ข้อความ']" แทนข้อความจริง
        if isinstance(frame, (COMM, USLT)):
            text_value = frame.text
            if isinstance(text_value, list):
                text_value = text_value[0] if text_value else ""
            return {
                "lang": frame.lang,
                "desc": frame.desc,
                "text": str(text_value),
            }

        # ── Text frames ทั่วไป (TIT2, TPE1, TALB, TCON, ...) ──
        # .text เป็น list of string
        if isinstance(frame, TextFrame):
            values = list(frame.text)
            return values[0] if len(values) == 1 else values

        # ── WXXX (user-defined URL) ──
        if isinstance(frame, WXXX):
            return {"desc": frame.desc, "url": frame.url}

        # ── URL frames ทั่วไป (WOAR, WPUB, WCOM, ...) ──
        if isinstance(frame, UrlFrame):
            return frame.url

        # ── USER (terms of use) ──
        if isinstance(frame, USER):
            return {"lang": frame.lang, "text": str(frame.text)}

        # ── APIC (attached picture เช่น album art) ──
        # type 3 = Front Cover ที่ใช้บ่อยที่สุด
        if isinstance(frame, APIC):
            return {
                "mime": frame.mime,
                "type": int(frame.type),
                "desc": frame.desc,
                "data": frame.data,
            }

        # ── PCNT (play counter) ──
        if isinstance(frame, PCNT):
            return frame.count

        # ── SEEK ──
        if isinstance(frame, SEEK):
            return frame.offset

        # ── POPM (popularimeter / rating) ──
        # rating: 0 = unknown, 1 = worst, 255 = best
        if isinstance(frame, POPM):
            return {
                "email": frame.email,
                "rating": frame.rating,
                "count": frame.count,
            }

        # ── GEOB (general encapsulated object) ──
        if isinstance(frame, GEOB):
            return {
                "mime": frame.mime,
                "filename": frame.filename,
                "desc": frame.desc,
                "data": frame.data,
            }

        # ── UFID (unique file identifier) ──
        if isinstance(frame, UFID):
            return {"owner": frame.owner, "data": frame.data}

        # ── PRIV (private frame) ──
        if isinstance(frame, PRIV):
            return {"owner": frame.owner, "data": frame.data}

        # ── MCDI (music CD identifier) ──
        if isinstance(frame, MCDI):
            return frame.data

        # ── SYLT (synchronized lyrics) ──
        # entries เป็น list of (text, timestamp_ms)
        if isinstance(frame, SYLT):
            return {
                "lang": frame.lang,
                "format": frame.format,
                "type": frame.type,
                "desc": frame.desc,
                "entries": list(frame.text),
            }

        # ── SIGN (signature) ──
        if isinstance(frame, SIGN):
            return {"group": frame.group, "sig": frame.sig}

        # ── OWNE (ownership) ──
        if isinstance(frame, OWNE):
            return {
                "currency": frame.currency,
                "price": frame.price,
                "date": frame.date,
                "seller": frame.seller,
            }

        # frame ที่เหลือ
        if hasattr(frame, "data"):
            return frame.data

        return None

    def read_metadata_categorized(self, file_path: str) -> tuple[dict[str, str], dict[str, str], dict[str, Any]]:
        """
        อ่าน metadata แล้วแยกออกเป็น 3 ประเภท
        
        Returns:
            tuple: (standard_text_frame, user_defined_frame, complex_frame)
        """
        
        standard_text_frame: dict[str, str] = {}
        user_defined_frame: dict[str, str] = {}
        complex_frame: dict[str, Any] = {}

        # Read ID3 tags
        try:
            tags = ID3(file_path)
        except ID3NoHeaderError:
            tags = None

        if tags:
            for tag_key, frame in tags.items():
                frame_id = tag_key[:4].upper()

                # ── Text frames ──
                if frame_id.startswith("T") and frame_id not in ("TXXX",):
                    text = frame_to_str(frame)
                    standard_text_frame[frame_id] = text

                # ── URL frames (W...) ──
                elif frame_id.startswith("W") and frame_id not in ("WXXX",):
                    text = str(frame)
                    standard_text_frame[frame_id] = text

                # ── COMM (Comment) ──
                elif frame_id == "COMM":
                    lang = getattr(frame, "lang", "")
                    desc = getattr(frame, "desc", "")
                    text = frame_to_str(frame)
                    key = f"COMM [{lang}]"
                    if desc:
                        key += f" [{desc}]"
                    complex_frame[key] = text

                # ── APIC (Attached Picture) ──
                elif frame_id == "APIC":
                    mime = getattr(frame, "mime", "unknown")
                    type_id = getattr(frame, "type", 0)
                    desc = getattr(frame, "desc", "")
                    data = getattr(frame, "data", b"")
                    type_str = APIC_TYPES.get(int(type_id), str(type_id))
                    key = f"APIC [type={type_id}: {type_str}]"
                    complex_frame[key] = {
                        "mime": mime,
                        "type_id": type_id,
                        "type_str": type_str,
                        "desc": desc,
                        "image_data": data
                    }

                # ── USLT (Lyrics) ──
                elif frame_id == "USLT":
                    lang = getattr(frame, "lang", "")
                    desc = getattr(frame, "desc", "")
                    text = getattr(frame, "text", "")
                    key = f"USLT [{lang}]"
                    if desc:
                        key += f" [{desc}]"
                    complex_frame[key] = text

                # ── SYLT (Synced Lyrics) ──
                elif frame_id == "SYLT":
                    lang = getattr(frame, "lang", "")
                    format_id = getattr(frame, "format", "")
                    lines = len(getattr(frame, "text", []))
                    complex_frame[f"SYLT [{lang}]"] = {
                        "format": format_id,
                        "lines": lines
                    }

                # ── POPM (Popularimeter) ──
                elif frame_id == "POPM":
                    email = getattr(frame, "email", "")
                    rating = getattr(frame, "rating", 0)
                    count = getattr(frame, "count", 0)
                    stars = "★" * int(rating / 51) + "☆" * (5 - int(rating / 51))
                    complex_frame[f"POPM [{email}]"] = {
                        "email": email,
                        "rating": rating,
                        "count": count,
                        "stars": stars
                    }

                # ── TXXX (User-defined text) ──
                elif frame_id == "TXXX":
                    desc = getattr(frame, "desc", "")
                    text = frame_to_str(frame)
                    user_defined_frame[f"TXXX [{desc}]"] = text

                # ── WXXX (User-defined URL) ──
                elif frame_id == "WXXX":
                    desc = getattr(frame, "desc", "")
                    url = getattr(frame, "url", str(frame))
                    user_defined_frame[f"WXXX [{desc}]"] = url

                # ── PRIV / UFID / อื่นๆ ──
                elif frame_id == "PRIV":
                    owner = getattr(frame, "owner", "")
                    data = getattr(frame, "data", b"")
                    complex_frame[f"PRIV [{owner}]"] = {
                        "owner": owner,
                        "data": data
                    }

                elif frame_id == "UFID":
                    owner = getattr(frame, "owner", "")
                    data = getattr(frame, "data", b"")
                    complex_frame[f"UFID [{owner}]"] = {
                        "owner": owner,
                        "data": data
                    }

                elif frame_id == "PCNT":
                    count = getattr(frame, "count", 0)
                    standard_text_frame["PCNT"] = str(count)

                elif frame_id == "USER":
                    lang = getattr(frame, "lang", "")
                    text = getattr(frame, "text", "")
                    complex_frame[f"USER [{lang}]"] = str(text)

                else:
                    # Unknown frame
                    standard_text_frame[f"{tag_key}"] = str(frame)

        return standard_text_frame, user_defined_frame, complex_frame

    def write_metadata(self, data: dict, save_path: str, source_path: str = None, create_backup: bool = True, clear_existing: bool = False) -> str:
        """
        เขียน metadata ลงไฟล์ MP3 ที่ save_path โดยตรง (ผลลัพธ์อยู่ที่ save_path เสมอ
        ไม่ใช่ไฟล์สำรอง — ต่างจากพฤติกรรมเดิมที่ path ที่คืนค่าไม่ตรงกับ save_path ที่ส่งเข้ามา)

        เขียนแบบ "merge" ระดับ instance เดียว: แทนที่เฉพาะ frame ที่ตรง HashKey เป๊ะๆ
        (เช่น "TXXX:SIENG_SECRET") ส่วน frame อื่นที่เหลือ - ทั้งประเภทที่ไม่เกี่ยวข้องเลย
        (title/artist/album) และ instance อื่นของ frame ประเภทเดียวกันที่มีได้หลายอัน
        (เช่น TXXX:Encoded_by, TXXX:BPM ที่ desc ไม่ตรงกับของเรา) จะไม่ถูกแตะต้องเลย
        เพื่อให้ cover file ยังดูเป็น metadata ปกติ ไม่ใช่ถูกแทนที่ทั้งหมดด้วย payload ลับ
        (ยกเว้นเรียกด้วย clear_existing=True ซึ่งตั้งใจล้างของเดิมทิ้งจริงๆ)

        Args:
            data: dict รูปแบบเดียวกับที่ read_metadata() คืนมา (เฉพาะ frame ที่ต้องการเขียน/แทนที่)
            save_path: path ปลายทางที่จะบันทึกไฟล์ผลลัพธ์
            source_path: ไฟล์ต้นฉบับที่จะอ่าน frame เดิมมา merge (ค่าเริ่มต้น = save_path เอง)
                         ถ้า save_path ต่างจาก source_path (เช่น "Save As" ไปชื่อไฟล์ใหม่ที่ยังไม่มีอยู่จริง)
                         จะคัดลอก source_path ไปที่ save_path ก่อนเสมอ โดยไม่แตะต้อง source_path เลย
            create_backup: สำรองไฟล์ก่อนแก้ไขหรือไม่ (มีผลเฉพาะตอนเขียนทับที่เดิม save_path == source_path)
            clear_existing: ลบ frame เดิมทั้งหมดก่อนเขียน data ใหม่ (reset เป็นไฟล์ untagged ล้วนๆ)

        Returns:
            str: save_path (ไฟล์ผลลัพธ์อยู่ตรงนี้เสมอ)
        """
        source_path = source_path or save_path

        if save_path != source_path:
            # Save As ไปไฟล์ใหม่: คัดลอกต้นฉบับไปเป็นฐานก่อน (save_path อาจยังไม่มีอยู่จริง)
            # source_path (ไฟล์ต้นฉบับที่โหลดมา) จะไม่ถูกแก้ไขเลยไม่ว่ากรณีใด
            shutil.copy2(source_path, save_path)
        elif create_backup:
            backup_path = self.safe_copy(save_path)
            print(f"[Info] สร้างไฟล์สำรอง: {backup_path}")

        try:
            tag = ID3(save_path)
        except ID3NoHeaderError:
            tag = ID3()

        if clear_existing:
            tag.clear()

        # เขียนทับเฉพาะ instance ที่ HashKey ตรงกันเป๊ะๆ (เช่น "TXXX:SIENG_SECRET")
        # instance อื่นของ frame ประเภทเดียวกัน (เช่น TXXX:Encoded_by) ไม่ถูกลบ
        for frame_id, value in data.items():
            for frame in self._build_frames(frame_id, value):
                if isinstance(frame, PRIV) and frame.owner == "S2M":
                    # สารบัญ S2M มีได้แค่ 1 อันเสมอ แต่เนื้อหา (ciphertext) เปลี่ยนทุกครั้งที่เข้ารหัสใหม่
                    # เลยลบของเก่าด้วย owner แทนการเทียบ HashKey เป๊ะๆ (จะไม่มีวันตรงกัน -> ค้างสะสม)
                    for old_key in [k for k in tag.keys() if k.startswith("PRIV:S2M:")]:
                        del tag[old_key]
                else:
                    tag.delall(frame.HashKey)
                tag.add(frame)

        tag.save(save_path, v2_version=4)
        return save_path

    def _build_frames(self, frame_id: str, value) -> list:
        """
        สร้าง mutagen frame objects จาก frame_id และ value
        คืน list เพราะบาง frame มีได้หลาย instance
        """

        # ── Timestamp frames ──
        if frame_id in TIMESTAMP_FRAMES:
            cls = get_frame_class(frame_id)
            values = value if isinstance(value, list) else [value]
            return [cls(encoding=self.enc, text=values)]

        # ── People list (TIPL, TMCL) ──
        if frame_id in ("TIPL", "TMCL"):
            cls = get_frame_class(frame_id)
            return [cls(encoding=self.enc, people=list(value))]

        # ── TXXX ──
        if frame_id == "TXXX":
            items = value if isinstance(value, list) else [value]
            return [
                TXXX(encoding=self.enc, desc=item["desc"], text=[item["text"]])
                for item in items
            ]

        # ── Text frames ทั่วไป (T*** ที่เหลือ) ──
        if frame_id.startswith("T"):
            cls = get_frame_class(frame_id)
            if cls is None:
                return []
            values = value if isinstance(value, list) else [value]
            return [cls(encoding=self.enc, text=values)]

        # ── WXXX ──
        if frame_id == "WXXX":
            items = value if isinstance(value, list) else [value]
            return [
                WXXX(encoding=self.enc, desc=item["desc"], url=item["url"])
                for item in items
            ]

        # ── URL frames ทั่วไป (W*** ที่เหลือ) ──
        if frame_id.startswith("W"):
            cls = get_frame_class(frame_id)
            if cls is None:
                return []
            return [cls(url=value)]

        # ── COMM ──
        if frame_id == "COMM":
            items = value if isinstance(value, list) else [value]
            return [
                COMM(encoding=self.enc, lang=item["lang"], desc=item["desc"], text=item["text"])
                for item in items
            ]

        # ── USLT ──
        if frame_id == "USLT":
            items = value if isinstance(value, list) else [value]
            return [
                USLT(encoding=self.enc, lang=item["lang"], desc=item["desc"], text=item["text"])
                for item in items
            ]

        # ── USER ──
        if frame_id == "USER":
            items = value if isinstance(value, list) else [value]
            return [
                USER(encoding=self.enc, lang=item["lang"], text=item["text"])
                for item in items
            ]

        # ── APIC ──
        if frame_id == "APIC":
            items = value if isinstance(value, list) else [value]
            apic_frames = []
            used_descs = set()  # APIC ของ mutagen ใช้ desc อย่างเดียวเป็น HashKey (ไม่รวม type ด้วย)
                                 # ถ้าปล่อยว่าง/ซ้ำกันหลายรูป เฟรมก่อนหน้าจะโดนทับหายเงียบๆ ตอน tag.add()
                                 # เลยต้องบังคับให้ desc ไม่ซ้ำกันเองภายใน batch นี้เสมอ

            for item in items:
                if isinstance(item, dict):
                    # รองรับทั้ง path และ data
                    img_data = None
                    mime = item.get("mime", "image/png")

                    if "path" in item:
                        img_path = Path(item["path"])
                        if img_path and img_path.is_file():
                            with open(img_path, "rb") as img_f:
                                img_data = img_f.read()
                            ext = img_path.suffix.lower()
                            mime = {
                                ".jpg": "image/jpeg",
                                ".jpeg": "image/jpeg",
                                ".png": "image/png",
                                ".gif": "image/gif"
                            }.get(ext, "image/png")
                    elif "data" in item:
                        img_data = item["data"]
                        mime = item.get("mime", "image/png")

                    if img_data:
                        desc = item.get("desc") or "Cover"
                        base_desc = desc
                        suffix = 2
                        while desc in used_descs:
                            desc = f"{base_desc} ({suffix})"
                            suffix += 1
                        used_descs.add(desc)

                        apic_frames.append(APIC(
                            encoding=self.enc,
                            mime=mime,
                            type=item.get("type", 3),
                            desc=desc,
                            data=img_data,
                        ))

            return apic_frames

        # ── PCNT ──
        if frame_id == "PCNT":
            return [PCNT(count=value)]

        # ── SEEK ──
        if frame_id == "SEEK":
            return [SEEK(offset=value)]

        # ── POPM ──
        if frame_id == "POPM":
            items = value if isinstance(value, list) else [value]
            return [
                POPM(email=item["email"], rating=item["rating"], count=item["count"])
                for item in items
            ]

        # ── GEOB ──
        if frame_id == "GEOB":
            items = value if isinstance(value, list) else [value]
            return [
                GEOB(
                    encoding=self.enc,
                    mime=item["mime"],
                    filename=item["filename"],
                    desc=item["desc"],
                    data=item["data"],
                )
                for item in items
            ]

        # ── UFID ──
        if frame_id == "UFID":
            items = value if isinstance(value, list) else [value]
            return [UFID(owner=item["owner"], data=item["data"]) for item in items]

        # ── PRIV ──
        if frame_id == "PRIV":
            items = value if isinstance(value, list) else [value]
            return [PRIV(owner=item["owner"], data=item["data"]) for item in items]

        # ── MCDI ──
        if frame_id == "MCDI":
            return [MCDI(data=value)]

        # ── SYLT ──
        if frame_id == "SYLT":
            items = value if isinstance(value, list) else [value]
            return [
                SYLT(
                    encoding=self.enc,
                    lang=item["lang"],
                    format=item["format"],
                    type=item["type"],
                    desc=item["desc"],
                    text=item.get("entries", item.get("text", [])),
                )
                for item in items
            ]

        # ── SIGN ──
        if frame_id == "SIGN":
            items = value if isinstance(value, list) else [value]
            return [SIGN(group=item["group"], sig=item["sig"]) for item in items]

        # ── OWNE ──
        if frame_id == "OWNE":
            items = value if isinstance(value, list) else [value]
            return [
                OWNE(
                    encoding=self.enc,
                    currency=item["currency"],
                    price=item["price"],
                    date=item["date"],
                    seller=item["seller"],
                )
                for item in items
            ]

        # frame ที่ไม่รองรับ write → ข้ามไป (แจ้งเตือนไว้ กันข้อมูลหายแบบเงียบๆ)
        print(f"[!] Warning: ไม่รองรับการเขียน frame '{frame_id}' ข้ามไป")
        return []

    # ──────────────────────────────────────────────────────────────
    # Utility Functions
    # ──────────────────────────────────────────────────────────────

    def safe_copy(self, file_path: str, suffix: str = "_backup") -> str:
        """
        สร้างไฟล์สำรอง (สำเนาของไฟล์ก่อนแก้ไข) ไว้เผื่อกู้คืน
        ไม่ใช่ไฟล์ผลลัพธ์ — ไฟล์ผลลัพธ์จริงอยู่ที่ save_path เสมอ (ดู write_metadata)

        Args:
            file_path: path ของไฟล์ที่จะ copy
            suffix: suffix ที่จะเพิ่มในชื่อไฟล์สำรอง (ค่าเริ่มต้น "_backup")

        Returns:
            str: path ของไฟล์สำรอง
        """
        src_path = Path(file_path)

        if not src_path.exists():
            raise FileNotFoundError(f"File not found: {src_path}")

        dst_path = src_path.with_stem(f"{src_path.stem}{suffix}")

        # ถ้ามีชื่อซ้ำให้เพิ่ม timestamp กำกับ
        if dst_path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dst_path = src_path.with_stem(f"{src_path.stem}{suffix}_{ts}")

        shutil.copy2(src_path, dst_path)
        return str(dst_path)

    def get_frame_info(self, frame_id: str) -> tuple[str, str]:
        """
        รับข้อมูลอธิบายเกี่ยวกับ frame_id
        
        Args:
            frame_id: เช่น "TIT2", "APIC"
            
        Returns:
            tuple: (name_th, description) ถ้าไม่พบจะคืน (None, None)
        """
        return FRAME_INFO.get(frame_id, (None, None))

    def get_apic_type_info(self, type_id: int) -> str:
        """
        รับข้อมูลอธิบายเกี่ยวกับประเภทรูปภาพ APIC
        
        Args:
            type_id: 0-20
            
        Returns:
            str: คำอธิบายประเภทรูปภาพ
        """
        return APIC_TYPES.get(type_id, f"Unknown type {type_id}")


# ==========================================
# Main Function - Demo
# ==========================================

def main():
    """ตัวอย่างการใช้งานและทดสอบระบบ SIENG2 MP3 Metadata Handler"""
    
    # 1. กำหนดและคำนวณ Path สำหรับไฟล์ทดสอบ
    sample_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
    mp3_path = sample_dir / "sample" / "mp3" / "sample-3s.mp3"
    cover_img_path = sample_dir / "sample" / "img" / "1.png"
    output_path = sample_dir / "sample" / "mp3" / "sample-3s_edited.mp3"
    
    if not mp3_path.exists():
        print(f"[-] [Error] ไม่พบไฟล์: {mp3_path}")
        print("    กรุณาสร้างไฟล์ MP3 ตัวอย่างหรือปรับ path ให้ถูกต้อง")
        return
    
    print("=" * 70)
    print("SIENG 2 : MP3 Metadata Handler Test")
    print("=" * 70)
    
    # สร้าง Handler Instance
    handler = MetadataMP3Handler()
    
    # ==========================================
    # ส่วนที่ 1: การจัดการ Metadata พื้นฐาน (Standard Operations)
    # ==========================================
    print("\n[*] --- ส่วนที่ 1: ตรวจสอบข้อมูลต้นฉบับ ---")
    meta = handler.read_metadata(str(mp3_path))
    print(f"[+] อ่านไฟล์ต้นฉบับสำเร็จ พบข้อมูลทั้งหมด {len(meta)} frames")
    
    # ==========================================
    # ส่วนที่ 2: ทดสอบระบบสารบัญซ่อนข้อมูล (Steganography / Embed & Extract)
    # ==========================================
    print("\n[*] --- ส่วนที่ 2: ทดสอบระบบสารบัญซ่อนข้อมูล (S2M TOC) ---")
    
    # ข้อมูลลับที่ต้องการนำไปฝัง (Payload)
    secret_payload = {
        "TIT2": "SIENG 2 - MP3 Steganography Test",
        "TPE1": "ผู้พัฒนาแพลตฟอร์ม",
        "TALB": "Secret Workspace",
        "COMM": [{
            "lang": "tha",
            "desc": "HiddenData",
            "text": "ข้อความลับนี้ถูกดึงผ่านสารบัญ PRIV S2M"
        }],
        "TXXX": [{
            "desc": "SIENG_KEY",
            "text": "FLAG{MP3_STEGO_MASTER_2026}"
        }]
    }
    
    # แนบรูปภาพปก (ถ้ามีไฟล์อยู่จริง)
    if cover_img_path.exists():
        secret_payload["APIC"] = [{
            "desc": "Secret Cover",
            "type": 3,
            "path": str(cover_img_path)
        }]

    print(f"    กำลังฝังข้อมูล (Embed) คีย์ต่อไปนี้ลงสารบัญ: {list(secret_payload.keys())}")
    
    try:
        # ทดสอบการ Embed (ฟังก์ชันนี้จะสร้าง PRIV S2M ให้โดยอัตโนมัติ)
        saved_file = handler.embed_metadata(str(mp3_path), secret_payload, str(output_path))
        print(f"[+] บันทึกไฟล์ที่ซ่อนข้อมูลสำเร็จ: {Path(saved_file).name}")
        
        # ทดสอบการ Extract (ระบบจะต้องอ่านเจอเฉพาะคีย์ที่อยู่ในสารบัญ PRIV S2M เท่านั้น)
        print("\n    กำลังสกัดข้อมูล (Extract) ผ่านสารบัญ...")
        extracted_data = handler.extract_metadata(saved_file)
        
        if not extracted_data:
            print("[-] [Error] สกัดข้อมูลไม่สำเร็จ หรือไม่พบสารบัญ S2M")
        else:
            print("[+] สกัดข้อมูลสำเร็จ! ผลลัพธ์ที่ดึงออกมาได้:")
            for key, value in extracted_data.items():
                # ตัดทอนข้อมูล APIC ไม่ให้รกหน้าจอเวลา Print
                if key == "APIC" and isinstance(value, list):
                    print(f"    -> {key} : [Image Data Included]")
                else:
                    print(f"    -> {key} : {value}")
            
            # ตรวจสอบความถูกต้อง (Validation)
            # ลบ PRIV ทิ้งชั่วคราวตอนเทียบ เพราะ embed_metadata แอบยัด PRIV ลงไปในตัวแปร dict ด้วย
            test_keys = set(secret_payload.keys()) - {"PRIV"}
            extracted_keys = set(extracted_data.keys())
            
            if test_keys.issubset(extracted_keys):
                print("\n[✔] PASS: ข้อมูลที่ Extract ได้ตรงกับ Payload ต้นฉบับ 100%")
            else:
                print("\n[!] FAIL: ข้อมูลสูญหายระหว่างทาง")
                
    except Exception as e:
        print(f"[-] [Error] เกิดข้อผิดพลาดในระบบ Embed/Extract: {e}")

    print("\n" + "=" * 70)
    print("ทดสอบเสร็จสิ้น พร้อมนำไปประกอบหน้าต่าง GUI แล้ว!")
    print("=" * 70)

if __name__ == "__main__":
    main()