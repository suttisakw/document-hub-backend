from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from io import BytesIO
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
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import delete, func
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_session
from app.models import Document, DocumentPage, ExtractedField, User
from app.schemas import (
    DocumentDetailResponse,
    DocumentExportRequest,
    DocumentListResponse,
    DocumentPageResponse,
    DocumentResponse,
    DocumentUpdate,
    ExtractedFieldResponse,
    ExtractedFieldUpdate,
)
from app.services.audit import write_audit_log
from app.services.pdf_render import render_pdf_to_png_pages
from app.services.storage import resolve_storage_path, save_bytes, save_document_file

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/", response_model=DocumentListResponse)
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

    conditions = [Document.user_id == current_user.id]
    if status:
        conditions.append(Document.status == status)
    if type:
        conditions.append(Document.type == type)
    if q:
        conditions.append(Document.name.ilike(f"%{q}%"))

    def _parse_dt(value: str, *, end_of_day: bool) -> datetime | None:
        try:
            if len(value) == 10:
                suffix = "T23:59:59" if end_of_day else "T00:00:00"
                return datetime.fromisoformat(f"{value}{suffix}")
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    if created_from:
        dt = _parse_dt(created_from, end_of_day=False)
        if dt is not None:
            conditions.append(Document.created_at >= dt)
    if created_to:
        dt = _parse_dt(created_to, end_of_day=True)
        if dt is not None:
            conditions.append(Document.created_at <= dt)
    if confidence_min is not None:
        conditions.append(Document.confidence >= confidence_min)
    if confidence_max is not None:
        conditions.append(Document.confidence <= confidence_max)

    base_stmt = select(Document).where(*conditions)
    total = session.exec(select(func.count()).select_from(Document).where(*conditions)).one()

    sort_map = {
        "created_at": Document.created_at,
        "updated_at": Document.updated_at,
        "name": Document.name,
        "confidence": Document.confidence,
    }
    order_col = sort_map.get((sort_by or "created_at").lower(), Document.created_at)
    if (sort_order or "desc").lower() == "asc":
        base_stmt = base_stmt.order_by(order_col.asc())
    else:
        base_stmt = base_stmt.order_by(order_col.desc())

    docs = session.exec(base_stmt.offset(offset).limit(limit)).all()
    return DocumentListResponse(
        items=list(docs),
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=dict)
def document_stats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    docs = session.exec(select(Document).where(Document.user_id == current_user.id)).all()
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for d in docs:
        by_status[d.status] = by_status.get(d.status, 0) + 1
        by_type[d.type] = by_type.get(d.type, 0) + 1

    return {
        "total": len(docs),
        "by_status": by_status,
        "by_type": by_type,
    }


