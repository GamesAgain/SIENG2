from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, ID3NoHeaderError
from PIL import Image

from src.core.stego.metadata_handlers.png_handler import MetadataPNGHandler
from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap, format_file_size, truncate_text_middle

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
        audio = MP3(file_path)

        # ระยะเวลาเพลง: mutagen ให้เป็นวินาที (float) แปลงเป็น "นาที:วินาที"
        total_seconds = int(audio.info.length)
        duration_text = f"{total_seconds // 60}:{total_seconds % 60:02d}"

        # bitrate: mutagen ให้หน่วยเป็น bps แปลงเป็น kbps
        bitrate_text = f"{audio.info.bitrate // 1000} kbps"

        # เวอร์ชัน ID3 tag เช่น (2, 4, 0) -> "ID3v2.4" ถ้าไฟล์ไม่มี tag เลยให้แจ้งว่า No Tag
        # จำนวน frame: นับ entry ใน ID3 tag ไม่รวม PRIV:S2M (สารบัญภายในของแอปเอง ไม่ใช่ metadata ผู้ใช้)
        try:
            tag = ID3(file_path)
            major, minor, _ = tag.version
            id3_version = f"ID3v{major}.{minor}"
            frame_count = sum(
                1 for k, frame in tag.items()
                if not (k.startswith("PRIV:") and getattr(frame, "owner", None) == "S2M")
            )
        except ID3NoHeaderError:
            id3_version = "No Tag"
            frame_count = 0

        return {
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
            "icon": str(ICON_DIR / "photo.svg"),
            "name": display_name,
            "detail": f"{size_text} · {width} × {height} · {bit_depth}-bit",
            "badges": [("PNG", "blue"), (chunk_text, "neutral")],
        }


class FileInfoBar(QFrame):
    """แถบข้อมูลไฟล์ที่เลือกไว้ (icon + ชื่อ + รายละเอียด + badge + ปุ่ม Change File)
    ใช้ร่วมกันทั้งฝั่ง embed และ extract
    """
    change_file_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("fileInfoCard")
        add_shadow_effect(self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        icon_box = QFrame()
        icon_box.setObjectName("fileInfoIconBox")
        icon_box.setFixedSize(44, 44)
        icon_box_layout = QVBoxLayout(icon_box)
        icon_box_layout.setContentsMargins(0, 0, 0, 0)
        icon_box_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.file_info_icon = QLabel()
        icon_box_layout.addWidget(self.file_info_icon)
        layout.addWidget(icon_box)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.file_info_name = QLabel()
        self.file_info_name.setObjectName("fileInfoName")

        self.file_info_detail = QLabel()
        self.file_info_detail.setObjectName("fileInfoDetail")

        text_layout.addWidget(self.file_info_name)
        text_layout.addWidget(self.file_info_detail)
        layout.addLayout(text_layout)

        layout.addStretch()

        self.badge_layout = QHBoxLayout()
        self.badge_layout.setSpacing(6)
        layout.addLayout(self.badge_layout)

        change_file_btn = QPushButton("Change File")
        change_file_btn.setObjectName("ChangeFileBtn")
        change_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        change_file_btn.clicked.connect(self.change_file_requested.emit)
        layout.addWidget(change_file_btn)
        self._change_file_btn = change_file_btn

    def add_extra_button(self, text: str) -> QPushButton:
        """เพิ่มปุ่มเสริมทางซ้ายของปุ่ม Change File (เช่น "View Frames" ในหน้า extract)
        ไม่ได้ผูกไว้ใน __init__ ตรงๆ เพราะปุ่มนี้ใช้เฉพาะบางหน้า (ไม่ใช่ทุกที่ที่ใช้ FileInfoBar)
        """
        btn = QPushButton(text)
        btn.setObjectName("SecondaryBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        index = self.layout().indexOf(self._change_file_btn)
        self.layout().insertWidget(index, btn)
        return btn

    def update_info(self, info: dict):
        self.file_info_icon.setPixmap(create_icon_pixmap(info["icon"], "#38BDF8", size=20))
        self.file_info_name.setText(info["name"])
        self.file_info_detail.setText(info["detail"])

        # เคลียร์ badge เก่าก่อนเติมชุดใหม่ (จำนวน badge ไม่เท่ากันในแต่ละไฟล์)
        while self.badge_layout.count():
            item = self.badge_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()  # deleteLater() รอรอบ event loop ถัดไป ต้อง hide() ก่อนกันค้างเห็นซ้อนกัน
                widget.deleteLater()

        for label_text, color in info["badges"]:
            badge = QLabel(label_text)
            badge.setObjectName("fileInfoBadge")
            badge.setProperty("badgeColor", color)
            self.badge_layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
