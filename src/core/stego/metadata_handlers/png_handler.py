"""
Metadata-PNG: อ่าน/แก้ text chunk ของ PNG แบบ Metadata editor

ขั้นตอนการใช้งาน
1. read_text(path)                 -> text ทั้งหมดในไฟล์ (tEXt / zTXt / iTXt) เอาไปแสดงใน editor
2. ผู้ใช้ เพิ่ม / แก้ / ลบ field
3. write_text(source, dest, edited) -> บันทึก text ทั้งหมดเป็น iTXt
   field ที่ผู้ใช้ "เพิ่ม" หรือ "แก้" = secret -> จดชื่อ key ไว้ใน TOC chunk 'stWo'
   (field ที่ลบ หรือค่าเท่าเดิม ไม่นับ)
4. ฝั่งถอด read_secret(path)        -> คืนเฉพาะ field ที่อยู่ใน TOC (สิ่งที่ผู้ส่งเพิ่ม/แก้)

ไม่แตะพิกเซล (IDAT) และเก็บไบต์ที่อยู่หลัง IEND ไว้ (Locomotive ต่อข้อมูลไว้ตรงนั้น)
จึงใช้ซ้อนกับ LSB++ / Locomotive ได้ทุกลำดับ
"""
import os
import struct
import tempfile
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TEXT_CHUNKS = {b"tEXt", b"zTXt", b"iTXt"}

# TOC chunk 'stWo' (SIENG Two) ตัวพิมพ์เล็ก-ใหญ่มีความหมายตามสเปก PNG:
#   s เล็ก = ancillary (โปรแกรมที่ไม่รู้จักข้ามได้ ภาพไม่พัง)
#   t เล็ก = private (ไม่ชนกับ chunk มาตรฐาน)
#   W ใหญ่ = reserved bit (สเปกบังคับให้ตัวที่ 3 เป็นตัวใหญ่)
#   o เล็ก = safe-to-copy (โปรแกรมแก้ภาพคัดลอกต่อได้)
TOC_CHUNK = b"stWo"
TOC_DELIMITER = "\n"  # keyword ของ PNG มี newline ไม่ได้ จึงใช้คั่นได้ปลอดภัย

MAX_KEYWORD_LENGTH = 79  # bytes ตามสเปก PNG

# keyword มาตรฐานตามสเปก PNG -> (ชื่อ, คำอธิบาย) ให้ editor ใช้แสดง
PNG_TEXT_KEYWORDS = {
    "Title":         ("Title", "Short title or caption for the image"),
    "Author":        ("Author", "Name of the image's creator"),
    "Description":   ("Description", "Longer description of the image"),
    "Copyright":     ("Copyright", "Copyright notice"),
    "Creation Time": ("Creation Time", "Time of original image creation"),
    "Software":      ("Software", "Software used to create the image"),
    "Disclaimer":    ("Disclaimer", "Legal disclaimer"),
    "Warning":       ("Warning", "Warning about the nature of the content"),
    "Source":        ("Source", "Device used to create the image"),
    "Comment":       ("Comment", "Miscellaneous comment"),
}
# keyword ที่ editor แสดงเสมอ (แม้ไฟล์ไม่มีค่า) - ตัวที่ File Explorer แสดงบ่อย
STANDARD_KEYWORDS = ["Title", "Author", "Description", "Copyright", "Creation Time", "Software"]


