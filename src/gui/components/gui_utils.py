from PyQt6.QtGui import QPixmap, QPainter, QIcon, QColor
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QWidget


def format_file_size(file_size_bytes: int) -> str:
    if file_size_bytes < 1024:
        return f"{file_size_bytes} B"
    elif file_size_bytes < 1024 * 1024:
        return f"{file_size_bytes / 1024:.2f} KB"
    else:
        return f"{file_size_bytes / (1024 * 1024):.2f} MB"
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
    
    