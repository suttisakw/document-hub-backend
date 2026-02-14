from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import List, Dict, Any
from uuid import UUID
from datetime import datetime

from app.db.session import get_session
from app.api.deps import get_current_user
from app.models import User, Document, ExtractedField
from pydantic import BaseModel

router = APIRouter()

class ReviewAction(BaseModel):
    action: str  # approve, reject, skip
    corrections: Dict[str, str] | None = None

@router.get("/queue")
def get_review_queue(
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> List[Document]:
    """Get all documents flagging for manual review."""
    statement = select(Document).where(Document.status == "needs_review")
    return db.exec(statement).all()

@router.post("/{document_id}/action")
def process_review_action(
    document_id: UUID,
    action_data: ReviewAction,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Approve or reject a document with optional corrections."""
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    if action_data.action == "approve":
        doc.status = "completed"
        # Apply corrections if provided
        if action_data.corrections:
            for field_name, value in action_data.corrections.items():
                # Update or create ExtractedField
                field = db.exec(
                    select(ExtractedField).where(
                        ExtractedField.document_id == doc.id,
                        ExtractedField.field_name == field_name
                    )
                ).first()
                if field:
                    field.field_value = value
                    field.is_corrected = True
                    db.add(field)
        
        doc.scanned_at = datetime.utcnow()
        db.add(doc)
        db.commit()
        return {"status": "success", "message": "Document approved and finalized"}
        
    elif action_data.action == "reject":
        doc.status = "error"
        doc.error_message = "Rejected during manual review"
        db.add(doc)
        db.commit()
        return {"status": "success", "message": "Document rejected"}
        
    return {"status": "ignored"}
