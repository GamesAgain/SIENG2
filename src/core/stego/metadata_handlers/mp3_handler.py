"""
Metadata-MP3: อ่าน/แก้ frame ID3 ของ MP3 แบบ Metadata editor (คู่กับ png_handler.py)

ขั้นตอนการใช้งาน
1. read_frames(path)                  -> frame ที่ editor แก้ได้ทั้งหมด {key: MP3Field}
2. ผู้ใช้ เพิ่ม / แก้ / ลบ field
3. write_frames(source, dest, edited) -> บันทึกเป็น ID3v2.3
   field ที่ผู้ใช้ "เพิ่ม" หรือ "แก้" = secret -> จด key ไว้ใน TOC (frame PRIV owner 'S2M')
   (field ที่ลบ หรือค่าเท่าเดิม ไม่นับ)
4. ฝั่งถอด read_secret(path)          -> คืนเฉพาะ field ที่อยู่ใน TOC (สิ่งที่ผู้ส่งเพิ่ม/แก้)

ขอบเขตที่ editor แก้ได้: Text (T***), URL (W***), TXXX, WXXX, COMM, USLT, APIC
frame อื่น (PRIV, GEOB, POPM, UFID ...) เก็บไว้ไม่แตะ · ไม่แตะข้อมูลเสียง (ตรวจ hash ก่อน/หลัง)
key ของ field = HashKey ของ mutagen เช่น TIT2, WOAR:<url>, TXXX:<desc>, APIC:<desc>, COMM:<desc>:<lang>
"""
import os
import re
import shutil
import tempfile
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import mutagen.id3 as id3
from mutagen import MutagenError
from mutagen.id3 import APIC, ID3, PRIV, ID3NoHeaderError, Encoding, TextFrame, UrlFrame
from mutagen.mp3 import MP3

TOC_OWNER = "S2M"
TOC_DELIMITER = "\n"  # key ห้ามมี newline (check_field ตรวจ) จึงใช้คั่นได้ปลอดภัย

# frame ที่มี desc (และ lang) เป็นส่วนหนึ่งของ key -> มีได้หลายตัวในไฟล์เดียว
DESC_FRAMES = {"TXXX", "WXXX", "COMM", "USLT", "APIC"}
LANG_FRAMES = {"COMM", "USLT"}

# frame วันที่ของ v2.3 - mutagen อ่านแล้วรวมเป็น TDRC/TDOR ให้เอง จึงให้แก้ผ่าน TDRC/TDOR แทน
V23_DATE_FRAMES = {"TYER", "TDAT", "TIME", "TORY", "TRDA", "TSIZ"}

# frame ข้อความที่มีเฉพาะใน v2.4 -> บันทึกเป็น v2.3 ไม่ได้ ผู้ใช้ต้องลบใน editor เอง
V24_ONLY_TEXT = {"TDEN", "TDRL", "TDTG", "TMOO", "TPRO", "TSOA", "TSOP", "TSOT", "TSST"}

# frame นอกขอบเขตที่มีเฉพาะใน v2.4 -> editor ไม่แสดง จึงต้องให้ผู้ใช้ยืนยันก่อนทิ้ง (drop_unsupported)
V24_ONLY_OTHER = {"ASPI", "EQU2", "RVA2", "SEEK", "SIGN", "TMCL"}

