from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import delete, false
from sqlmodel import Session, select

from app.api.deps import get_current_user, require_admin
from app.core.config import settings
from app.db.session import get_session
from app.models import (
    Document,
    ExternalOcrInterface,
    ExtractedField,
    OcrJob,
    User,
)
from app.schemas import (
    OcrDlqItemResponse,
    OcrDlqPurgeResponse,
    OcrDlqRequeueResponse,
    OcrJobResponse,
    OcrJobResultResponse,
    OcrJobWithDocumentResponse,
    OcrQueueStatsResponse,
    OcrRequeueLogItemResponse,
    OcrTriggerExternalRequest,
)
from app.services.ocr_external import trigger_external_ocr
from app.services.ocr_queue import enqueue_easyocr_job
from app.services.redis_queue import (
    append_easyocr_ops_log,
    get_easyocr_queue_stats,
    list_easyocr_dlq,
    list_easyocr_ops_log,
    purge_easyocr_dlq,
    remove_easyocr_dlq_job,
    requeue_easyocr_dlq_job,
)

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


@router.get(
    "/jobs",
    response_model=list[OcrJobWithDocumentResponse],
    summary="List OCR jobs",
    description="Filter by provider, status, document_id; paginated.",
)
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


@router.get(
    "/jobs/queue",
    response_model=list[OcrJobWithDocumentResponse],
    summary="List queue jobs",
    description="Active jobs only: status triggered or running.",
)
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


@router.get(
    "/jobs/history",
    response_model=list[OcrJobWithDocumentResponse],
    summary="List job history",
    description="Terminal jobs: completed, error, cancelled.",
)
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


@router.get(
    "/ops/queue/stats",
    response_model=OcrQueueStatsResponse,
    summary="Queue stats (admin)",
    description="Queue depth, delayed, DLQ depth. Admin only.",
)
def get_queue_stats(
    _: User = Depends(require_admin),
) -> OcrQueueStatsResponse:
    stats = get_easyocr_queue_stats()
    return OcrQueueStatsResponse(
        queue_depth=stats.get("queue_depth", 0),
        processing_depth=stats.get("processing_depth", 0),
        delayed_depth=stats.get("delayed_depth", 0),
        dlq_depth=stats.get("dlq_depth", 0),
    )


@router.get(
    "/ops/dlq",
    response_model=list[OcrDlqItemResponse],
    summary="List DLQ (admin)",
    description="Dead-letter queue items. Admin only.",
)
def list_dlq(
    limit: int = 50,
    _: User = Depends(require_admin),
) -> list[OcrDlqItemResponse]:
    items = list_easyocr_dlq(limit=max(1, min(limit, 200)))
    out: list[OcrDlqItemResponse] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        job_id = str(item.get("job_id") or "")
        payload = {k: v for k, v in item.items() if k != "job_id"}
        out.append(OcrDlqItemResponse(job_id=job_id, payload=payload))
    return out


@router.post(
    "/ops/dlq/requeue/{job_id}",
    response_model=OcrDlqRequeueResponse,
    summary="Requeue DLQ job (admin)",
    description="Move job from DLQ back to queue. Admin only.",
)
def requeue_dlq_job(
    job_id: UUID,
    admin_user: User = Depends(require_admin),
) -> OcrDlqRequeueResponse:
    ok = requeue_easyocr_dlq_job(job_id=str(job_id))
    if not ok:
        return OcrDlqRequeueResponse(
            ok=False,
            message="Job not found in DLQ",
            job_id=str(job_id),
        )

    append_easyocr_ops_log(
        payload={
            "job_id": str(job_id),
            "action": "requeue",
            "at": datetime.now(UTC).isoformat(),
            "actor_user_id": str(admin_user.id),
            "actor_email": admin_user.email,
        }
    )

    return OcrDlqRequeueResponse(
        ok=True,
        message="Job requeued",
        job_id=str(job_id),
    )


@router.delete(
    "/ops/dlq/{job_id}",
    response_model=OcrDlqPurgeResponse,
    summary="Purge one DLQ job (admin)",
    description="Remove job from DLQ. Admin only.",
)
def purge_dlq_job(
    job_id: UUID,
    admin_user: User = Depends(require_admin),
) -> OcrDlqPurgeResponse:
    removed = 1 if remove_easyocr_dlq_job(job_id=str(job_id)) else 0
    if removed:
        append_easyocr_ops_log(
            payload={
                "job_id": str(job_id),
                "action": "purge",
                "at": datetime.now(UTC).isoformat(),
                "actor_user_id": str(admin_user.id),
                "actor_email": admin_user.email,
            }
        )
    return OcrDlqPurgeResponse(
        ok=removed > 0,
        message="Removed" if removed > 0 else "Job not found in DLQ",
        removed=removed,
        job_id=str(job_id),
    )


