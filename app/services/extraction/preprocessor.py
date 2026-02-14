import logging
from datetime import datetime, UTC
from typing import List, Tuple
from uuid import UUID
from app.models import Document, DocumentPage
from app.services.storage import get_storage
from sqlalchemy import delete
from sqlmodel import Session

logger = logging.getLogger(__name__)

class DocumentPreProcessor:
    """Handles PDF rendering and page image generation."""
    
    def __init__(self, db: Session):
        self.db = db
        self.storage = get_storage()

    async def prepare_pages(self, doc: Document) -> List[DocumentPage]:
        """
        Renders PDF to images or prepares single page for images.
        Clears existing pages.
        """
        # 1. Clear old pages
        self.db.exec(delete(DocumentPage).where(DocumentPage.document_id == doc.id))
        
        is_pdf = (doc.mime_type or "").lower() == "application/pdf" or doc.file_path.lower().endswith(".pdf")
        file_bytes = self.storage.read_bytes(doc.file_path)
        
        pages_objs = []
        
        if is_pdf:
            from app.services.pdf_render import render_pdf_to_png_pages
            rendered = render_pdf_to_png_pages(file_bytes)
            doc.pages = len(rendered)
            
            for page in rendered:
                rel_path = f"pages/{doc.id}/{page.page_number}.png"
                self.storage.save_bytes(rel_path, page.png_bytes)
                
                page_obj = DocumentPage(
                    document_id=doc.id,
                    page_number=page.page_number,
                    image_path=rel_path,
                    width=page.width,
                    height=page.height,
                    created_at=datetime.now(UTC)
                )
                self.db.add(page_obj)
                pages_objs.append(page_obj)
        else:
            doc.pages = 1
            page_obj = DocumentPage(
                document_id=doc.id,
                page_number=1,
                image_path=doc.file_path,
                created_at=datetime.now(UTC)
            )
            self.db.add(page_obj)
            pages_objs.append(page_obj)
            
        self.db.add(doc)
        self.db.commit()
        return pages_objs