# ชื่อ/คำอธิบายของ frame ไว้แสดงใน editor (เฉพาะที่บันทึกเป็น v2.3 ได้)
FRAME_INFO = {
    # ── Song info ──
    "TIT1": ("Grouping", "Grouping or content group description"),
    "TIT2": ("Title", "Song title"),
    "TIT3": ("Subtitle", "Subtitle or description refinement"),
    "TALB": ("Album", "Album/Movie/Show title"),
    "TOAL": ("Original Album", "Original album/movie/show title"),
    "TRCK": ("Track Number", "Track number / Total tracks (e.g. '3/12')"),
    "TPOS": ("Disc Number", "Part of a set / Disc number (e.g. '1/2')"),
    "TSRC": ("ISRC", "International Standard Recording Code"),
    # ── Artist / Personnel ──
    "TPE1": ("Lead Artist", "Lead performer / Soloist / Singing group"),
    "TPE2": ("Album Artist", "Band / Orchestra / Accompaniment"),
    "TPE3": ("Conductor", "Conductor / Performer refinement"),
    "TPE4": ("Remixed By", "Interpreted / Remixed / Modified by"),
    "TOPE": ("Original Artist", "Original lead performer"),
    "TCOM": ("Composer", "Composer of the work"),
    "TEXT": ("Lyricist", "Lyricist / Text writer"),
    "TOLY": ("Original Lyricist", "Original lyricist / text writer"),
    "TOWN": ("File Owner", "File owner / Licensee"),
    # ── Dates ──
    "TDRC": ("Recording Date", "Recording date (YYYY or YYYY-MM-DD)"),
    "TDOR": ("Original Release Year", "Original release year (YYYY)"),
    # ── Genre / Technical ──
    "TCON": ("Genre", "Content type / Genre (e.g. 'Pop')"),
    "TBPM": ("BPM", "Beats per minute"),
    "TKEY": ("Initial Key", "Initial key (e.g. 'Am')"),
    "TLEN": ("Length", "Duration of audio in milliseconds"),
    "TMED": ("Media Type", "Original medium type (e.g. 'CD')"),
    "TSSE": ("Encoding Settings", "Software/hardware used for encoding"),
    "TENC": ("Encoded By", "Software/person that encoded the file"),
    "TFLT": ("File Type", "File type (e.g. 'MPG/3')"),
    "TDLY": ("Playlist Delay", "Playlist delay in milliseconds"),
    # ── Publishing / Rights ──
    "TPUB": ("Publisher", "Record label / Publisher"),
    "TCOP": ("Copyright", "Copyright message"),
    "TLAN": ("Language", "Language code ISO-639-2 (e.g. 'tha')"),
    "TRSN": ("Internet Radio Station Name", "Name of the internet radio station"),
    "TRSO": ("Internet Radio Station Owner", "Owner of the internet radio station"),
    "TOFN": ("Original Filename", "Original filename"),
    # ── User-defined / Complex ──
    "TXXX": ("User Text", "User-defined text (description + value)"),
    "COMM": ("Comment", "Comment (description + language + text)"),
    "USLT": ("Lyrics", "Unsynchronized lyrics (description + language + text)"),
    "APIC": ("Attached Picture", "Cover image (MIME + picture type + description + image bytes)"),
    # ── URL ──
    "WOAR": ("Artist URL", "Official artist webpage"),
    "WOAS": ("Source URL", "Official audio source webpage"),
    "WOAF": ("Audio File URL", "Official audio file webpage"),
    "WCOP": ("Copyright URL", "Copyright / Legal information"),
    "WCOM": ("Commercial URL", "Commercial information"),
    "WPUB": ("Publisher URL", "Official publisher webpage"),
    "WORS": ("Radio Station URL", "Official internet radio station homepage"),
    "WPAY": ("Payment URL", "Payment webpage"),
    "WXXX": ("User URL", "User-defined URL (description + URL)"),
    # ── นอกขอบเขต (แสดงใน View all เท่านั้น) ──
    "PRIV": ("Private Data", "Private binary data"),
    "UFID": ("Unique File ID", "Unique file identifier"),
    "POPM": ("Popularimeter", "Email + Rating + Counter"),
    "PCNT": ("Play Counter", "Number of times played"),
    "GEOB": ("Encapsulated Object", "General encapsulated binary object"),
    "SYLT": ("Synced Lyrics", "Synchronized lyrics"),
    "USER": ("Terms of Use", "Terms of use"),
}

