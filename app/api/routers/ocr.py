from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import delete, false
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_session
from app.models import (
    Document,
    DocumentPage,
    ExternalOcrInterface,
    ExtractedField,
    OcrJob,
    User,
)
from app.schemas import (
    OcrJobResponse,
    OcrJobWithDocumentResponse,
    OcrTriggerExternalRequest,
)
from app.services.ocr_easyocr import run_easyocr_on_image_bytes
from app.services.ocr_external import trigger_external_ocr
from app.services.pdf_render import render_pdf_to_png_pages
from app.services.storage import resolve_storage_path, save_bytes

router = APIRouter(prefix="/ocr", tags=["ocr"])


TERMINAL_JOB_STATUSES = ["completed", "error", "cancelled"]


def _apply_external_structured_result(
    *,
    session: Session,
    doc: Document,
    job: OcrJob,
    payload: dict,
) -> None:
    # Expected payload shape (example):
    # {
    #   status: true,
    #   error: null,
    #   request_id: 652,
    #   interface_id: "...",
    #   transaction_id: "...",
    #   result: [{ doc_type: "INVOICE", pages: [3,3], data: {"Total": {page:1,value:... ,bbox:{...}}}}]
    # }

    if payload.get("status") is not True:
        job.status = "error"
        job.error_message = str(payload.get("error") or "External OCR error")
        job.completed_at = datetime.utcnow()
        session.add(job)
        doc.status = "error"
        doc.updated_at = datetime.utcnow()
        session.add(doc)
        return

    # Replace unedited extracted fields for this document
    session.exec(
        delete(ExtractedField).where(
            ExtractedField.document_id == doc.id,
            ExtractedField.is_edited == false(),
        )
    )

    result_list = payload.get("result") or []
    if not isinstance(result_list, list):
        result_list = []

    # Update document type/pages from first result element
    if result_list:
        first = result_list[0] if isinstance(result_list[0], dict) else {}
        doc_type = first.get("doc_type")
        if isinstance(doc_type, str) and doc_type:
            doc.type = doc_type

        pages_meta = first.get("pages")
        if isinstance(pages_meta, list) and pages_meta:
            try:
                doc.pages = int(max(pages_meta))
            except Exception:
                pass

        data = first.get("data")
        if isinstance(data, dict):
            for field_name, field_obj in data.items():
                if not isinstance(field_name, str) or not isinstance(field_obj, dict):
                    continue
                page_number = field_obj.get("page")
                value = field_obj.get("value")
                bbox = field_obj.get("bbox")

                bbox_left = bbox_top = bbox_right = bbox_bottom = None
                if isinstance(bbox, dict):
                    bbox_top = bbox.get("top")
                    bbox_left = bbox.get("left")
                    bbox_right = bbox.get("right")
                    bbox_bottom = bbox.get("bottom")

                # External bbox is normalized [0..1] with left/right/top/bottom.
                # Store as x/y/width/height in the same normalized space.
                x = float(bbox_left) if bbox_left is not None else None
                y = float(bbox_top) if bbox_top is not None else None
                w = (
                    float(bbox_right) - float(bbox_left)
                    if bbox_right is not None and bbox_left is not None
                    else None
                )
                h = (
                    float(bbox_bottom) - float(bbox_top)
                    if bbox_bottom is not None and bbox_top is not None
                    else None
                )

                session.add(
                    ExtractedField(
                        document_id=doc.id,
                        page_id=None,
                        page_number=int(page_number)
                        if page_number is not None
                        else None,
                        field_name=field_name,
                        field_value=str(value) if value is not None else None,
                        confidence=None,
                        bbox_x=x,
                        bbox_y=y,
                        bbox_width=w,
                        bbox_height=h,
                        is_edited=False,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                )

    job.status = "completed"
    job.completed_at = datetime.utcnow()
    session.add(job)

    doc.status = "scanned"
    doc.scanned_at = datetime.utcnow()
    doc.updated_at = datetime.utcnow()
    session.add(doc)


@router.get("/jobs", response_model=list[OcrJobWithDocumentResponse])
def list_jobs(
    provider: str | None = None,
    status: str | None = None,
    document_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[OcrJobWithDocumentResponse]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    docs = session.exec(select(Document).where(Document.user_id == current_user.id)).all()
    if not docs:
        return []
    docs_by_id = {d.id: d for d in docs}

    stmt = select(OcrJob).where(OcrJob.document_id.in_(list(docs_by_id.keys())))
    if document_id is not None:
        if document_id not in docs_by_id:
            return []
        stmt = stmt.where(OcrJob.document_id == document_id)
    if provider:
        stmt = stmt.where(OcrJob.provider == provider)
    if status:
        stmt = stmt.where(OcrJob.status == status)

    jobs = session.exec(stmt.order_by(OcrJob.requested_at.desc()).offset(offset).limit(limit)).all()
    out: list[OcrJobWithDocumentResponse] = []
    for job in jobs:
        doc = docs_by_id.get(job.document_id)
        if doc is None:
            continue
        out.append(
            OcrJobWithDocumentResponse(
                **OcrJobResponse.model_validate(job, from_attributes=True).model_dump(),
                document_name=doc.name,
                document_type=doc.type,
                document_status=doc.status,
            )
        )
    return out


@router.get("/jobs/queue", response_model=list[OcrJobWithDocumentResponse])
def list_job_queue(
    limit: int = 100,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[OcrJobWithDocumentResponse]:
    limit = max(1, min(limit, 200))
    docs = session.exec(select(Document).where(Document.user_id == current_user.id)).all()
    if not docs:
        return []
    docs_by_id = {d.id: d for d in docs}

    jobs = session.exec(
        select(OcrJob)
        .where(
            OcrJob.document_id.in_(list(docs_by_id.keys())),
            OcrJob.status.in_(["triggered", "running"]),
        )
        .order_by(OcrJob.requested_at.desc())
        .limit(limit)
    ).all()

    out: list[OcrJobWithDocumentResponse] = []
    for job in jobs:
        doc = docs_by_id.get(job.document_id)
        if doc is None:
            continue
        out.append(
            OcrJobWithDocumentResponse(
                **OcrJobResponse.model_validate(job, from_attributes=True).model_dump(),
                document_name=doc.name,
                document_type=doc.type,
                document_status=doc.status,
            )
        )
    return out


@router.get("/jobs/history", response_model=list[OcrJobWithDocumentResponse])
def list_job_history(
    provider: str | None = None,
    document_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[OcrJobWithDocumentResponse]:
    limit = max(1, min(limit, 300))
    offset = max(0, offset)

    docs = session.exec(select(Document).where(Document.user_id == current_user.id)).all()
    if not docs:
        return []
    docs_by_id = {d.id: d for d in docs}

    stmt = select(OcrJob).where(
        OcrJob.document_id.in_(list(docs_by_id.keys())),
        OcrJob.status.in_(TERMINAL_JOB_STATUSES),
    )
    if document_id is not None:
        if document_id not in docs_by_id:
            return []
        stmt = stmt.where(OcrJob.document_id == document_id)
    if provider:
        stmt = stmt.where(OcrJob.provider == provider)

    jobs = session.exec(
        stmt.order_by(OcrJob.requested_at.desc()).offset(offset).limit(limit)
    ).all()
    out: list[OcrJobWithDocumentResponse] = []
    for job in jobs:
        doc = docs_by_id.get(job.document_id)
        if doc is None:
            continue
        out.append(
            OcrJobWithDocumentResponse(
                **OcrJobResponse.model_validate(job, from_attributes=True).model_dump(),
                document_name=doc.name,
                document_type=doc.type,
                document_status=doc.status,
            )
        )
    return out


@router.post("/jobs/{job_id}/retry", response_model=OcrJobResponse)
async def retry_job(
    job_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OcrJob:
    old_job = session.exec(select(OcrJob).where(OcrJob.id == job_id)).first()
    if old_job is None:
        raise HTTPException(status_code=404, detail="OCR job not found")

    doc = session.exec(select(Document).where(Document.id == old_job.document_id)).first()
    if doc is None or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="OCR job not found")

    if old_job.status != "error":
        raise HTTPException(status_code=400, detail="Only failed jobs can be retried")

    if old_job.provider == "easyocr":
        return run_easyocr(
            document_id=doc.id,
            session=session,
            current_user=current_user,
        )

    if old_job.provider == "external":
        interface_uuid = old_job.interface_id
        if interface_uuid is None:
            default_interface = session.exec(
                select(ExternalOcrInterface).where(
                    ExternalOcrInterface.user_id == current_user.id,
                    ExternalOcrInterface.enabled.is_(True),
                    ExternalOcrInterface.is_default.is_(True),
                )
            ).first()
            if default_interface is None:
                raise HTTPException(
                    status_code=400,
                    detail="Retry failed: no interface_id on old job and no default interface",
                )
            interface_uuid = default_interface.id

        return await trigger_external(
            document_id=doc.id,
            body=OcrTriggerExternalRequest(
                interface_id=str(interface_uuid),
                transaction_id=str(uuid4()),
                filepath=None,
            ),
            request=request,
            session=session,
            current_user=current_user,
        )

    raise HTTPException(status_code=400, detail="Unsupported OCR provider")


@router.post("/jobs/{job_id}/cancel", response_model=OcrJobResponse)
def cancel_job(
    job_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OcrJob:
    job = session.exec(select(OcrJob).where(OcrJob.id == job_id)).first()
    if job is None:
        raise HTTPException(status_code=404, detail="OCR job not found")

    doc = session.exec(select(Document).where(Document.id == job.document_id)).first()
    if doc is None or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="OCR job not found")

    if job.status in TERMINAL_JOB_STATUSES:
        raise HTTPException(status_code=400, detail="Job is already completed")

    job.status = "cancelled"
    job.error_message = "Cancelled by user"
    job.completed_at = datetime.now(UTC)
    session.add(job)

    active_other = session.exec(
        select(OcrJob)
        .where(
            OcrJob.document_id == doc.id,
            OcrJob.id != job.id,
            OcrJob.status.in_(["pending", "triggered", "running"]),
        )
        .limit(1)
    ).first()
    if active_other is None and doc.status == "processing":
        doc.status = "pending"
        doc.updated_at = datetime.now(UTC)
        session.add(doc)

    session.commit()
    session.refresh(job)
    return job


@router.get("/jobs/{job_id}/result", response_model=dict)
def get_job_result(
    job_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    job = session.exec(select(OcrJob).where(OcrJob.id == job_id)).first()
    if job is None:
        raise HTTPException(status_code=404, detail="OCR job not found")

    doc = session.exec(select(Document).where(Document.id == job.document_id)).first()
    if doc is None or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="OCR job not found")

    return {
        "job_id": str(job.id),
        "document_id": str(job.document_id),
        "provider": job.provider,
        "status": job.status,
        "requested_at": job.requested_at,
        "completed_at": job.completed_at,
        "error_message": job.error_message,
        "result_json": job.result_json,
    }


@router.get("/jobs/{document_id}", response_model=list[OcrJobResponse])
def list_document_jobs(
    document_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[OcrJob]:
    doc = session.exec(
        select(Document).where(
            Document.id == document_id, Document.user_id == current_user.id
        )
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    jobs = session.exec(
        select(OcrJob)
        .where(OcrJob.document_id == doc.id)
        .order_by(OcrJob.requested_at.desc())
    ).all()
    return list(jobs)


@router.get("/job/{job_id}", response_model=OcrJobResponse)
def get_job(
    job_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OcrJob:
    job = session.exec(select(OcrJob).where(OcrJob.id == job_id)).first()
    if job is None:
        raise HTTPException(status_code=404, detail="OCR job not found")

    # Ensure user owns the document
    doc = session.exec(select(Document).where(Document.id == job.document_id)).first()
    if doc is None or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="OCR job not found")

    return job


@router.post("/trigger/external/{document_id}", response_model=OcrJobResponse)
async def trigger_external(
    document_id: UUID,
    body: OcrTriggerExternalRequest,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OcrJob:
    try:
        interface_uuid = UUID(body.interface_id)
        transaction_uuid = UUID(body.transaction_id)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail="Invalid interface_id/transaction_id"
        ) from e

    # Resolve interface config (from DB, fallback to env)
    interface_item = session.exec(
        select(ExternalOcrInterface).where(
            ExternalOcrInterface.user_id == current_user.id,
            ExternalOcrInterface.id == interface_uuid,
        )
    ).first()

    trigger_url = (
        interface_item.trigger_url if interface_item else settings.ocr_external_url
    )
    api_key = (
        interface_item.api_key
        if interface_item and interface_item.api_key
        else settings.ocr_external_api_key
    )

    if not trigger_url:
        raise HTTPException(
            status_code=400, detail="External OCR trigger URL is not configured"
        )
    if interface_item is not None and not interface_item.enabled:
        raise HTTPException(
            status_code=400, detail="External OCR interface is disabled"
        )

    doc = session.exec(
        select(Document).where(
            Document.id == document_id, Document.user_id == current_user.id
        )
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Build filepath for external OCR to fetch.
    if body.filepath:
        filepath = body.filepath
    else:
        base = settings.public_base_url.rstrip("/")
        if not base:
            base = str(request.base_url).rstrip("/")
        filepath = f"{base}/documents/{doc.id}/file"

    job = OcrJob(
        document_id=doc.id,
        provider="external",
        status="triggered",
        requested_at=datetime.utcnow(),
        interface_id=interface_uuid,
        transaction_id=transaction_uuid,
    )
    session.add(job)
    doc.status = "processing"
    doc.updated_at = datetime.utcnow()
    session.add(doc)
    session.commit()
    session.refresh(job)

    try:
        result = await trigger_external_ocr(
            url=trigger_url,
            api_key=api_key,
            filepath=filepath,
            interface_id=body.interface_id,
            transaction_id=body.transaction_id,
        )
    except Exception as e:
        job.status = "error"
        job.error_message = str(e)
        session.add(job)
        session.commit()
        raise HTTPException(
            status_code=502, detail="External OCR trigger failed"
        ) from e

    job.external_job_id = result.external_job_id
    job.result_json = result.raw
    if result.raw.get("request_id") is not None:
        try:
            job.request_id = int(result.raw.get("request_id"))
        except Exception:
            pass
    session.add(job)

    # If the external returns structured result immediately, apply it now.
    if isinstance(result.raw, dict) and result.raw.get("result") is not None:
        _apply_external_structured_result(
            session=session, doc=doc, job=job, payload=result.raw
        )

    session.commit()
    session.refresh(job)
    return job


@router.post("/run/easyocr/{document_id}", response_model=OcrJobResponse)
def run_easyocr(
    document_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OcrJob:
    doc = session.exec(
        select(Document).where(
            Document.id == document_id, Document.user_id == current_user.id
        )
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    path = resolve_storage_path(settings.storage_dir, doc.file_path)
    try:
        file_bytes = path.read_bytes()
    except OSError as e:
        raise HTTPException(status_code=500, detail="Failed to read stored file") from e

    job = OcrJob(
        document_id=doc.id,
        provider="easyocr",
        status="running",
        requested_at=datetime.utcnow(),
    )
    session.add(job)
    doc.status = "processing"
    doc.updated_at = datetime.utcnow()
    session.add(doc)
    session.commit()
    session.refresh(job)

    extracted_count = 0
    try:
        if (
            doc.mime_type or ""
        ).lower() == "application/pdf" or path.name.lower().endswith(".pdf"):
            rendered = render_pdf_to_png_pages(file_bytes)
            doc.pages = len(rendered)
            session.add(doc)
            session.commit()

            for page in rendered:
                rel = f"pages/{doc.id}/{page.page_number}.png"
                save_bytes(settings.storage_dir, rel, page.png_bytes)
                session.add(
                    DocumentPage(
                        document_id=doc.id,
                        page_number=page.page_number,
                        image_path=rel,
                        width=page.width,
                        height=page.height,
                        created_at=datetime.utcnow(),
                    )
                )

                fields = run_easyocr_on_image_bytes(page.png_bytes)
                for f in fields:
                    session.add(
                        ExtractedField(
                            document_id=doc.id,
                            page_id=None,
                            page_number=page.page_number,
                            field_name=f.field_name,
                            field_value=f.field_value,
                            confidence=f.confidence,
                            bbox_x=f.bbox_x,
                            bbox_y=f.bbox_y,
                            bbox_width=f.bbox_width,
                            bbox_height=f.bbox_height,
                            is_edited=False,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                        )
                    )
                    extracted_count += 1
        else:
            fields = run_easyocr_on_image_bytes(file_bytes)
            for f in fields:
                session.add(
                    ExtractedField(
                        document_id=doc.id,
                        page_id=None,
                        page_number=1,
                        field_name=f.field_name,
                        field_value=f.field_value,
                        confidence=f.confidence,
                        bbox_x=f.bbox_x,
                        bbox_y=f.bbox_y,
                        bbox_width=f.bbox_width,
                        bbox_height=f.bbox_height,
                        is_edited=False,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                )
                extracted_count += 1
    except Exception as e:
        job.status = "error"
        job.error_message = str(e)
        session.add(job)
        session.commit()
        raise HTTPException(
            status_code=400,
            detail="EasyOCR failed (unsupported file or OCR error)",
        ) from e

    job.status = "completed"
    job.completed_at = datetime.utcnow()
    session.add(job)

    doc.status = "scanned" if extracted_count > 0 else "error"
    doc.scanned_at = datetime.utcnow()
    doc.updated_at = datetime.utcnow()
    session.add(doc)

    session.commit()
    session.refresh(job)
    return job


@router.post(
    "/webhook/external",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def external_webhook(
    payload: dict,
    x_ocr_secret: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Response:
    # Secret validation:
    # - If global secret is set, require it.
    # - Otherwise, require per-interface secret (looked up via interface_id or job.interface_id).
    if settings.ocr_external_webhook_secret:
        if not x_ocr_secret or x_ocr_secret != settings.ocr_external_webhook_secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    transaction_id = payload.get("transaction_id")
    interface_id = payload.get("interface_id")
    request_id = payload.get("request_id")

    job = None
    if request_id is not None:
        try:
            job = session.exec(
                select(OcrJob).where(OcrJob.request_id == int(request_id))
            ).first()
        except Exception:
            job = None

    if job is None and transaction_id:
        try:
            tx = UUID(str(transaction_id))
            job = session.exec(
                select(OcrJob).where(OcrJob.transaction_id == tx)
            ).first()
        except ValueError:
            job = None

    if job is None:
        raise HTTPException(status_code=404, detail="OCR job not found")

    if not settings.ocr_external_webhook_secret:
        # Validate per-interface secret
        iface_uuid = job.interface_id
        if iface_uuid is None and interface_id:
            try:
                iface_uuid = UUID(str(interface_id))
            except ValueError:
                iface_uuid = None

        if iface_uuid is None:
            raise HTTPException(
                status_code=401, detail="Missing interface_id for webhook validation"
            )

        iface = session.exec(
            select(ExternalOcrInterface).where(ExternalOcrInterface.id == iface_uuid)
        ).first()
        expected = iface.webhook_secret if iface else None
        if expected:
            if not x_ocr_secret or x_ocr_secret != expected:
                raise HTTPException(status_code=401, detail="Invalid webhook secret")

    doc = session.exec(select(Document).where(Document.id == job.document_id)).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if job.interface_id is None and interface_id:
        try:
            job.interface_id = UUID(str(interface_id))
        except ValueError:
            pass

    if job.transaction_id is None and transaction_id:
        try:
            job.transaction_id = UUID(str(transaction_id))
        except ValueError:
            pass
    if request_id is not None:
        try:
            job.request_id = int(request_id)
        except Exception:
            pass

    job.result_json = payload
    _apply_external_structured_result(
        session=session, doc=doc, job=job, payload=payload
    )
    session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
