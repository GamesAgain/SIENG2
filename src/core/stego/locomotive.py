import io
import math
import os
import random
import secrets
import struct
import zipfile
from pathlib import Path, PureWindowsPath
from typing import Callable, Optional
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.core.crypto.sym_encrypt import SymmetricEncryption
from src.core.crypto.asym_encrypt import AsymmetricEncryption
from src.core.crypto.asym_encrypt import load_public_key, load_private_key, get_public_bytes

# Encrypt Mode constants SIENG2
MAGIC_NONE = b"\x00" #  None Encryption
MAGIC_SYM = b"\x01" #   Symmetric Encryption
MAGIC_ASYM = b"\x02" #   Asymmetric Encryption
ENCRYPT_MAGIC_LENGTH = 1  # bytes -- length of MAGIC_NONE/SYM/ASYM above

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"  # first 8 bytes of every PNG file
PNG_EOF_SIG = b'\x00\x00\x00\x00IEND\xaeB`\x82'  # PNG End-of-File marker

# Session block: [marker | session_id | part_index | total_parts | part_size | part data]
MARKER_LENGTH = 4  # bytes -- derived from password/key, so stacked layers with different credentials stay separate
BLOCK_HEADER_SIZE = MARKER_LENGTH + 16  # marker + 4 header fields of 4 bytes each
MAX_SINGLE_COVER_PARTS = 10  # one cover: payload is cut into up to 10 parts and shuffled

# Names the core gives to payloads it creates itself (extract callers rely on them)
TEXT_PAYLOAD_NAME = "secret_message.txt"  # raw_text payload
ZIP_PAYLOAD_NAME = "secret_files.zip"      # several payload files packed together
MAX_FILENAME_BYTES = 0xFFFF                # the payload header stores the filename length in 2 bytes

GROWTH_WARNING_RATIO = 1.0  # GUI warns when outputs grow more than 100% (warn only, never block)

secure_random = random.SystemRandom()  # OS randomness for shuffling (not predictable like random.shuffle)

# สำหรับใช้ Update Progress Bar, Stats Message
ProgressCallback = Optional[Callable[[int, str], None]]
def update_progress(callBack: ProgressCallback, percent: int, message: str):
    if callBack is not None:
        callBack(percent, message)


def validate_encryption_mode(
    password: str = None,
    public_key_path: str = None,
) -> None:
    """Embed must use either password mode or public-key mode."""
    if password is not None and public_key_path is not None:
        raise ValueError(
            "Choose either password encryption or public-key encryption, not both."
        )


def as_path_list(paths) -> list[str]:
    """Accept None, one path, or an iterable of paths (str or Path) and return a list of str."""
    if paths is None:
        return []
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]
    return [os.fspath(path) for path in paths]


def check_unique_names(paths: list[str], label: str) -> None:
    """Raise ValueError if two paths share a filename (case-insensitive, like Windows)."""
    seen = set()
    for path in paths:
        name = os.path.basename(path)
        if name.casefold() in seen:
            raise ValueError(f"{label} filenames must be unique: '{name}' is selected more than once.")
        seen.add(name.casefold())


