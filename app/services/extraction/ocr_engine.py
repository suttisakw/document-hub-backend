import os
import logging
import tempfile
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from app.services.ocr_service import extract_text_detailed
from app.services.storage import get_storage
from app.models import DocumentPage

logger = logging.getLogger(__name__)

@dataclass
class OcrResult:
    full_text: str
    pages_raw: List[Dict[str, Any]]
    lines_per_page: List[str]

import asyncio
from concurrent.futures import ProcessPoolExecutor

# Module-level executor to bypass GIL for CPU-bound OCR
# Using 2 workers as a starting point to avoid memory issues with Paddle/EasyOCR models
_ocr_executor = ProcessPoolExecutor(max_workers=2)

class OcrEngine:
    """Orchestrates OCR execution across document pages."""
    
    def __init__(self):
        self.storage = get_storage()

    async def run_ocr(self, pages: List[DocumentPage]) -> OcrResult:
        """
        Runs OCR on all provided pages with batch processing.
        Processes 5 pages at a time to reduce memory overhead.
        """
        all_text_lines = []
        all_raw_data = []
        loop = asyncio.get_running_loop()
        
        # Batch size for processing
        BATCH_SIZE = 5
        
        # Process pages in batches
        for batch_start in range(0, len(pages), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(pages))
            batch_pages = pages[batch_start:batch_end]
            
            logger.info(f"Processing OCR batch {batch_start//BATCH_SIZE + 1}: pages {batch_start+1}-{batch_end}")
            
            # Collect image bytes for batch
            batch_image_bytes = []
            batch_tmp_paths = []
            
            for page in batch_pages:
                image_bytes = self.storage.read_bytes(page.image_path)
                batch_image_bytes.append(image_bytes)
                
                # Create temp file
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp.write(image_bytes)
                    batch_tmp_paths.append(tmp.name)
            
            try:
                # Process batch in executor
                batch_results = await loop.run_in_executor(
                    _ocr_executor,
                    self._process_batch_sync,
                    batch_tmp_paths
                )
                
                # Collect results
                for page_ocr in batch_results:
                    all_text_lines.append(page_ocr.text)
                    if page_ocr.raw_data:
                        all_raw_data.append(page_ocr.raw_data)
                    else:
                        all_raw_data.append({})
            
            finally:
                # Cleanup temp files
                for tmp_path in batch_tmp_paths:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
        
        return OcrResult(
            full_text="\n".join(all_text_lines),
            pages_raw=all_raw_data,
            lines_per_page=all_text_lines
        )
    
    @staticmethod
    def _process_batch_sync(tmp_paths: List[str]):
        """Process batch of images synchronously (runs in executor)."""
        results = []
        for tmp_path in tmp_paths:
            page_ocr = extract_text_detailed(tmp_path)
            results.append(page_ocr)
        return results
