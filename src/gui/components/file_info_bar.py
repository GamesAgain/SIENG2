from pathlib import Path

from PyQt6.QtCore import QFileInfo, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFileIconProvider, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QSizePolicy

from src.gui.components.gui_utils import add_shadow_effect, create_icon_pixmap


class FileInfoBar(QFrame):
    """แถบข้อมูลไฟล์ที่เลือกไว้ (icon + ชื่อ + รายละเอียด + badge + ปุ่ม Change File)"""
    change_file_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("fileInfoCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        change_file_btn.setObjectName("SecondaryBtn")
        change_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        change_file_btn.clicked.connect(self.change_file_requested.emit)
        layout.addWidget(change_file_btn)
        self._change_file_btn = change_file_btn

    def add_extra_button(self, text: str) -> QPushButton:
        """เพิ่มปุ่มเสริมทางซ้ายของปุ่ม Change File (เช่น "View Frames" หรือ "Run Analysis")
        ไม่ได้ผูกไว้ใน __init__ ตรงๆ เพื่อให้หน้านั้นๆ นำไปใช้แบบ dynamic
        """
        btn = QPushButton(text)
        btn.setObjectName("SecondaryBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        index = self.layout().indexOf(self._change_file_btn)
        self.layout().insertWidget(index, btn)
        return btn

    def update_info(self, info: dict):
        file_path = info.get("path")
        if file_path:
            file_path_obj = Path(file_path)
            file_ext = file_path_obj.suffix.lower()
            image_exts = ['.png', '.jpg', '.jpeg', '.bmp', '.gif']

            if file_ext in image_exts:
                pixmap = QPixmap(file_path)
                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                    self.file_info_icon.setPixmap(scaled_pixmap)
                else:
                    self.file_info_icon.setPixmap(create_icon_pixmap(info["icon"], "#38BDF8", size=20))
            else:
                provider = QFileIconProvider()
                icon = provider.icon(QFileInfo(file_path))
                self.file_info_icon.setPixmap(icon.pixmap(32, 32))
        else:
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