@router.delete(
    "/ops/dlq",
    response_model=OcrDlqPurgeResponse,
    summary="Purge all DLQ (admin)",
    description="Clear entire DLQ. Admin only.",
)
def purge_all_dlq(
    admin_user: User = Depends(require_admin),
) -> OcrDlqPurgeResponse:
    removed = purge_easyocr_dlq()
    append_easyocr_ops_log(
        payload={
            "job_id": "*",
            "action": "purge_all",
            "at": datetime.now(UTC).isoformat(),
            "actor_user_id": str(admin_user.id),
            "actor_email": admin_user.email,
            "removed": removed,
        }
    )
    return OcrDlqPurgeResponse(
        ok=True,
        message="DLQ purged",
        removed=removed,
    )


@router.get(
    "/ops/requeue-history",
    response_model=list[OcrRequeueLogItemResponse],
    summary="Requeue history (admin)",
    description="Log of requeue/purge actions. Admin only.",
)
def get_ops_history(
    limit: int = 50,
    _: User = Depends(require_admin),
) -> list[OcrRequeueLogItemResponse]:
    rows = list_easyocr_ops_log(limit=max(1, min(limit, 200)))
    out: list[OcrRequeueLogItemResponse] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            OcrRequeueLogItemResponse(
                job_id=str(row.get("job_id") or ""),
                action=str(row.get("action") or "unknown"),
                at=str(row.get("at") or ""),
                actor_user_id=str(row.get("actor_user_id"))
                if row.get("actor_user_id")
                else None,
                actor_email=str(row.get("actor_email")) if row.get("actor_email") else None,
            )
        )
    return out


@router.post(
    "/jobs/{job_id}/retry",
    response_model=OcrJobResponse,
    summary="Retry failed job",
    description="Only jobs with status 'error' can be retried.",
)
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
        return enqueue_easyocr_job(session=session, document_id=doc.id)

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


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=OcrJobResponse,
    summary="Cancel job",
    description="Cancel active job (pending/triggered/running).",
)
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


@router.get(
    "/jobs/{job_id}/result",
    response_model=OcrJobResultResponse,
    summary="Get job result",
    description="Normalized result envelope including result_json from provider.",
)
def get_job_result(
    job_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OcrJobResultResponse:
    job = session.exec(select(OcrJob).where(OcrJob.id == job_id)).first()
    if job is None:
        raise HTTPException(status_code=404, detail="OCR job not found")

    doc = session.exec(select(Document).where(Document.id == job.document_id)).first()
    if doc is None or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="OCR job not found")

    return OcrJobResultResponse(
        job_id=str(job.id),
        document_id=str(job.document_id),
        provider=job.provider,
        status=job.status,
        requested_at=job.requested_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        result_json=job.result_json,
    )


@router.get(
    "/jobs/{document_id}",
    response_model=list[OcrJobResponse],
    summary="List jobs for document",
    description="All OCR jobs for a single document.",
)
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


@router.get(
    "/job/{job_id}",
    response_model=OcrJobResponse,
    summary="Get job by ID",
    description="Single OCR job details.",
)
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


@router.post(
    "/trigger/external/{document_id}",
    response_model=OcrJobResponse,
    summary="Trigger external OCR",
    description="Send document to external OCR interface; returns job.",
)
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


@router.post(
    "/run/easyocr/{document_id}",
    response_model=OcrJobResponse,
    summary="Run EasyOCR",
    description="Enqueue EasyOCR job for document; returns existing job if already queued.",
)
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

    active_job = session.exec(
        select(OcrJob)
        .where(
            OcrJob.document_id == doc.id,
            OcrJob.provider == "easyocr",
            OcrJob.status.in_(["pending", "running"]),
        )
        .order_by(OcrJob.requested_at.desc())
        .limit(1)
    ).first()
    if active_job is not None:
        return active_job

    return enqueue_easyocr_job(session=session, document_id=doc.id)


@router.post(
    "/webhook/external",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="External OCR webhook",
    description="Callback for external OCR; validate X-OCR-Secret; apply result to job.",
    include_in_schema=True,
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
