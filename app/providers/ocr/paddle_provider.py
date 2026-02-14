import re
from pathlib import Path
from functools import lru_cache
from typing import List, Optional, Any

from app.providers.ocr.base import OcrProvider, OcrResult

class PaddleOcrProvider(OcrProvider):
    """PaddleOCR implementation of the OCR provider."""

    def __init__(self, use_gpu: bool = False):
        self.use_gpu = use_gpu

    @lru_cache(maxsize=4)
    def _get_model(self, lang: str):
        from paddleocr import PaddleOCR
        return PaddleOCR(use_angle_cls=True, lang=lang, use_gpu=self.use_gpu)

    def _has_thai(self, text: str) -> bool:
        """Check if text contains Thai characters."""
        return bool(re.search(r'[\u0e00-\u0e7f]', text))

    def _extract_lines(self, raw_result: list) -> List[str]:
        lines: List[str] = []
        for page in raw_result or []:
            if page is None:
                continue
            for entry in page:
                if not entry or len(entry) < 2:
                    continue
                text_data = entry[1]
                if not text_data or len(text_data) < 1:
                    continue
                text = str(text_data[0]).strip()
                if text:
                    lines.append(text)
        return lines

    def extract_text(self, file_path: str, lang: str = "th") -> OcrResult:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Input file not found: {file_path}")

        # Run primary language OCR
        model = self._get_model(lang)
        raw_result = model.ocr(str(path), cls=True)
        
        lines = self._extract_lines(raw_result)
        full_text = "\n".join(lines).strip()

        # Optimization for Thai/English
        if lang == "th" and not self._has_thai(full_text) and len(full_text) > 10:
            en_model = self._get_model("en")
            en_result = en_model.ocr(str(path), cls=True)
            lines = self._extract_lines(en_result)
            full_text = "\n".join(lines).strip()
            lang = "en"

        return OcrResult(
            text=full_text,
            lines=lines,
            raw_data=raw_result,
            language=lang,
            confidence=0.9  # PaddleOCR usually high but placeholder
        )

    def get_name(self) -> str:
        return "paddle_ocr"
