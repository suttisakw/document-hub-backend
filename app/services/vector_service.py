import logging
from typing import List, Dict, Any, Optional
from sqlmodel import Session, select
import numpy as np
from app.models import Document
from app.services.llm_service import get_llm_provider

logger = logging.getLogger(__name__)

class VectorService:
    """Handles semantic indexing and cosine similarity search."""
    
    def __init__(self, db: Session):
        self.db = db
        self.llm = get_llm_provider()

    async def index_document(self, doc_id: str) -> Optional[List[float]]:
        """Generates and stores embedding for a document."""
        doc = self.db.get(Document, doc_id)
        if not doc or not doc.full_text:
            return None
            
        # Use first 2000 chars for semantic context
        embedding = await self.llm.get_embedding(doc.full_text[:4000])
        if embedding:
            doc.embedding = embedding
            self.db.add(doc)
            self.db.commit()
            logger.info(f"Indexed document {doc_id} semantically.")
            
        return embedding

    async def semantic_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Finds documents most semantically similar to the query."""
        query_vec = await self.llm.get_embedding(query)
        if not query_vec:
            return []
            
        # In a real system, we'd use pgvector or Faiss. 
        # Here we do a brute-force cosine similarity for demonstration.
        all_docs = self.db.exec(select(Document).where(Document.embedding != None)).all()
        if not all_docs:
            return []
            
        results = []
        q_norm = np.linalg.norm(query_vec)
        
        for doc in all_docs:
            doc_vec = np.array(doc.embedding)
            d_norm = np.linalg.norm(doc_vec)
            
            if q_norm > 0 and d_norm > 0:
                similarity = np.dot(query_vec, doc_vec) / (q_norm * d_norm)
                results.append({
                    "document": doc,
                    "score": float(similarity)
                })
                
        # Sort by similarity score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
