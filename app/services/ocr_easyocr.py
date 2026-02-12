from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class EasyOcrField:
    field_name: str
    field_value: str
    confidence: float | None
    bbox_x: float | None
    bbox_y: float | None
    bbox_width: float | None
    bbox_height: float | None


_reader: Any | None = None


def get_reader():
    global _reader
    if _reader is None:
        import easyocr

        # English + Thai by default (common for this project).
        _reader = easyocr.Reader(["en", "th"], gpu=False)
    return _reader


def run_easyocr_on_image_bytes(image_bytes: bytes) -> list[EasyOcrField]:
    reader = get_reader()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img_np = np.array(img)
    results = reader.readtext(img_np)

    fields: list[EasyOcrField] = []
    for i, (bbox, text, conf) in enumerate(results):
        # bbox is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        fields.append(
            EasyOcrField(
                field_name=f"text_{i}",
                field_value=text,
                confidence=float(conf) if conf is not None else None,
                bbox_x=float(x1),
                bbox_y=float(y1),
                bbox_width=float(x2 - x1),
                bbox_height=float(y2 - y1),
            )
        )

    return fields
