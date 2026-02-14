from __future__ import annotations

import io
import gc
import logging
from dataclasses import dataclass
from typing import Any, List
from contextlib import contextmanager

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EasyOcrField:
    field_name: str
    field_value: str
    confidence: float | None
    bbox_x: float | None
    bbox_y: float | None
    bbox_width: float | None
    bbox_height: float | None


class EasyOcrReader:
    """
    EasyOCR reader with proper lifecycle management.
    Replaces global singleton to prevent memory leaks.
    """
    
    def __init__(self, languages: List[str] = None, gpu: bool = False):
        self.languages = languages or ["en", "th"]
        self.gpu = gpu
        self._reader = None
    
    def __enter__(self):
        """Initialize reader on context entry."""
        import easyocr
        logger.info(f"Initializing EasyOCR reader: languages={self.languages}, gpu={self.gpu}")
        self._reader = easyocr.Reader(self.languages, gpu=self.gpu)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup reader on context exit."""
        logger.info("Cleaning up EasyOCR reader")
        self._reader = None
        gc.collect()  # Force garbage collection
    
    def readtext(self, image_np: np.ndarray) -> list:
        """Run OCR on image."""
        if self._reader is None:
            raise RuntimeError("Reader not initialized. Use context manager.")
        return self._reader.readtext(image_np)
    
    def readtext_batch(self, images: List[np.ndarray]) -> List[list]:
        """
        Run OCR on batch of images.
        More memory efficient than processing one by one.
        """
        if self._reader is None:
            raise RuntimeError("Reader not initialized. Use context manager.")
        
        results = []
        for img in images:
            result = self._reader.readtext(img)
            results.append(result)
        
        return results


def run_easyocr_on_image_bytes(image_bytes: bytes) -> list[EasyOcrField]:
    """
    Run OCR on single image (backward compatible).
    Uses context manager for proper cleanup.
    """
    with EasyOcrReader() as reader:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_np = np.array(img)
        results = reader.readtext(img_np)
        
        return _parse_ocr_results(results)


def run_easyocr_on_image_batch(image_bytes_list: List[bytes]) -> List[list[EasyOcrField]]:
    """
    Run OCR on batch of images.
    More efficient than processing individually.
    
    Args:
        image_bytes_list: List of image bytes
    
    Returns:
        List of OCR results for each image
    """
    with EasyOcrReader() as reader:
        # Convert all images to numpy arrays
        images = []
        for image_bytes in image_bytes_list:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img_np = np.array(img)
            images.append(img_np)
        
        # Process batch
        batch_results = reader.readtext_batch(images)
        
        # Parse results
        parsed_results = []
        for results in batch_results:
            parsed_results.append(_parse_ocr_results(results))
        
        return parsed_results


def _parse_ocr_results(results: list) -> list[EasyOcrField]:
    """Parse EasyOCR results into EasyOcrField objects."""
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