@router.get("/stats/weekly", response_model=list[dict])
def document_stats_weekly(
    days: int = 7,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
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

    out: list[dict] = []
    for i in range(days):
        day = start_date + timedelta(days=i)
        key = day.isoformat()
        out.append({"date": key, "count": counts.get(key, 0)})
    return out


@router.get("/recent", response_model=list[DocumentResponse])
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


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    request: Request,
    type: str = Form(...),
    name: str | None = Form(None),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Document:
    if file.filename is None:
        raise HTTPException(status_code=400, detail="Missing filename")

    doc = Document(
        user_id=current_user.id,
        name=name or file.filename,
        type=type,
        status="pending",
        file_path="",
        file_size=0,
        mime_type=file.content_type,
        pages=1,
        confidence=None,
        scanned_at=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
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

    file_path = save_document_file(settings.storage_dir, doc.id, file)
    try:
        size = os.path.getsize(resolve_storage_path(settings.storage_dir, file_path))
    except OSError:
        size = 0

    doc.file_path = file_path
    doc.file_size = size
    doc.updated_at = datetime.utcnow()
    session.add(doc)

    # If the upload is an image, use it as page 1 preview
    if (doc.mime_type or "").startswith("image/"):
        session.add(
            DocumentPage(
                document_id=doc.id,
                page_number=1,
                image_path=doc.file_path,
                width=None,
                height=None,
                created_at=datetime.utcnow(),
            )
        )

    session.commit()
    session.refresh(doc)

    return doc


@router.post("/export")
def export_documents_zip(
    body: DocumentExportRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    doc_ids = list(dict.fromkeys(body.document_ids))
    if not doc_ids:
        raise HTTPException(status_code=400, detail="document_ids is required")
    if len(doc_ids) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 documents per export")

    docs = session.exec(
        select(Document).where(Document.user_id == current_user.id, Document.id.in_(doc_ids))
    ).all()
    if not docs:
        raise HTTPException(status_code=404, detail="No documents found")

    requested_count = len(doc_ids)
    exported_count = 0
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zipf:
        for doc in docs:
            try:
                path = resolve_storage_path(settings.storage_dir, doc.file_path)
            except OSError:
                continue
            if not path.exists() or not path.is_file():
                continue

            ext = path.suffix if path.suffix else ""
            safe_name = (doc.name or str(doc.id)).strip() or str(doc.id)
            safe_name = safe_name.replace("/", "_").replace("\\", "_")
            arc_name = f"{doc.id}_{safe_name}{ext}"
            try:
                zipf.write(path, arcname=arc_name)
                exported_count += 1
            except OSError:
                continue

    if buffer.getbuffer().nbytes == 0:
        raise HTTPException(status_code=404, detail="No readable files for selected documents")

    buffer.seek(0)
    filename = f"document-export-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Requested-Count": str(requested_count),
            "X-Exported-Count": str(exported_count),
        },
    )


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DocumentDetailResponse:
    doc = session.exec(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == current_user.id,
        )
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    fields = session.exec(
        select(ExtractedField)
        .where(ExtractedField.document_id == doc.id)
        .order_by(ExtractedField.page_number.asc(), ExtractedField.created_at.asc())
    ).all()
    # Attach for response model
    pages = session.exec(
        select(DocumentPage)
        .where(DocumentPage.document_id == doc.id)
        .order_by(DocumentPage.page_number.asc())
    ).all()

    # Build response
    return DocumentDetailResponse(
        id=str(doc.id),
        user_id=str(doc.user_id),
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


@router.patch("/{document_id}/fields/{field_id}", response_model=ExtractedFieldResponse)
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


@router.get("/{document_id}/pages", response_model=list[DocumentPageResponse])
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


@router.post("/{document_id}/render", response_model=list[DocumentPageResponse])
def render_pdf_pages(
    document_id: UUID,
    request: Request,
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

    path = resolve_storage_path(settings.storage_dir, doc.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if (
        doc.mime_type or ""
    ).lower() != "application/pdf" and not path.name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Not a PDF")

    try:
        pdf_bytes = path.read_bytes()
    except OSError as e:
        raise HTTPException(status_code=500, detail="Failed to read stored file") from e

    rendered = render_pdf_to_png_pages(pdf_bytes)

    # Replace existing page images for this document
    session.exec(delete(DocumentPage).where(DocumentPage.document_id == doc.id))

    pages: list[DocumentPage] = []
    for page in rendered:
        rel = f"pages/{doc.id}/{page.page_number}.png"
        save_bytes(settings.storage_dir, rel, page.png_bytes)
        p = DocumentPage(
            document_id=doc.id,
            page_number=page.page_number,
            image_path=rel,
            width=page.width,
            height=page.height,
            created_at=datetime.utcnow(),
        )
        session.add(p)
        pages.append(p)

    doc.pages = len(rendered)
    doc.updated_at = datetime.utcnow()
    session.add(doc)
    session.commit()

    write_audit_log(
        session=session,
        actor=current_user,
        action="document.render_pages",
        entity_type="document",
        entity_id=doc.id,
        document_id=doc.id,
        request=request,
        meta={"pages": doc.pages},
    )
    session.commit()

    # Refresh pages ids
    out = session.exec(
        select(DocumentPage)
        .where(DocumentPage.document_id == doc.id)
        .order_by(DocumentPage.page_number.asc())
    ).all()
    return [DocumentPageResponse.model_validate(p, from_attributes=True) for p in out]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    doc = session.exec(
        select(Document).where(
            Document.id == document_id, Document.user_id == current_user.id
        )
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Note: file cleanup is best-effort; DB delete is primary.
    try:
        path = resolve_storage_path(settings.storage_dir, doc.file_path)
        if path.exists():
            path.unlink()
    except OSError:
        pass

    # Cleanup rendered pages (if any)
    try:
        pages_dir = resolve_storage_path(settings.storage_dir, f"pages/{doc.id}")
        if pages_dir.exists() and pages_dir.is_dir():
            for p in pages_dir.glob("*"):
                try:
                    p.unlink()
                except OSError:
                    pass
            try:
                pages_dir.rmdir()
            except OSError:
                pass
    except OSError:
        pass

    write_audit_log(
        session=session,
        actor=current_user,
        action="document.delete",
        entity_type="document",
        entity_id=doc.id,
        document_id=doc.id,
        request=request,
        meta={"name": doc.name, "type": doc.type, "status": doc.status},
    )

    session.delete(doc)
    session.commit()


@router.patch("/{document_id}", response_model=DocumentResponse)
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


@router.get("/{document_id}/file")
def get_document_file(
    document_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    doc = session.exec(
        select(Document).where(
            Document.id == document_id, Document.user_id == current_user.id
        )
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    path = resolve_storage_path(settings.storage_dir, doc.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path=path, media_type=doc.mime_type or None, filename=doc.name)


@router.get("/{document_id}/pages/{page_number}/image")
def get_page_image(
    document_id: UUID,
    page_number: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    doc = session.exec(
        select(Document).where(
            Document.id == document_id, Document.user_id == current_user.id
        )
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    page = session.exec(
        select(DocumentPage).where(
            DocumentPage.document_id == doc.id,
            DocumentPage.page_number == page_number,
        )
    ).first()
    if page is None or not page.image_path:
        raise HTTPException(status_code=404, detail="Page image not found")

    path = resolve_storage_path(settings.storage_dir, page.image_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Page image file not found")

    return FileResponse(path=path, media_type="image/png")
