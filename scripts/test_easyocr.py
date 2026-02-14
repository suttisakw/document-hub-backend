#!/usr/bin/env python3
"""
ทดสอบ EasyOCR ด้วยภาพจากไฟล์ (ไม่ต้องใช้ DB/Redis).

การใช้งาน:
  poetry run python scripts/test_easyocr.py [path/to/image.png]

  - ถ้าไม่ระบุ path จะสร้างภาพทดสอบขนาดเล็กที่มีข้อความ "Test OCR 123" แล้วรัน OCR
  - ครั้งแรก EasyOCR จะดาวน์โหลด model (en, th) อาจใช้เวลาสักครู่
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

# เพิ่ม backend เป็น path เพื่อ import app
backend = Path(__file__).resolve().parent.parent
if str(backend) not in sys.path:
    sys.path.insert(0, str(backend))


def make_sample_image() -> bytes:
    """สร้างภาพ PNG ขนาดเล็กที่มีข้อความสำหรับทดสอบ"""
    from PIL import Image, ImageDraw, ImageFont

    width, height = 320, 80
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 24), "Test OCR 123", fill=(0, 0, 0), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def main() -> int:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if not path.exists():
            print(f"ไม่พบไฟล์: {path}", file=sys.stderr)
            return 1
        image_bytes = path.read_bytes()
        label = str(path)
    else:
        print("ไม่ระบุ path ภาพ — ใช้ภาพทดสอบที่มีข้อความ 'Test OCR 123'\n")
        image_bytes = make_sample_image()
        label = "(sample image)"

    print(f"กำลังรัน EasyOCR บนภาพ: {label}")
    print("(ครั้งแรกอาจดาวน์โหลด model นาน 1–2 นาที)\n")

    from app.services.ocr_easyocr import run_easyocr_on_image_bytes

    fields = run_easyocr_on_image_bytes(image_bytes)
    print(f"พบข้อความ {len(fields)} บล็อก:")
    for i, f in enumerate(fields):
        conf = f"{f.confidence:.2f}" if f.confidence is not None else "—"
        print(f"  [{i}] {f.field_name}: {f.field_value!r} (confidence: {conf})")
    if not fields:
        print("  (ไม่พบข้อความ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
