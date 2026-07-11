from pathlib import Path

ICON_DIR = Path(__file__).resolve().parents[3] / "assets" / "svg"
ICON_SIZE = 16
CHIP_ICON_SIZE = 12

# ข้อมูลของแต่ละชนิด step (label, accentColor property, hex สำหรับ icon, ข้อความรอง default)
# key = ชื่อ module ตรงกับ backend (config_mode.MODULE_HANDLERS) จะได้ไม่ต้อง map ตอนสร้าง config
STEP_META = {
    "lsbpp":      {"label": "LSB++",      "accent": "blue",   "hex": "#38BDF8", "sub": "no cover yet"},
    "locomotive": {"label": "Locomotive", "accent": "purple", "hex": "#A78BFA", "sub": "no cover yet"},
    "metadata":   {"label": "Metadata",   "accent": "orange", "hex": "#F59E0F", "sub": "no target yet"},
}
CLEAR_CHIP_COLOR = "#f43f5e"

# ปุ่ม chip toolbar (ใช้ key ของ STEP_META)
TECHNIQUE_CHIPS = ["lsbpp", "locomotive", "metadata"]

# Template ตัวอย่าง — map เป็น list ของ step type (ย่อจาก engine จริง ไว้ pre-set โครง)
SCENARIOS = {
    "single-lsb": ["lsbpp"],
    "distributed-nested": ["lsbpp", "lsbpp", "metadata", "locomotive"],
    "cross-media": ["locomotive", "locomotive", "metadata", "metadata"],
    "loco-fragment": ["locomotive"],
    "meta-split": ["metadata", "metadata"],
}

# ขนาดของ step card + badge ที่ลอยทับมุม
CARD_WIDTH, CARD_HEIGHT = 155, 62
DOT_SIZE = 18          # จุดสถานะ (มุมบนซ้าย)
CLOSE_BTN_SIZE = 22        # ปุ่มปิด (มุมบนขวา)
OVERLAP = 11      # ระยะที่ badge ยื่นออกนอกการ์ด (= CLOSE // 2)
ADD_SIZE = 38     # เส้นผ่านศูนย์กลางปุ่มวงกลมเพิ่ม step
WRAP_WIDTH = CARD_WIDTH + OVERLAP * 2
WRAP_HEIGHT = CARD_HEIGHT + OVERLAP
