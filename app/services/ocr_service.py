from __future__ import annotations

from functools import lru_cache
from pathlib import Path


import re
from pathlib import Path
from typing import List, Optional

from app.providers.ocr.base import OcrProvider, OcrResult
from app.providers.ocr.paddle_provider import PaddleOcrProvider

# Global provider instance (could be moved to dependency injection later)
_DEFAULT_PROVIDER: OcrProvider = PaddleOcrProvider(use_gpu=False)

def get_ocr_provider() -> OcrProvider:
    """Get the configured OCR provider."""
    return _DEFAULT_PROVIDER

def extract_text(file_path: str, lang: str = "th") -> str:
    """
    Extract text from file using the configured OCR provider.
    
    Args:
        file_path: Path to file
        lang: Primary language (default 'th')
    """
    provider = get_ocr_provider()
    result = provider.extract_text(file_path, lang)
    return result.text

def extract_text_detailed(file_path: str, lang: str = "th") -> OcrResult:
    """
    Extract text with full details.
    """
    provider = get_ocr_provider()
    return provider.extract_text(file_path, lang)
