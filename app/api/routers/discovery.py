from fastapi import APIRouter, Depends, Query
from sqlmodel import Session
from typing import List, Dict, Any
from uuid import UUID

from app.db.session import get_session
from app.api.deps import get_current_user
from app.models import User, Document
from app.services.discovery_service import DiscoveryService

from app.services.vector_service import VectorService
from app.services.audit_service import AuditService

router = APIRouter()

@router.get("/search")
def search_documents(
    query: str = Query(..., min_length=1),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> List[Any]:
    """Keyword-based search documents."""
    service = DiscoveryService(db)
    return service.search_documents(query)

@router.post("/semantic-search")
async def semantic_search(
    query: str = Query(..., min_length=1),
    limit: int = 10,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Semantic search (meaning-based) using vector embeddings."""
    service = VectorService(db)
    return await service.semantic_search(query, limit=limit)

@router.get("/{document_id}/audit")
async def audit_document(
    document_id: UUID,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Run an AI logic audit on the document's extracted data."""
    service = AuditService(db)
    return await service.audit_document(str(document_id))

@router.get("/{document_id}/summary")
async def get_document_summary(
    document_id: UUID,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Generate an AI summary for a document."""
    service = DiscoveryService(db)
    summary = await service.generate_summary(str(document_id))
    return {"document_id": document_id, "summary": summary}

@router.get("/{document_id}/similar")
def get_similar_documents(
    document_id: UUID,
    limit: int = 5,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Find documents similar to this one."""
    service = DiscoveryService(db)
    return service.find_similar_documents(str(document_id), limit=limit)