class Locomotive:
    def __init__(self):
        self.last_session_id = None   # set by embed(); the pipeline records it to extract this layer later


    # ==================== Main Public Methods ====================

    def embed(
        self,
        cover_image_paths: list[str],
        file_paths: list[str] = None,
        raw_text: str = None,
        public_key_path: str = None,
        password: str = None,
        progress_callback: ProgressCallback = None
        ) -> list[tuple[str, bytes]]:
        """
        Embed payload (files or text) into cover PNG(s).
        Returns one (filename, bytes) per cover, in cover order.
        """
        # 0. Validate inputs (before any expensive encryption)
        validate_encryption_mode(password, public_key_path)
        cover_image_paths = as_path_list(cover_image_paths)
        file_paths = as_path_list(file_paths)
        self.validate_embed_inputs(cover_image_paths, file_paths, raw_text)

        # 1. Read payload (text -> secret_message.txt, 1 file -> as-is, N files -> secret_files.zip)
        update_progress(progress_callback, 5, "Reading payload data...")
        if raw_text is not None:
            file_data = raw_text.encode('utf-8')
            payload_package = self.pack_payload(TEXT_PAYLOAD_NAME, file_data)
        else:
            file_data, payload_name = self.pack_files(file_paths)
            payload_package = self.pack_payload(payload_name, file_data)

        # 2. Encrypt
        update_progress(progress_callback, 30, "Encrypting payload...")
        encrypted_payload = self.encrypt_data(payload_package, public_key_path, password)

        # 3. Size of each part (1 cover: equal parts / N covers: proportional to cover size)
        update_progress(progress_callback, 50, "Calculating part sizes...")
        part_sizes = self.get_part_sizes(len(encrypted_payload), cover_image_paths)

        # 4. Session blocks: [marker | session | part# | total | size | data]
        update_progress(progress_callback, 70, "Creating session blocks...")
        marker = self.get_marker(password=password, public_key_path=public_key_path)
        self.last_session_id = secrets.randbits(32)
        blocks = self.create_session_block(self.last_session_id, part_sizes, encrypted_payload, marker)

        # 5. Append blocks after the end of the cover PNG(s)
        update_progress(progress_callback, 90, "Embedding payload into cover images...")
        if len(cover_image_paths) == 1:
            output_files = self.append_onefile(cover_image_paths[0], blocks)
        else:
            output_files = self.append_multifile(cover_image_paths, blocks)

        update_progress(progress_callback, 100, "Embedding completed.")
        return output_files

    def extract(
        self,
        stego_image_paths: list[str],
        private_key_path: str = None,
        password: str = None,
        session_id: int = None,
        progress_callback: ProgressCallback = None
        ) -> tuple[str, bytes]:
        """
        Extract one session (layer) from the stego image(s).
        session_id: layer to extract; omit it to take the latest (outermost) layer.
        """
        # 1. Marker from the same credential used by embed()
        update_progress(progress_callback, 5, "Initializing extraction process...")
        marker = self.get_marker(password=password, private_key_path=private_key_path)

        # 2. Collect all sessions of this credential
        update_progress(progress_callback, 10, "Extracting payload blocks from images...")
        sessions = self.collect_sessions(as_path_list(stego_image_paths), marker)
        if not sessions:
            raise ValueError("No valid payload found. Are you sure these are stego images ?")

        # 3. Pick the layer (default: latest = last found)
        update_progress(progress_callback, 60, "Reconstructing target session...")
        if session_id is None:
            session_id = list(sessions)[-1]
        elif session_id not in sessions:
            raise ValueError(f"Session {session_id} not found in the given stego image(s) (found: {list(sessions)}).")
        session = sessions[session_id]

        # 4. Reassemble parts in part# order (undo the shuffle)
        update_progress(progress_callback, 75, "Reconstructing encrypted payload...")
        if len(session['data']) != session['total_parts']:
            raise ValueError(f"Missing parts for the payload! Found {len(session['data'])} of {session['total_parts']}.")
        encrypted_payload = b"".join(session['data'][i] for i in range(session['total_parts']))

        # 5. Decrypt and unpack
        update_progress(progress_callback, 85, "Decrypting payload data...")
        payload_package = self.decrypt_data(encrypted_payload, private_key_path, password)

        update_progress(progress_callback, 95, "Unpacking original files...")
        filename, file_data = self.unpack_payload(payload_package)

        update_progress(progress_callback, 100, "Extraction completed.")
        return filename, file_data

    def list_sessions(
        self,
        stego_image_paths: list[str],
        private_key_path: str = None,
        password: str = None,
        ) -> list[dict]:
        """
        Sessions (layers) found for this credential, oldest first
        """
        marker = self.get_marker(password=password, private_key_path=private_key_path)
        sessions = self.collect_sessions(as_path_list(stego_image_paths), marker)
        return [
            {"session_id": sid, "found_parts": len(session['data']), "total_parts": session['total_parts']}
            for sid, session in sessions.items()
        ]

    # ==================== Validation ====================

    def validate_embed_inputs(self, cover_image_paths: list[str], file_paths: list[str], raw_text: str | None) -> None:
        """Reject bad input before any expensive work (encryption) starts."""
        # Covers
        if not cover_image_paths:
            raise ValueError("At least one cover image is required.")

        for cover in cover_image_paths:
            name = os.path.basename(cover)
            try:
                with open(cover, 'rb') as f:
                    header = f.read(len(PNG_SIGNATURE))
            except OSError:
                raise ValueError(f"Cover file is unavailable: {name}")
            if header != PNG_SIGNATURE:
                raise ValueError(f"Cover is not a PNG image: {name}")

        # Output names are "<stem>_loco<ext>", so cover names must not collide.
        check_unique_names(cover_image_paths, "Cover")

        # Payload: exactly one of text / files
        if raw_text is not None and file_paths:
            raise ValueError("Provide either payload files or text, not both.")

        if raw_text is not None:
            if not raw_text:
                raise ValueError("Payload text is empty.")
            return

        if not file_paths:
            raise ValueError("No payload provided (neither file nor text).")

        for path in file_paths:
            if not os.path.isfile(path):
                raise ValueError(f"Payload file is unavailable: {os.path.basename(path)}")

        # Several files are zipped by name, so duplicates would be ambiguous.
        check_unique_names(file_paths, "Payload")

    # ==================== Session blocks ====================

    def get_marker(
        self,
        password: str = None,
        public_key_path: str = None,
        private_key_path: str = None,
    ) -> bytes:
        """Derive the fragment marker from the selected credential."""
        validate_encryption_mode(password, public_key_path)
        if public_key_path is not None and private_key_path is not None:
            raise ValueError("Choose either a public key or a private key, not both.")

        if public_key_path is not None:
            public_key = load_public_key(public_key_path)
            seed = get_public_bytes(public_key)
        elif private_key_path is not None:
            private_key = load_private_key(private_key_path, password)
            seed = get_public_bytes(private_key.public_key())
        elif password is not None:
            seed = password.encode("utf-8")
        else:
            seed = b"SIENG2_LOCOMOTIVE_DEFAULT"

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=MARKER_LENGTH,
            salt=None,
            info=b"SIENG2_LOCOMOTIVE_MARKER",
        )
        return hkdf.derive(seed)

    def get_part_sizes(self, payload_length: int, cover_image_paths: list[str]) -> list[int]:
        """
        Size of every block.
        1 cover : up to 10 equal parts (shuffled later in append_onefile)
        N covers: one part per cover, proportional to cover file size -> every output grows by the same ratio
        """
        # 1. One cover -> equal parts
        if len(cover_image_paths) == 1:
            num_parts = max(1, min(payload_length, MAX_SINGLE_COVER_PARTS))
            chunk_size = math.ceil(payload_length / num_parts)
            return [max(0, min(chunk_size, payload_length - i * chunk_size)) for i in range(num_parts)]

        # 2. Several covers -> share by cover size (a small cover no longer gets the same bytes as a big one)
        cover_sizes = [os.path.getsize(path) for path in cover_image_paths]
        total_size = sum(cover_sizes)
        part_sizes = [payload_length * size // total_size for size in cover_sizes]
        part_sizes[-1] += payload_length - sum(part_sizes)  # rounding remainder goes to the last cover
        return part_sizes

    def create_session_block(self, session_id: int, part_sizes: list[int], payload: bytes, marker: bytes) -> list[bytes]:
        """
        Cut the encrypted payload into numbered blocks of one session
        """
        blocks = []
        start = 0
        for part_idx, part_size in enumerate(part_sizes):
            part_data = payload[start:start + part_size]
            start += part_size

            header = struct.pack('>IIII', session_id, part_idx, len(part_sizes), part_size) # 16 bytes
            blocks.append(marker + header + part_data)
        return blocks

    def collect_sessions(self, stego_image_paths: list[str], marker: bytes) -> dict[int, dict]:
        """
        Read every block after IEND and group it by session id.
        Dict order = order found = oldest layer first (newer layers are appended later).
        """
        sessions = {}
        for path in stego_image_paths:
            # 1. Data after the PNG end
            img_data = self.read_bytes(path)
            eof_idx = img_data.find(PNG_EOF_SIG)
            if eof_idx == -1:
                raise ValueError(
                    f"'{path}' does not look like a PNG with Locomotive data appended "
                    f"(no PNG end-of-file marker found). Please verify the file."
                )
            tail = img_data[eof_idx + len(PNG_EOF_SIG):]

            # 2. Walk the blocks of this credential's marker
            cursor = 0
            while True:
                sig_idx = tail.find(marker, cursor)
                if sig_idx == -1: break                     # no more blocks

                header_end = sig_idx + BLOCK_HEADER_SIZE
                if header_end > len(tail): break            # header cut off

                session_id, part_idx, total_parts, part_size = struct.unpack('>IIII', tail[sig_idx + MARKER_LENGTH:header_end])
                if header_end + part_size > len(tail): break  # data cut off

                session = sessions.setdefault(session_id, {'total_parts': total_parts, 'data': {}})
                session['data'][part_idx] = tail[header_end:header_end + part_size]
                cursor = header_end + part_size
        return sessions

    def append_onefile(self, cover_path: str, blocks: list[bytes]) -> list[tuple[str, bytes]]:
        """
        Shuffle all blocks and append them after the end of one cover PNG
        """
        # สับลำดับ: ตัดก้อนข้อมูลหลัง IEND ไปถอดตรง ๆ ไม่ได้ ต้องประกอบตาม part# ก่อน
        secure_random.shuffle(blocks)
        final_payload = b"".join(blocks)
        with open(cover_path, 'rb') as f:
            cover_img = f.read()
        stego_img =  cover_img + final_payload

        filename, ext = os.path.splitext(os.path.basename(cover_path))

        return [(f'{filename}_loco{ext}', stego_img)]

    def append_multifile(self, cover_image_paths: list[str], blocks: list[bytes]) -> list[tuple[str, bytes]]:
        """
        Append block i after the end of cover PNG i (one block per cover)
        """

        output_files = []
        for i, path in enumerate(cover_image_paths):
            with open(path, 'rb') as f:
                cover_img = f.read()
            stego_img =  cover_img + blocks[i]

            filename, ext = os.path.splitext(os.path.basename(path))
            output_files.append((f'{filename}_loco{ext}', stego_img))

        return output_files

    # ==================== Payload packing ====================

    def pack_payload(self, file_path: str, data: bytes) -> bytes:
        """
        Pack the payload with filename and data
        """
        file_name = os.path.basename(file_path).encode('utf-8')
        if len(file_name) > MAX_FILENAME_BYTES:
            raise ValueError(f"Payload filename is too long (max {MAX_FILENAME_BYTES} bytes).")
        filename_length = len(file_name).to_bytes(2, 'big') # 2 bytes for filename length
        payload_package = filename_length + file_name + data

        return payload_package

    def unpack_payload(self, payload: bytes) -> tuple[str, bytes]:
        """
        Unpack the payload to get filename and data.
        The filename comes from the (untrusted) payload, so only its last path component is returned.
        """
        filename_length = int.from_bytes(payload[:2], 'big')
        if len(payload) < 2 + filename_length:
            raise ValueError("Payload is truncated or corrupted. Please verify your image and password/key.")
        try:
            filename_ext = payload[2 : 2 + filename_length].decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError("Failed to decode payload filename. Please verify your image and password/key.")
        file_data = payload[2 + filename_length :]

        # PureWindowsPath treats both "\" and "/" (and drive letters) as separators on any OS.
        filename_ext = PureWindowsPath(filename_ext).name
        if filename_ext in ("", ".", ".."):
            raise ValueError("Payload filename is invalid. Please verify your image and password/key.")

        return filename_ext, file_data

    # ==================== Crypto ====================

    def encrypt_data(self, data: bytes, public_key_path: str = None, password: str = None):
        """
        Encrypt the data using either symmetric or asymmetric encryption
        """
        validate_encryption_mode(password, public_key_path)

        if password is not None:
            magic = MAGIC_SYM  # 0x01: Symmetric encryption
            encryptor = SymmetricEncryption()
            data_bytes = encryptor.encrypt(data, password)
        elif public_key_path is not None:
            magic = MAGIC_ASYM  # 0x02: Asymmetric encryption
            encryptor = AsymmetricEncryption()
            public_key = load_public_key(public_key_path)
            data_bytes = encryptor.encrypt(data, public_key)
        else:
            magic = MAGIC_NONE  # 0x00: No encryption
            data_bytes = data

        encrypted_data = magic + data_bytes
        return encrypted_data

    def decrypt_data(self, data: bytes, private_key_path: str = None, password: str = None):
        """
        Decrypt the data using either symmetric or asymmetric decryption
        """
        magic = data[:ENCRYPT_MAGIC_LENGTH]
        header_length = len(magic)

        extracted_data = data[header_length:]
        if magic == MAGIC_SYM:
            if password is None:
                raise ValueError("Password required for symmetric encryption")

            decryptor = SymmetricEncryption()
            data_bytes = decryptor.decrypt(extracted_data, password)
            return data_bytes
        elif magic == MAGIC_ASYM:
            if not private_key_path:
                raise ValueError("Private key required for asymmetric decryption")

            # password (optional) unlocks a password-protected private key
            decryptor = AsymmetricEncryption()
            private_key = load_private_key(private_key_path, password)
            data = decryptor.decrypt(extracted_data, private_key)
            return data
        elif magic == MAGIC_NONE:  # SEN: No encryption
            return extracted_data

        else:
            raise ValueError("Extraction failed: Invalid SIENG2 signature. Please verify your image and password.")

    # ==================== Utility Methods ====================
    def read_bytes(self, path: str) -> bytes:
        with open(path, 'rb') as f:
            return f.read()

    def pack_files(self, file_paths: list[str]) -> tuple[bytes, str]:
        """
        Return (data, filename): one file as-is, or several files zipped as ZIP_PAYLOAD_NAME
        """
        if len(file_paths) == 1:
            path = file_paths[0]
            return self.read_bytes(path), os.path.basename(path)

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(
            zip_buffer,
            'w',
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6
        ) as zipf:

            for path in file_paths:
                zipf.write(
                    path,
                    arcname=Path(path).name
                )
        return zip_buffer.getvalue(), ZIP_PAYLOAD_NAME

# --- External function ---
def estimate_growth_ratio(cover_image_paths, payload_size: int) -> float:
    """
    ≈ how much every output file grows (payload / total cover size).
    Same for all covers because the payload is split by cover size.
    Encryption and block headers (< 1 KB) are ignored -- it is a hint for the GUI, not an exact number.
    """
    total_size = sum(os.path.getsize(path) for path in as_path_list(cover_image_paths))
    return payload_size / total_size if total_size else 0.0
