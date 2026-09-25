from PyQt6.QtGui import QPen, QPixmap, QPainter, QIcon, QColor
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QLineEdit, QWidget

# ---------------------------------------------------------
# ฟังก์ชั่นย่อ Text
# ---------------------------------------------------------
def truncate_text_middle(text: str, max_length: int = 40) -> str:
    """
    ตัวอย่าง:
    "my_super_long_secret_project_document_final_v2.png" (max_length=40)
    จะกลายเป็น: "my_super_long_secre...ment_final_v2.png"
    """
    if len(text) <= max_length:
        return text
        
    # หักพื้นที่ 3 ตัวอักษรไว้สำหรับ "..."
    chars_to_keep = max_length - 3
    
    # แบ่งตัวอักษรไว้ครึ่งหน้า และครึ่งหลัง
    # (ถ้าหารไม่ลงตัว ให้ครึ่งหน้ายาวกว่า 1 ตัวอักษร)
    left_len = chars_to_keep // 2 + (chars_to_keep % 2) 
    right_len = chars_to_keep // 2
    
    return f"{text[:left_len]}...{text[-right_len:]}"

# ---------------------------------------------------------
# ฟังก์ชัน Format File Size [B | KB | MB | GB | TB]
# ---------------------------------------------------------
def format_file_size(file_size_bytes: int) -> str:
    if file_size_bytes < 1024:
        return f"{file_size_bytes} B"
    elif file_size_bytes < 1024 ** 2: # หลักร้อยพันไบต์ -> KB
        return f"{file_size_bytes / 1024:.2f} KB"
    elif file_size_bytes < 1024 ** 3: # หลักล้านไบต์ -> MB
        return f"{file_size_bytes / (1024 ** 2):.2f} MB"
    elif file_size_bytes < 1024 ** 4: # หลักพันล้านไบต์ -> GB
        return f"{file_size_bytes / (1024 ** 3):.2f} GB"
    else:                             # ทะลุไปหลักล้านล้านไบต์ -> TB
        return f"{file_size_bytes / (1024 ** 4):.2f} TB"
    
# ---------------------------------------------------------
# ฟังก์ชั่นสร้าง Icon state
# ---------------------------------------------------------
def create_icon_state(icon_path: str, icon_size: int = 16, color_normal: str = "#94A3B8", color_checked: str = "#38BDF8") -> QIcon:
    icon = QIcon()
    
    # --- Create pixmaps for different states ---
    # Normal State
    pix_normal = create_icon_pixmap(icon_path, color_normal, size=icon_size)
    icon.addPixmap(pix_normal, QIcon.Mode.Normal, QIcon.State.Off)
    
    # Checked State
    pix_checked = create_icon_pixmap(icon_path, color_checked, size=icon_size)
    icon.addPixmap(pix_checked, QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(pix_checked, QIcon.Mode.Active, QIcon.State.On)
    
    return icon

# ---------------------------------------------------------
# ฟังก์ชั่นใส่เงาสุดเท่ Widgets
# ---------------------------------------------------------
def add_shadow_effect(widget: QWidget, offset_x: int = 0, offset_y: int = 1, blur_radius: int = 8, color: QColor = QColor(0, 0, 0, 89)):
    """
    Args:
        widget: QWidget ที่ต้องการใส่เงา
        offset_x: ระยะห่างของเงาในแนวแกน X (default: 0)
        offset_y: ระยะห่างของเงาในแนวแกน Y (default: 1)
        blur_radius: ขนาดของเงา (default: 8)
        color: สีของเงา (default: QColor(0, 0, 0, 89)) # 35% opacity
    """
    shadow = QGraphicsDropShadowEffect()
    
    # ตั้งค่าเงา
    shadow.setXOffset(offset_x)
    shadow.setYOffset(offset_y)
    shadow.setBlurRadius(blur_radius)
    shadow.setColor(color)
    widget.setGraphicsEffect(shadow)

# ---------------------------------------------------------
# ฟังก์ชันสำหรับย้อมสี Icon (Tinting)
# ---------------------------------------------------------
def create_icon_pixmap(icon_path: str, color_hex: str = "#94a3b8", size: int = 22) -> QPixmap: 
    """
    Args:
        icon_path: ตำแหน่งไฟล์ icon
        color_hex: สีที่ต้องการย้อม (hex format เช่น "#FF0000")
        size: ขนาดของ icon (default: 22)
    """
    path = str(icon_path)
    
    # สร้าง pixmap โปร่งใสขนาดที่กำหนด
    icon_pixmap = QPixmap(size, size)
    icon_pixmap.fill(Qt.GlobalColor.transparent)
    
    # สร้าง painter เพื่อวาด icon
    painter = QPainter(icon_pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing) # ป้องกันรอยหยัก
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform) # ป้องกันการเบลอจากการย่อ/ขยาย
    
    # วาด icon ลงใน pixmap
    icon = QIcon(path)
    icon.paint(painter, 0, 0, size, size, Qt.AlignmentFlag.AlignCenter)
    
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn) # วาดในพื้นที่ที่มีสีเดิมวาดอยู่แล้ว
    painter.fillRect(icon_pixmap.rect(), QColor(color_hex))
    
    painter.end()
    
    return icon_pixmap



# ---------------------------------------------------------
# ฟังก์ชันสำหรับซ่อนและแสดง Password
# ---------------------------------------------------------
def add_password_visibility_toggle(line_edit: QLineEdit, *linked_line_edits: QLineEdit,) -> None:
    """Add synchronized show/hide actions to one or more password fields."""

    def create_eye_icon(is_open: bool) -> QIcon:
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#94A3B8")
        painter.setPen(QPen(color, 2))

        painter.drawEllipse(2, 6, 20, 12)
        if is_open:
            painter.setBrush(color)
            painter.drawEllipse(10, 10, 4, 4)
        else:
            painter.drawLine(4, 4, 20, 20)

        painter.end()
        return QIcon(pixmap)

    visible_icon = create_eye_icon(True)
    hidden_icon = create_eye_icon(False)
    fields = (line_edit, *linked_line_edits)
    actions = []

    def set_visibility(visible: bool) -> None:
        echo_mode = (
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        )
        for field, action in zip(fields, actions):
            field.setEchoMode(echo_mode)
            action.setIcon(visible_icon if visible else hidden_icon)
            action.setToolTip("Hide password" if visible else "Show password")

    for field in fields:
        action = field.addAction(
            hidden_icon,
            QLineEdit.ActionPosition.TrailingPosition,
        )
        action.setObjectName("passwordVisibilityAction")
        action.setToolTip("Show password")
        actions.append(action)

        def toggle_visibility(
            checked: bool = False,
            source: QLineEdit = field,
        ) -> None:
            del checked
            set_visibility(source.echoMode() == QLineEdit.EchoMode.Password)

        action.triggered.connect(toggle_visibility)