class MetadataPNGHandler:
    """Read and edit the text metadata of a PNG; the added/modified fields are the secret."""

    # ================= Public API =================

    def read_text(self, path: str) -> dict[str, str]:
        """All text chunks of the PNG as {keyword: value}, in file order."""
        chunks, _ = self.read_chunks(path)
        return self.text_of(chunks)

    @staticmethod
    def changed_keys(original: dict[str, str], edited: dict[str, str]) -> list[str]:
        """Keys the user added or modified. A deleted key, or a value that is still the same, does not count."""
        return [key for key, value in edited.items() if original.get(key) != value]

    def write_text(self, source: str, destination: str, edited: dict[str, str]) -> list[str]:
        """
        Save `edited` as the only text of the PNG (all iTXt) + the TOC of the changed keys.
        Returns the changed (secret) keys. The source file is never modified.
        """
        # 1. ตรวจข้อมูลก่อน จะได้ไม่เขียนไฟล์เสียครึ่งทาง
        for key, value in edited.items():
            self.check_keyword(key)
            if not isinstance(value, str):
                raise ValueError(f"The value of '{key}' must be text.")

        # 2. อ่านไฟล์ต้นฉบับ แล้วหาว่าผู้ใช้เพิ่ม/แก้ field ไหน
        chunks, trailing = self.read_chunks(source)
        secret_keys = self.changed_keys(self.text_of(chunks), edited)

        # 3. ทิ้ง text และ TOC เดิมทั้งหมด แล้วสร้างใหม่จาก edited (field ที่ผู้ใช้ลบจึงหายไปจริง)
        kept = [(kind, data) for kind, data in chunks if kind not in TEXT_CHUNKS and kind != TOC_CHUNK]
        new_chunks = [self.make_itxt(key, value) for key, value in edited.items()]
        if secret_keys:
            new_chunks.append((TOC_CHUNK, TOC_DELIMITER.join(secret_keys).encode("utf-8")))

        # 4. วางต่อจาก IHDR (chunk แรกเสมอ) ก่อน IDAT - โปรแกรมทั่วไปอ่าน text ส่วนหัวได้ทันที
        chunks = kept[:1] + new_chunks + kept[1:]
        data = self.build_png(chunks) + trailing  # ไบต์หลัง IEND (ของ Locomotive) ต่อกลับเหมือนเดิม

        # 5. เขียนไฟล์ชั่วคราว -> ตรวจ -> ค่อยแทนที่ปลายทาง (ล้มกลางทางไฟล์ปลายทางไม่เสีย)
        self.save_checked(data, destination, edited, secret_keys, trailing)
        return secret_keys

    def read_secret(self, path: str) -> dict[str, str]:
        """Extract: the fields listed in the TOC (what the sender added or modified). {} = no TOC."""
        chunks, _ = self.read_chunks(path)
        text = self.text_of(chunks)
        return {key: text[key] for key in self.toc_of(chunks) if key in text}

    def check_keyword(self, key: str) -> None:
        """PNG keyword rules: 1-79 bytes of printable Latin-1, no leading/trailing/double spaces."""
        if not isinstance(key, str) or not key:
            raise ValueError("A keyword cannot be empty.")
        try:
            raw = key.encode("latin-1")
        except UnicodeEncodeError:
            raise ValueError(f"Keyword '{key}' must use Latin-1 characters only (A-Z, 0-9, ...).") from None
        if len(raw) > MAX_KEYWORD_LENGTH:
            raise ValueError(f"Keyword '{key}' is longer than {MAX_KEYWORD_LENGTH} characters.")
        if any(not (32 <= byte <= 126 or 161 <= byte <= 255) for byte in raw):
            raise ValueError(f"Keyword '{key}' contains a character that is not allowed.")
        if key != key.strip() or "  " in key:
            raise ValueError(f"Keyword '{key}' cannot start/end with a space or contain double spaces.")

    # ================= Read: chunks -> text =================

    def read_chunks(self, path: str) -> tuple[list[tuple[bytes, bytes]], bytes]:
        """
        Split a PNG into [(chunk_type, chunk_data), ...] up to IEND, and the bytes after IEND.
        แต่ละ chunk = length(4) + type(4) + data + crc(4)
        """
        raw = Path(path).read_bytes()
        if raw[:8] != PNG_SIGNATURE:
            raise ValueError("The file is not a PNG image.")

        chunks = []
        pos = 8  # ข้าม signature
        while pos + 8 <= len(raw):
            length = struct.unpack(">I", raw[pos:pos + 4])[0]
            kind = raw[pos + 4:pos + 8]
            end = pos + 12 + length
            if end > len(raw):
                raise ValueError("The PNG file is truncated or damaged.")
            chunks.append((kind, raw[pos + 8:pos + 8 + length]))
            pos = end
            if kind == b"IEND":
                return chunks, raw[pos:]  # ที่เหลือหลัง IEND = trailing (เช่น ข้อมูลของ Locomotive)

        raise ValueError("The PNG file has no IEND chunk.")

    def text_of(self, chunks: list[tuple[bytes, bytes]]) -> dict[str, str]:
        """{keyword: value} of the text chunks. A keyword that appears twice keeps the last value."""
        text = {}
        for kind, data in chunks:
            if kind in TEXT_CHUNKS:
                key, value = self.decode_text_chunk(kind, data)
                text.pop(key, None)  # ซ้ำ -> ใช้ตัวล่าสุด
                text[key] = value
        return text

    def toc_of(self, chunks: list[tuple[bytes, bytes]]) -> list[str]:
        """The keys listed in the TOC chunk ([] when there is none)."""
        for kind, data in chunks:
            if kind == TOC_CHUNK:
                return [key for key in data.decode("utf-8").split(TOC_DELIMITER) if key]
        return []

    def decode_text_chunk(self, kind: bytes, data: bytes) -> tuple[str, str]:
        """
        tEXt: keyword \\0 text                                  (Latin-1)
        zTXt: keyword \\0 method(1) compressed-text             (Latin-1)
        iTXt: keyword \\0 flag(1) method(1) lang \\0 translated \\0 text   (UTF-8, flag 1 = compressed)
        """
        try:
            keyword, rest = data.split(b"\0", 1)
            key = keyword.decode("latin-1")
            if kind == b"tEXt":
                return key, rest.decode("latin-1")
            if kind == b"zTXt":
                return key, zlib.decompress(rest[1:]).decode("latin-1")

            # iTXt
            compressed = rest[0] == 1
            _language, _translated, text = rest[2:].split(b"\0", 2)
            if compressed:
                text = zlib.decompress(text)
            return key, text.decode("utf-8")
        except (ValueError, IndexError, zlib.error, UnicodeDecodeError):
            raise ValueError(f"Cannot read a {kind.decode()} chunk of this PNG (it is damaged).") from None

    # ================= Write: text -> chunks -> file =================

    def make_itxt(self, key: str, value: str) -> tuple[bytes, bytes]:
        """One iTXt chunk. Not compressed, unless compressing makes it smaller (long text)."""
        raw = value.encode("utf-8")
        compressed = zlib.compress(raw)
        if len(compressed) < len(raw):
            flag, text = 1, compressed
        else:
            flag, text = 0, raw
        # keyword \0 flag method(0 = zlib) lang(ว่าง) \0 translated keyword(ว่าง) \0 text
        data = key.encode("latin-1") + b"\0" + bytes([flag, 0]) + b"\0" + b"\0" + text
        return b"iTXt", data

    def build_png(self, chunks: list[tuple[bytes, bytes]]) -> bytes:
        """Signature + every chunk with its length and a fresh CRC."""
        parts = [PNG_SIGNATURE]
        for kind, data in chunks:
            crc = zlib.crc32(kind + data) & 0xFFFFFFFF
            parts.append(struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc))
        return b"".join(parts)

    def save_checked(self, data: bytes, destination: str, edited: dict, secret_keys: list[str], trailing: bytes) -> None:
        """Write to a temporary file next to the destination, check it, then replace the destination."""
        target = Path(destination)
        handle, temp_path = tempfile.mkstemp(prefix=".sieng-png-", suffix=".png", dir=target.parent)
        try:
            with os.fdopen(handle, "wb") as file:
                file.write(data)

            # อ่านกลับมาตรวจว่าได้ตามที่ตั้งใจจริง
            chunks, saved_trailing = self.read_chunks(temp_path)
            if self.text_of(chunks) != edited or self.toc_of(chunks) != secret_keys or saved_trailing != trailing:
                raise ValueError("The saved PNG metadata does not match; the file was not replaced.")

            os.replace(temp_path, target)
        except BaseException:
            Path(temp_path).unlink(missing_ok=True)
            raise
