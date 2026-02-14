from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, false
from sqlmodel import Session, select

from app.core.config import settings
from app.models import Document, DocumentPage, ExtractedField, OcrJob
from app.services.ocr_easyocr import run_easyocr_on_image_bytes
from app.services.pdf_render import render_pdf_to_png_pages
from app.services.redis_lock import acquire_ocr_claim_lock, release_ocr_claim_lock
from app.services.redis_queue import (
    publish_easyocr_job,
    push_easyocr_dlq,
    schedule_easyocr_retry,
)
from app.services.storage import StorageError, get_storage


def enqueue_easyocr_job(*, session: Session, document_id: UUID) -> OcrJob:
    doc = session.exec(select(Document).where(Document.id == document_id)).first()
    if doc is None:
        raise ValueError("Document not found")

    job = OcrJob(
        document_id=doc.id,
        provider="easyocr",
        status="pending",
        requested_at=datetime.now(UTC),
    )
    session.add(job)

    doc.status = "processing"
    doc.updated_at = datetime.now(UTC)
    session.add(doc)

    session.commit()
    session.refresh(job)
    publish_easyocr_job(str(job.id))
    return job


def claim_easyocr_job_by_id(*, session: Session, job_id: UUID) -> OcrJob | None:
    lock_ok = acquire_ocr_claim_lock(job_id=str(job_id))
    if not lock_ok:
        return None

    try:
        job = session.exec(select(OcrJob).where(OcrJob.id == job_id)).first()
        if job is None:
            return None
        if job.provider != "easyocr" or job.status != "pending":
            return None

        job.status = "running"
        session.add(job)
        session.commit()
        session.refresh(job)
        return job
    finally:
        release_ocr_claim_lock(job_id=str(job_id))


def claim_next_pending_easyocr_job(*, session: Session) -> OcrJob | None:
    candidates = session.exec(
        select(OcrJob.id)
        .where(OcrJob.provider == "easyocr", OcrJob.status == "pending")
        .order_by(OcrJob.requested_at.asc())
        .limit(25)
    ).all()

    for candidate_id in candidates:
        lock_ok = acquire_ocr_claim_lock(job_id=str(candidate_id))
        if not lock_ok:
            continue

        try:
            job = session.exec(select(OcrJob).where(OcrJob.id == candidate_id)).first()
            if job is None or job.status != "pending":
                continue

            job.status = "running"
            session.add(job)
            session.commit()
            session.refresh(job)
            return job
        finally:
            release_ocr_claim_lock(job_id=str(candidate_id))

    return None


def process_easyocr_job(*, session: Session, job_id: UUID) -> OcrJob:
    job = session.exec(select(OcrJob).where(OcrJob.id == job_id)).first()
    if job is None:
        raise ValueError("OCR job not found")

    doc = session.exec(select(Document).where(Document.id == job.document_id)).first()
    if doc is None:
        raise ValueError("Document not found")

    if job.status in {"completed", "error", "cancelled"}:
        return job

    if job.status != "running":
        job.status = "running"
        session.add(job)
        session.commit()
        session.refresh(job)

    storage = get_storage()
    extracted_count = 0

    max_attempts = max(1, settings.ocr_queue_max_attempts)
    backoff_base = max(1, settings.ocr_queue_retry_base_seconds)
    backoff_max = max(backoff_base, settings.ocr_queue_retry_max_seconds)

    result_json = dict(job.result_json or {})
    queue_meta = dict(result_json.get("_queue", {})) if isinstance(result_json, dict) else {}
    attempt = int(queue_meta.get("attempt", 0)) + 1
    queue_meta["attempt"] = attempt
    queue_meta["max_attempts"] = max_attempts
    result_json["_queue"] = queue_meta
    job.result_json = result_json
    session.add(job)
    session.commit()
    session.refresh(job)

    try:
        file_bytes = storage.read_bytes(doc.file_path)

        session.exec(
            delete(ExtractedField).where(
                ExtractedField.document_id == doc.id,
                ExtractedField.is_edited == false(),
            )
        )
        session.exec(delete(DocumentPage).where(DocumentPage.document_id == doc.id))

        doc.applied_template_id = None
        doc.applied_template_name = None
        session.add(doc)

        if (doc.mime_type or "").lower() == "application/pdf" or doc.file_path.lower().endswith(
            ".pdf"
        ):
            rendered = render_pdf_to_png_pages(file_bytes)
            doc.pages = len(rendered)

            for page in rendered:
                rel = f"pages/{doc.id}/{page.page_number}.png"
                storage.save_bytes(rel, page.png_bytes)
                session.add(
                    DocumentPage(
                        document_id=doc.id,
                        page_number=page.page_number,
                        image_path=rel,
                        width=page.width,
                        height=page.height,
                        created_at=datetime.now(UTC),
                    )
                )

                fields = run_easyocr_on_image_bytes(page.png_bytes)
                for field in fields:
                    session.add(
                        ExtractedField(
                            document_id=doc.id,
                            page_id=None,
                            page_number=page.page_number,
                            field_name=field.field_name,
                            field_value=field.field_value,
                            confidence=field.confidence,
                            bbox_x=field.bbox_x,
                            bbox_y=field.bbox_y,
                            bbox_width=field.bbox_width,
                            bbox_height=field.bbox_height,
                            is_edited=False,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )
                    extracted_count += 1
        else:
            doc.pages = 1
            fields = run_easyocr_on_image_bytes(file_bytes)
            for field in fields:
                session.add(
                    ExtractedField(
                        document_id=doc.id,
                        page_id=None,
                        page_number=1,
                        field_name=field.field_name,
                        field_value=field.field_value,
                        confidence=field.confidence,
                        bbox_x=field.bbox_x,
                        bbox_y=field.bbox_y,
                        bbox_width=field.bbox_width,
                        bbox_height=field.bbox_height,
                        is_edited=False,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )
                extracted_count += 1

        job.status = "completed"
        job.error_message = None
        job.completed_at = datetime.now(UTC)
        session.add(job)

        doc.status = "scanned" if extracted_count > 0 else "error"
        doc.scanned_at = datetime.now(UTC)
        doc.updated_at = datetime.now(UTC)
        session.add(doc)

        session.commit()
        session.refresh(job)
        return job

    except (StorageError, Exception) as e:
        error_text = str(e)

        if attempt < max_attempts:
            retry_delay = min(backoff_max, backoff_base * (2 ** (attempt - 1)))
            queue_meta["last_error"] = error_text
            queue_meta["next_retry_delay_seconds"] = retry_delay
            result_json["_queue"] = queue_meta

            job.status = "pending"
            job.error_message = f"retry scheduled in {retry_delay}s"
            job.completed_at = None
            job.result_json = result_json
            session.add(job)

            doc.status = "processing"
            doc.updated_at = datetime.now(UTC)
            session.add(doc)

            session.commit()
            session.refresh(job)

            schedule_easyocr_retry(job_id=str(job.id), delay_seconds=retry_delay)
            return job

        queue_meta["last_error"] = error_text
        result_json["_queue"] = queue_meta

        job.status = "error"
        job.error_message = error_text
        job.completed_at = datetime.now(UTC)
        job.result_json = result_json
        session.add(job)

        doc.status = "error"
        doc.updated_at = datetime.now(UTC)
        session.add(doc)

        session.commit()
        session.refresh(job)

        push_easyocr_dlq(
            job_id=str(job.id),
            payload={
                "document_id": str(job.document_id),
                "attempt": attempt,
                "max_attempts": max_attempts,
                "error": error_text,
                "at": datetime.now(UTC).isoformat(),
            },
        )
        return job