# frame ที่ File Explorer / เครื่องเล่นเพลงทั่วไปแสดงเป็นค่าเริ่มต้น (GUI ใช้แยกกลุ่ม)
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
    20: "Publisher/Studio logotype",
}


@dataclass(frozen=True)
class MP3Field:
    """ค่าของ 1 field ใน editor - ใช้เฉพาะช่องที่ frame ชนิดนั้นมี (ไม่เก็บ encoding)"""
    frame_id: str                                 # "TIT2", "WOAR", "TXXX", "COMM", "APIC" ...
    text: str = ""                                # ข้อความ หรือ url (หลายค่าคั่นด้วย "/")
    desc: str = ""                                # TXXX / WXXX / COMM / USLT / APIC
    lang: str = "eng"                             # COMM / USLT
    mime: str = ""                                # APIC
    picture_type: int = 3                         # APIC (3 = ปกหน้า)
    data: bytes = field(default=b"", repr=False)  # APIC: ไบต์ภาพดิบ

    @property
    def key(self) -> str:
        """Same as mutagen's HashKey: TIT2 / WOAR:<url> / TXXX:<desc> / COMM:<desc>:<lang>."""
        if self.frame_id in LANG_FRAMES:
            return f"{self.frame_id}:{self.desc}:{self.lang}"
        if self.frame_id in DESC_FRAMES:
            return f"{self.frame_id}:{self.desc}"
        if self.frame_id.startswith("W"):
            return f"{self.frame_id}:{self.text}"  # URL frame มีหลายตัวได้ แยกกันด้วย url
        return self.frame_id


