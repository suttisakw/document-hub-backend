import logging
from typing import List, Dict, Any
from sqlmodel import Session, select, or_, text
from app.models import Document
from app.services.llm_service import get_llm_provider

logger = logging.getLogger(__name__)

class DiscoveryService:
    """Handles advanced search, similarity, and summarization."""
    
    def __init__(self, db: Session):
        self.db = db
        self.llm = get_llm_provider()

    def search_documents(self, query: str, limit: int = 20) -> List[Document]:
        """Full-text search using PostgreSQL tsvector."""
        # Using a simple ILIKE for now, but in Phase 3.3 we want proper FTS
        # Assuming full_text field exists on Document
        statement = select(Document).where(
            or_(
                Document.name.ilike(f"%{query}%"),
                Document.full_text.ilike(f"%{query}%")
            )
        ).limit(limit)
        return self.db.exec(statement).all()

    async def generate_summary(self, doc_id: str) -> str:
        """Generates an AI summary of the document."""
        doc = self.db.get(Document, doc_id)
        if not doc or not doc.full_text:
            return "No content to summarize."
        
        prompt = f"Summarize the following document content in 2-3 concise sentences:\n\n{doc.full_text[:4000]}"
        summary = await self.llm.generate(prompt)
        
        # We could save this to the doc model if we had a summary field
        return summary

    def find_similar_documents(self, doc_id: str, limit: int = 5) -> List[Document]:
        """Finds documents with similar types or vendor names."""
        doc = self.db.get(Document, doc_id)
        if not doc:
            return []
            
        # Basic heuristic-based similarity (Phase 3.3)
        # In Phase 5 (Semantic), this will use Vector Embeddings
        statement = select(Document).where(
            Document.id != doc.id,
            Document.type == doc.type
        ).limit(limit)
        
        return self.db.exec(statement).all()
