import logging
from typing import List, Dict, Any
from app.models import Document, DocumentPage
from app.services.storage import get_storage
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

class TableExtractionEngine:
    """Handles table detection and extraction."""
    
    def __init__(self, db: Session):
        self.db = db
        self.storage = get_storage()

    async def extract_all_tables(self, doc: Document, pages: List[DocumentPage]) -> List[Dict[str, Any]]:
        """Extracts tables from all pages of a document."""
        from app.providers.table.paddle_table_provider import PaddleTableProvider
        table_provider = PaddleTableProvider()
        
        all_tables = []
        
        if pages:
            for page in pages:
                try:
                    page_tables = await table_provider.extract_tables(self.storage.get_full_path(page.image_path))
                    for t in page_tables:
                        t_dict = t.model_dump()
                        t_dict["page_number"] = page.page_number
                        all_tables.append(t_dict)
                except Exception as e:
                    logger.error(f"Table extraction failed for page {page.page_number}: {e}")
        else:
            # Fallback for single file if pages weren't created (unlikely in new flow)
            try:
                tables = await table_provider.extract_tables(self.storage.get_full_path(doc.file_path))
                all_tables = [t.model_dump() for t in tables]
            except Exception as e:
                logger.error(f"Table extraction failed for document: {e}")
                
        return all_tables