class MetadataMP3Handler:
    """Read and edit the ID3 frames of an MP3; the added/modified fields are the secret."""

    # ================= Public API =================

    def read_frames(self, path: str) -> dict[str, MP3Field]:
        """Every frame the editor can change, as {key: MP3Field}."""
        return self.fields_of(self.load_tags(path))

    def read_other_frames(self, path: str) -> dict[str, str]:
        """View all: frames outside the editor (not the TOC) as short text."""
        tags = self.load_tags(path)
        others = {key: frame.pprint().split("=", 1)[-1] for key, frame in tags.items()
                  if not self.is_editable(frame.FrameID) and not self.is_toc(frame)}
        for raw in tags.unknown_frames:
            others[f"{self.unknown_name(raw)} (unknown)"] = f"{len(raw)} bytes"
        return others

    def read_unsupported(self, path: str) -> list[str]:
        """Frames outside the editor that ID3v2.3 cannot keep (ask the user before dropping them)."""
        return self.unsupported_frames(self.load_tags(path))

    @staticmethod
    def changed_keys(original: dict[str, MP3Field], edited: dict[str, MP3Field]) -> list[str]:
        """Keys the user added or modified. A deleted key, or a value that is still the same, does not count."""
        return [key for key, value in edited.items() if original.get(key) != value]

    def write_frames(self, source: str, destination: str, edited: dict[str, MP3Field],
                     drop_unsupported: bool = False) -> list[str]:
        """
        Save `edited` as the editable frames of the MP3 (ID3v2.3) + the TOC of the changed keys.
        Frames outside the editor are kept. Returns the changed (secret) keys.
        The source file is never modified.
        """
        # 1. ตรวจข้อมูลก่อน จะได้ไม่เขียนไฟล์เสียครึ่งทาง
        for key, value in edited.items():
            self.check_field(key, value)
        v24_only = [key for key, value in edited.items() if value.frame_id in V24_ONLY_TEXT]
        if v24_only:
            raise ValueError(f"{', '.join(v24_only)} cannot be saved as ID3v2.3. "
                             "Delete these fields and save again.")

        # 2. อ่านไฟล์ต้นฉบับ แล้วหาว่าผู้ใช้เพิ่ม/แก้ field ไหน
        tags = self.load_tags(source)
        secret_keys = self.changed_keys(self.fields_of(tags), edited)

        # 3. frame นอกขอบเขตที่ v2.3 เก็บไม่ได้ - editor ไม่แสดง ผู้ใช้ลบเองไม่ได้ จึงต้องยืนยันก่อนทิ้ง
        unsupported = self.unsupported_frames(tags)
        if unsupported and not drop_unsupported:
            raise ValueError(f"These frames cannot be kept in ID3v2.3: {', '.join(unsupported)}. "
                             "Save again with drop_unsupported=True to remove them.")
        for key, frame in list(tags.items()):
            if frame.FrameID in V24_ONLY_OTHER:
                del tags[key]
        if tags.version[1] != 3:
            tags.unknown_frames = []  # mutagen เขียน unknown frame ได้เฉพาะเวอร์ชันเดิมของมัน

        # 4. ทิ้ง frame ในขอบเขต + TOC เดิม แล้วสร้างใหม่จาก edited (frame นอกขอบเขตไม่แตะ)
        for key, frame in list(tags.items()):
            if self.is_editable(frame.FrameID) or self.is_toc(frame):
                del tags[key]
        kept_keys = self.other_keys(tags)
        for value in edited.values():
            tags.add(self.frame_of(value))
        if secret_keys:
            tags.add(PRIV(owner=TOC_OWNER, data=TOC_DELIMITER.join(secret_keys).encode("utf-8")))

        # 5. เขียนไฟล์ชั่วคราว -> ตรวจ -> ค่อยแทนที่ปลายทาง (ล้มกลางทางไฟล์ปลายทางไม่เสีย)
        tags.update_to_v23()
        self.save_checked(source, destination, tags, edited, secret_keys, kept_keys)
        return secret_keys

    def read_secret(self, path: str) -> dict[str, MP3Field]:
        """Extract: the fields listed in the TOC (what the sender added or modified). {} = no TOC."""
        tags = self.load_tags(path)
        fields = self.fields_of(tags)
        return {key: fields[key] for key in self.toc_of(tags) if key in fields}

    def check_field(self, key: str, value: MP3Field) -> None:
        """Check one editor field before saving -> ValueError with a message for the user."""
        if not isinstance(value, MP3Field):
            raise ValueError(f"The value of '{key}' must be an MP3Field.")
        frame_id = value.frame_id
        if not self.is_editable(frame_id):
            raise ValueError(f"'{frame_id}' cannot be edited.")
        if key != value.key:
            raise ValueError(f"Key '{key}' does not match its field ('{value.key}').")

        for name in ("text", "desc", "lang", "mime"):
            if "\0" in getattr(value, name):
                raise ValueError(f"'{key}' cannot contain a null character.")
        for name in ("desc", "lang"):
            if "\n" in getattr(value, name) or "\r" in getattr(value, name):
                raise ValueError(f"The {name} of '{key}' cannot contain a new line.")

        if frame_id != "APIC" and not value.text:
            # mutagen ไม่เขียน frame ที่ว่าง -> field จะหายไปเงียบ ๆ
            raise ValueError(f"'{key}' cannot be empty. Enter a value or delete the field.")
        if frame_id in LANG_FRAMES and not re.fullmatch(r"[A-Za-z]{3}", value.lang):
            raise ValueError(f"The language of '{key}' must be 3 letters (e.g. 'eng', 'tha').")
        if frame_id.startswith("W"):
            # URL ตามสเปก ID3 เป็น Latin-1 และเป็นส่วนหนึ่งของ key จึงห้ามมี newline
            if not self.is_latin1(value.text) or "\n" in value.text or "\r" in value.text:
                raise ValueError(f"The URL of '{key}' must use Latin-1 characters only, on one line.")
        if frame_id == "APIC":
            if not value.mime.startswith("image/") or not self.is_latin1(value.mime):
                raise ValueError(f"The MIME type of '{key}' must be an image type (e.g. 'image/png').")
            if not value.data:
                raise ValueError(f"The picture '{key}' has no image data.")
            if value.picture_type not in APIC_TYPES:
                raise ValueError(f"The picture type of '{key}' must be 0-20.")
        # v2.3 เก็บวันที่ได้แค่ปี (TYER) + วัน/เดือน (TDAT) - เวลา/ปี-เดือน จะหาย
        if frame_id == "TDRC" and not re.fullmatch(r"\d{4}(-\d{2}-\d{2})?", value.text):
            raise ValueError("Recording Date (TDRC) must be YYYY or YYYY-MM-DD.")
        if frame_id == "TDOR" and not re.fullmatch(r"\d{4}", value.text):
            raise ValueError("Original Release Year (TDOR) must be YYYY.")

    # ================= ตัวช่วย =================

    def load_tags(self, path: str) -> ID3:
        """ID3 tag of an MP3 file (empty if it has none). Rejects files that are not MPEG audio."""
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File not found: {path}")
        try:
            MP3(path)  # ตรวจว่าเป็นเสียง MPEG จริง (ไฟล์ .mp3 บางไฟล์ข้างในเป็น MP4)
        except MutagenError:
            raise ValueError(f"'{Path(path).name}' is not an MP3 file.") from None
        try:
            return ID3(path)
        except ID3NoHeaderError:
            return ID3()

    def is_editable(self, frame_id: str) -> bool:
        """Text (T***), URL (W***), TXXX, WXXX, COMM, USLT, APIC."""
        if frame_id in DESC_FRAMES:
            return True
        if frame_id in V23_DATE_FRAMES:
            return False
        frame_class = getattr(id3, frame_id, None)
        if len(frame_id) != 4 or not isinstance(frame_class, type):
            return False
        if frame_id.startswith("T"):
            return issubclass(frame_class, TextFrame)  # TIPL/TMCL (รายชื่อคู่) ไม่ใช่ข้อความธรรมดา
        if frame_id.startswith("W"):
            return issubclass(frame_class, UrlFrame)
        return False

    def is_toc(self, frame) -> bool:
        return frame.FrameID == "PRIV" and frame.owner == TOC_OWNER

    @staticmethod
    def is_latin1(text: str) -> bool:
        try:
            text.encode("latin-1")
            return True
        except UnicodeEncodeError:
            return False

    @staticmethod
    def unknown_name(raw: bytes) -> str:
        """Frame ID (first 4 bytes) of a frame mutagen does not know."""
        return raw[:4].decode("latin-1")

    def fields_of(self, tags: ID3) -> dict[str, MP3Field]:
        fields = [self.field_of(frame) for frame in tags.values() if self.is_editable(frame.FrameID)]
        return {value.key: value for value in fields}

    def field_of(self, frame) -> MP3Field:
        """mutagen frame -> MP3Field"""
        frame_id = frame.FrameID
        if frame_id == "APIC":
            return MP3Field(frame_id, desc=frame.desc, mime=frame.mime,
                            picture_type=int(frame.type), data=frame.data)
        if frame_id == "USLT":
            return MP3Field(frame_id, text=frame.text, desc=frame.desc, lang=frame.lang)
        if frame_id == "COMM":
            return MP3Field(frame_id, text=self.joined(frame.text), desc=frame.desc, lang=frame.lang)
        if frame_id == "WXXX":
            return MP3Field(frame_id, text=frame.url, desc=frame.desc)
        if frame_id.startswith("W"):
            return MP3Field(frame_id, text=frame.url)
        if frame_id == "TXXX":
            return MP3Field(frame_id, text=self.joined(frame.text), desc=frame.desc)
        return MP3Field(frame_id, text=self.joined(frame.text))

    @staticmethod
    def joined(values) -> str:
        """Text frame หลายค่า (เช่น TPE1 = A, B) -> "A/B" แบบเดียวกับที่ v2.3 เก็บ"""
        return "/".join(str(value) for value in values)

    def frame_of(self, value: MP3Field):
        """MP3Field -> mutagen frame (ข้อความเป็น UTF-16 เพราะ v2.3 ไม่มี UTF-8)"""
        frame_id = value.frame_id
        frame_class = getattr(id3, frame_id)
        utf16 = Encoding.UTF16
        if frame_id == "APIC":
            return APIC(encoding=utf16, mime=value.mime, type=value.picture_type, desc=value.desc, data=value.data)
        if frame_id == "USLT":
            return frame_class(encoding=utf16, lang=value.lang, desc=value.desc, text=value.text)
        if frame_id == "COMM":
            return frame_class(encoding=utf16, lang=value.lang, desc=value.desc, text=[value.text])
        if frame_id == "WXXX":
            return frame_class(encoding=utf16, desc=value.desc, url=value.text)
        if frame_id.startswith("W"):
            return frame_class(url=value.text)
        if frame_id == "TXXX":
            return frame_class(encoding=utf16, desc=value.desc, text=[value.text])
        return frame_class(encoding=utf16, text=[value.text])

    def toc_of(self, tags: ID3) -> list[str]:
        for frame in tags.getall("PRIV"):
            if frame.owner == TOC_OWNER:
                return [key for key in frame.data.decode("utf-8", errors="replace").split(TOC_DELIMITER) if key]
        return []

    def other_keys(self, tags: ID3) -> list[str]:
        """Keys of the frames outside the editor (not the TOC) - must stay the same after saving."""
        return sorted(key for key, frame in tags.items()
                      if not self.is_editable(frame.FrameID) and not self.is_toc(frame))

    def unsupported_frames(self, tags: ID3) -> list[str]:
        names = [key for key, frame in tags.items() if frame.FrameID in V24_ONLY_OTHER]
        if tags.version[1] != 3:  # unknown frame ของเวอร์ชันอื่น mutagen เขียนเป็น v2.3 ไม่ได้
            names += [f"{self.unknown_name(raw)} (unknown)" for raw in tags.unknown_frames]
        return names

    def audio_digest(self, path: str) -> str:
        """Hash of the audio between the leading ID3v2 tag and a trailing ID3v1 tag."""
        try:
            start = ID3(path).size
        except ID3NoHeaderError:
            start = 0
        data = Path(path).read_bytes()
        end = len(data)
        if end - start >= 128 and data[end - 128:end - 125] == b"TAG":
            end -= 128  # ID3v1 (128 ไบต์ท้ายไฟล์) mutagen อาจเขียนใหม่ ไม่ใช่เสียง
        return hashlib.sha256(data[start:end]).hexdigest()

    def save_checked(self, source: str, destination: str, tags: ID3, edited: dict,
                     secret_keys: list[str], kept_keys: list[str]) -> None:
        """Copy the source to a temporary file next to the destination, save the tag, check it, then replace."""
        target = Path(destination)
        handle, temp_path = tempfile.mkstemp(prefix=".sieng-mp3-", suffix=".mp3", dir=target.parent)
        os.close(handle)
        try:
            shutil.copyfile(source, temp_path)
            tags.save(temp_path, v2_version=3, v23_sep="/")

            # อ่านกลับมาตรวจว่าได้ตามที่ตั้งใจจริง
            saved = ID3(temp_path)
            fields = self.fields_of(saved)
            wrong = sorted(key for key in edited.keys() | fields.keys() if edited.get(key) != fields.get(key))
            if wrong:
                raise ValueError(f"These fields could not be saved as ID3v2.3: {', '.join(wrong)}. "
                                 "The file was not replaced.")
            if (saved.version[:2] != (2, 3) or self.toc_of(saved) != secret_keys
                    or self.other_keys(saved) != kept_keys or saved.unknown_frames != tags.unknown_frames):
                raise ValueError("The saved MP3 metadata does not match; the file was not replaced.")
            if self.audio_digest(temp_path) != self.audio_digest(source):
                raise ValueError("The MP3 audio data changed; the file was not replaced.")

            os.replace(temp_path, target)
        except BaseException:
            Path(temp_path).unlink(missing_ok=True)
            raise
