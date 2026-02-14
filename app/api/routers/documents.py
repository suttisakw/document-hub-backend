from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import PurePosixPath
from typing import List
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models import Document, DocumentPage, ExtractedField, User
from app.schemas import (
    DocumentDetailResponse,
    DocumentExportRequest,
    DocumentListResponse,
    DocumentPageResponse,
    DocumentResponse,
    DocumentStatsResponse,
    DocumentStatsWeeklyItem,
    DocumentUpdate,
    DocumentTablesUpdate,
    ExtractedFieldResponse,
    ExtractedFieldUpdate,
)
from app.services.audit import write_audit_log
from app.services.pdf_render import render_pdf_to_png_pages
from app.services.storage import (
    StorageError,
    get_storage,
    storage_http_exception,
)
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get(
    "/",
    response_model=DocumentListResponse,
    summary="List documents",
    description="Paginated list with filters: q, status, type, date range, confidence, sort.",
)
def list_documents(
    q: str | None = None,
    status: str | None = None,
    type: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    confidence_min: float | None = None,
    confidence_max: float | None = None,
    sort_by: str | None = "created_at",
    sort_order: str | None = "desc",
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DocumentListResponse:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    def _parse_dt(value: str, *, end_of_day: bool) -> datetime | None:
        try:
            if len(value) == 10:
                suffix = "T23:59:59" if end_of_day else "T00:00:00"
                return datetime.fromisoformat(f"{value}{suffix}")
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    dt_from = _parse_dt(created_from, end_of_day=False) if created_from else None
    dt_to = _parse_dt(created_to, end_of_day=True) if created_to else None

    service = DocumentService(session)
    docs, total = service.list_documents(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        q=q,
        status=status,
        type=type,
        created_from=dt_from,
        created_to=dt_to
    )

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d, from_attributes=True) for d in docs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=DocumentListResponse)
async def search_documents(
    q: str,
    limit: int = 50,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Perform advanced full-text search across document contents."""
    service = DocumentService(session)
    results = service.search_advanced(current_user.id, q, limit)
    return DocumentListResponse(items=results, total=len(results), limit=limit, offset=0)


@router.get("/{document_id}/similar", response_model=List[DocumentResponse])
async def get_similar_documents(
    document_id: UUID,
    limit: int = 5,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Discover documents similar to the given one (by type/vendor)."""
    service = DocumentService(session)
    return service.get_similar_documents(document_id, current_user.id, limit)


@router.get("/{document_id}/summary")
async def get_document_summary(
    document_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Generate and return an AI-powered summary of the document."""
    service = DocumentService(session)
    summary = await service.generate_summary(document_id, current_user.id)
    return {"summary": summary}


@router.get(
    "/stats",
    response_model=DocumentStatsResponse,
    summary="Document statistics",
    description="Aggregate counts by status and type for current user's documents.",
)
def document_stats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DocumentStatsResponse:
    docs = session.exec(select(Document).where(Document.user_id == current_user.id)).all()
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for d in docs:
        by_status[d.status] = by_status.get(d.status, 0) + 1
        by_type[d.type] = by_type.get(d.type, 0) + 1

    return DocumentStatsResponse(
        total=len(docs),
        by_status=by_status,
        by_type=by_type,
    )


@router.get(
    "/stats/weekly",
    response_model=list[DocumentStatsWeeklyItem],
    summary="Weekly document counts",
    description="Daily document counts for the last N days (1–60).",
)
def document_stats_weekly(
    days: int = 7,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[DocumentStatsWeeklyItem]:
    days = max(1, min(days, 60))
    start_date = datetime.utcnow().date() - timedelta(days=days - 1)

    docs = session.exec(
        select(Document).where(
            Document.user_id == current_user.id,
            Document.created_at >= datetime.combine(start_date, datetime.min.time()),
        )
    ).all()
    counts: dict[str, int] = {}
    for d in docs:
        key = d.created_at.date().isoformat()
        counts[key] = counts.get(key, 0) + 1

    out: list[DocumentStatsWeeklyItem] = []
    for i in range(days):
        day = start_date + timedelta(days=i)
        key = day.isoformat()
        out.append(DocumentStatsWeeklyItem(date=key, count=counts.get(key, 0)))
    return out


@router.get(
    "/recent",
    response_model=list[DocumentResponse],
    summary="Recent documents",
    description="Latest documents for current user (limit 1–100).",
)
def recent_documents(
    limit: int = 10,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[Document]:
    limit = max(1, min(limit, 100))
    docs = session.exec(
        select(Document)
        .where(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .limit(limit)
    ).all()
    return list(docs)


@router.post(
    "/",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload document",
    description="Upload a file (PDF/image). Creates document and stores file.",
)
def create_document(
    request: Request,
    type: str = Form(...),
    name: str | None = Form(None),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Document:
    service = DocumentService(session)
    doc = service.create_document(current_user.id, file, doc_type=type)
    
    if name:
        doc.name = name
    
    # Image preview logic
    if (doc.mime_type or "").startswith("image/"):
        session.add(
            DocumentPage(
                document_id=doc.id,
                page_number=1,
                image_path=doc.file_path,
                created_at=datetime.utcnow(),
            )
        )
    
    session.add(doc)
    session.commit()
    session.refresh(doc)

    write_audit_log(
        session=session,
        actor=current_user,
        action="document.upload",
        entity_type="document",
        entity_id=doc.id,
        document_id=doc.id,
        request=request,
        meta={"name": doc.name, "type": doc.type, "mime_type": doc.mime_type},
    )
    session.commit()

    return doc


@router.post(
    "/export",
    summary="Export documents as ZIP",
    description="Returns a ZIP of requested documents. Headers: X-Requested-Count, X-Exported-Count.",
    responses={200: {"description": "ZIP stream"}},
)
def export_documents_zip(
    body: DocumentExportRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    doc_ids = list(dict.fromkeys(body.document_ids))
    if not doc_ids:
        raise HTTPException(status_code=400, detail="document_ids is required")

    service = DocumentService(session)
    buffer, filename, requested_count, exported_count = service.export_documents_zip(doc_ids, current_user.id)

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Requested-Count": str(requested_count),
            "X-Exported-Count": str(exported_count),
        },
    )


@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    summary="Get document detail",
    description="Document with extracted fields and page images.",
)
def get_document(
    document_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DocumentDetailResponse:
    service = DocumentService(session)
    doc, fields, pages = service.get_document_with_details(document_id, current_user.id)

    # Build response
    return DocumentDetailResponse(
        id=doc.id,
        user_id=doc.user_id,
        name=doc.name,
        type=doc.type,
        status=doc.status,
        file_path=doc.file_path,
        file_size=doc.file_size,
        mime_type=doc.mime_type,
        pages=doc.pages,
        confidence=doc.confidence,
        created_at=doc.created_at,
        extracted_fields=[
            ExtractedFieldResponse.model_validate(f, from_attributes=True)
            for f in fields
        ],
        page_images=[
            DocumentPageResponse.model_validate(p, from_attributes=True) for p in pages
        ],
    )


@router.patch(
    "/{document_id}/fields/{field_id}",
    response_model=ExtractedFieldResponse,
    summary="Update extracted field",
    description="Update field value and mark as edited.",
)
def update_extracted_field(
    document_id: UUID,
    field_id: UUID,
    patch: ExtractedFieldUpdate,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ExtractedFieldResponse:
    doc = session.exec(
        select(Document).where(
            Document.id == document_id, Document.user_id == current_user.id
        )
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    field = session.exec(
        select(ExtractedField).where(
            ExtractedField.id == field_id,
            ExtractedField.document_id == doc.id,
        )
    ).first()
    if field is None:
        raise HTTPException(status_code=404, detail="Field not found")

    old = field.field_value
    field.field_value = patch.field_value
    field.is_edited = True
    field.updated_at = datetime.utcnow()
    session.add(field)
    session.commit()
    session.refresh(field)

    write_audit_log(
        session=session,
        actor=current_user,
        action="field.update",
        entity_type="extracted_field",
        entity_id=field.id,
        document_id=doc.id,
        request=request,
        meta={
            "field_name": field.field_name,
            "from": old,
            "to": patch.field_value,
            "page_number": field.page_number,
        },
    )
    session.commit()
    return ExtractedFieldResponse.model_validate(field, from_attributes=True)


@router.get(
    "/{document_id}/pages",
    response_model=list[DocumentPageResponse],
    summary="List document pages",
    description="Rendered page images metadata for the document.",
)
def list_pages(
    document_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[DocumentPageResponse]:
    doc = session.exec(
        select(Document).where(
            Document.id == document_id, Document.user_id == current_user.id
        )
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    pages = session.exec(
        select(DocumentPage)
        .where(DocumentPage.document_id == doc.id)
        .order_by(DocumentPage.page_number.asc())
    ).all()
    return [DocumentPageResponse.model_validate(p, from_attributes=True) for p in pages]


@router.post(
    "/{document_id}/render",
    response_model=list[DocumentPageResponse],
    summary="Re-render PDF pages",
    description="Forces re-rendering of PDF pages to PNG images.",
)
def render_pdf_pages(
    document_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[DocumentPageResponse]:
    service = DocumentService(session)
    pages = service.render_pages(document_id, current_user.id)

    write_audit_log(
        session=session,
        actor=current_user,
        action="document.render_pages",
        entity_type="document",
        entity_id=document_id,
        document_id=document_id,
        request=request,
        meta={"pages": len(pages)},
    )
    session.commit()

    return [DocumentPageResponse.model_validate(p, from_attributes=True) for p in pages]


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete document",
    description="Delete document and stored file.",
)
def delete_document(
    document_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service = DocumentService(session)
    doc_meta = service.delete_document(document_id, current_user.id)

    write_audit_log(
        session=session,
        actor=current_user,
        action="document.delete",
        entity_type="document",
        entity_id=document_id,
        document_id=document_id,
        request=request,
        meta=doc_meta,
    )
    session.commit()


@router.patch(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Update document",
    description="Update name and/or type.",
)
def update_document(
    document_id: UUID,
    patch: DocumentUpdate,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Document:
    doc = session.exec(
        select(Document).where(
            Document.id == document_id, Document.user_id == current_user.id
        )
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    changed = False
    meta: dict = {}
    if patch.name is not None:
        meta["name"] = {"from": doc.name, "to": patch.name}
        doc.name = patch.name
        changed = True
    if patch.type is not None:
        meta["type"] = {"from": doc.type, "to": patch.type}
        doc.type = patch.type
        changed = True

    if changed:
        doc.updated_at = datetime.utcnow()
        session.add(doc)
        session.commit()
        session.refresh(doc)

        write_audit_log(
            session=session,
            actor=current_user,
            action="document.update",
            entity_type="document",
            entity_id=doc.id,
            document_id=doc.id,
            request=request,
            meta=meta,
        )
        session.commit()

    return doc


@router.patch("/{document_id}/tables", response_model=DocumentResponse)
async def update_document_tables(
    document_id: UUID,
    patch: DocumentTablesUpdate,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update extracted table data (manual corrections)."""
    doc = session.exec(
        select(Document).where(
            Document.id == document_id, Document.user_id == current_user.id
        )
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    old_tables = doc.extracted_tables
    doc.extracted_tables = patch.extracted_tables
    doc.updated_at = datetime.utcnow()
    doc.has_corrections = True
    
    session.add(doc)
    
    write_audit_log(
        session=session,
        actor=current_user,
        action="document.update_tables",
        entity_type="document",
        entity_id=doc.id,
        document_id=doc.id,
        request=request,
        meta={"tables": {"from": old_tables, "to": doc.extracted_tables}},
    )
    
    session.commit()
    session.refresh(doc)
    return doc


@router.get(
    "/{document_id}/file",
    summary="Download document file",
    description="Streams the stored file (PDF/image).",
    responses={200: {"description": "File stream"}},
)
def get_document_file(
    document_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service = DocumentService(session)
    return service.get_file_response(document_id, current_user.id)


@router.get(
    "/{document_id}/pages/{page_number}/image",
    summary="Get page image",
    description="Image for a single rendered page (e.g. PNG).",
    responses={200: {"description": "Image stream"}},
)
def get_page_image(
    document_id: UUID,
    page_number: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service = DocumentService(session)
    return service.get_page_image(document_id, page_number, current_user.id)
