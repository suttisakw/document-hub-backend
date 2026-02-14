from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlmodel import Session
from typing import List, Dict, Any
from uuid import UUID

from app.db.session import get_session
from app.api.deps import get_current_user
from app.models import User
from app.services.export_service import ExportService

router = APIRouter()

@router.post("/{document_id}/target/{target}")
async def export_to_external_system(
    document_id: UUID,
    target: str,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Export document data to an external ERP system."""
    service = ExportService(db)
    try:
        result = await service.export_to_system(str(document_id), target)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

@router.get("/batch/csv")
def export_batch_csv(
    ids: List[str] = Query(..., alias="id"),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Export a batch of documents as CSV."""
    service = ExportService(db)
    csv_data = service.export_to_csv(ids)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=documents_export.csv"}
    )

@router.get("/batch/json")
def export_batch_json(
    ids: List[str] = Query(..., alias="id"),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Export a batch of documents as JSON."""
    service = ExportService(db)
    json_data = service.export_to_json(ids)
    return Response(
        content=json_data,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=documents_export.json"}
    )
