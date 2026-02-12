from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _get_ocr_th():
    from paddleocr import PaddleOCR

    return PaddleOCR(use_angle_cls=True, lang="th", use_gpu=False)


@lru_cache(maxsize=1)
def _get_ocr_en():
    from paddleocr import PaddleOCR

    return PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False)


def _extract_lines(raw_result: list) -> list[str]:
    lines: list[str] = []
    for page in raw_result or []:
        for entry in page or []:
            if not entry or len(entry) < 2:
                continue
            text_data = entry[1]
            if not text_data or len(text_data) < 1:
                continue
            text = str(text_data[0]).strip()
            if text:
                lines.append(text)
    return lines


def extract_text(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    th_result = _get_ocr_th().ocr(str(path), cls=True)
    en_result = _get_ocr_en().ocr(str(path), cls=True)

    merged_lines: list[str] = []
    seen: set[str] = set()
    for line in [*_extract_lines(th_result), *_extract_lines(en_result)]:
        if line in seen:
            continue
        seen.add(line)
        merged_lines.append(line)

    return "\n".join(merged_lines).strip()
