from datetime import UTC, datetime
from uuid import UUID
import json
import logging
import asyncio
from sqlmodel import Session, select

from app.core.config import settings
from app.models import Document, OcrJob # Reusing OcrJob for now, maybe rename to TaskJob later
from app.services.extraction_service import ExtractionService
from app.services.resource_monitor import get_resource_monitor
from app.services.redis_queue import (
    publish_job,
    pop_job,
    schedule_easyocr_retry,
    push_easyocr_dlq,
)

logger = logging.getLogger(__name__)

def enqueue_extraction_job(*, session: Session, document_id: UUID) -> OcrJob:
    """Entry point: Start orchestration."""
    job = OcrJob(
        document_id=document_id,
        provider="easyocr",  # Add required provider field
        current_step="orchestrate",
        status="pending",
        requested_at=datetime.utcnow(),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    
    publish_job(str(job.id), "orchestration")
    return job

async def process_extraction_job(*, session: Session, job_id: UUID) -> OcrJob:
    job = session.exec(select(OcrJob).where(OcrJob.id == job_id)).first()
    if not job or job.status in {"completed", "error"}:
        return job
    
    # Check resource limits before starting
    monitor = get_resource_monitor()
    if not monitor.can_start_job():
        logger.warning(f"Cannot start job {job_id}: resource limits exceeded")
        # Requeue job for later
        schedule_easyocr_retry(str(job_id), delay_seconds=30)
        return job

    job.status = "running"
    session.add(job)
    session.commit()
    
    # Start tracking job for timeout
    monitor.start_job(str(job_id))

    try:
        if job.current_step == "orchestrate":
            await _handle_orchestrate(session, job)
        elif job.current_step == "render":
            await _handle_render(session, job)
        elif job.current_step == "ocr":
            await _handle_ocr(session, job)
        elif job.current_step == "extract":
            await _handle_extract(session, job)
        
        # Check if job timed out during processing
        if monitor.check_job_timeout(str(job_id)):
            raise TimeoutError(f"Job {job_id} exceeded timeout")
            
    except Exception as e:
        await _handle_failure(session, job, e)
    finally:
        # End job tracking
        monitor.end_job(str(job_id))

    return job

async def _handle_orchestrate(session: Session, job: OcrJob):
    doc = session.exec(select(Document).where(Document.id == job.document_id)).first()
    doc.status = "processing"
    session.add(doc)
    
    # Decide next step
    job.current_step = "render"
    job.status = "pending"
    session.add(job)
    session.commit()
    publish_job(str(job.id), "render")

async def _handle_render(session: Session, job: OcrJob):
    from app.services.extraction.preprocessor import DocumentPreProcessor
    doc = session.get(Document, job.document_id)
    preprocessor = DocumentPreProcessor(session)
    await preprocessor.prepare_pages(doc)
    
    job.current_step = "ocr"
    job.status = "pending"
    session.add(job)
    session.commit()
    publish_job(str(job.id), "ocr")

async def _handle_ocr(session: Session, job: OcrJob):
    from app.services.extraction.ocr_engine import OcrEngine
    from app.models import DocumentPage
    pages = session.exec(select(DocumentPage).where(DocumentPage.document_id == job.document_id)).all()
    
    ocr_engine = OcrEngine()
    result = await ocr_engine.run_ocr(pages)
    
    # Store result in job temporarily
    job.result_data = {
        "full_text": result.full_text,
        "pages_raw": result.pages_raw
    }
    job.current_step = "extract"
    job.status = "pending"
    session.add(job)
    session.commit()
    publish_job(str(job.id), "extraction")

async def _handle_extract(session: Session, job: OcrJob):
    from app.services.extraction_service import ExtractionService
    service = ExtractionService(session)
    # We need to bridge the old process_document slightly or refactor it to accept OCR results
    # For Phase 4.2, we'll let it handle the rest of the pipeline
    await service.process_document(job.document_id, ocr_result=job.result_data)
    
    job.status = "completed"
    job.completed_at = datetime.utcnow()
    session.add(job)
    session.commit()

async def _handle_failure(session: Session, job: OcrJob, e: Exception):
    logger.exception(f"Job {job.id} step {job.current_step} failed: {e}")
    max_retries = 3
    if job.retry_count < max_retries:
        job.retry_count += 1
        job.status = "pending"
        job.error_message = str(e)
        session.add(job)
        session.commit()
        
        delay = (2 ** job.retry_count) * 10
        # Re-publish to the CURRENT queue for retry
        queue_map = {"orchestrate": "orchestration", "render": "render", "ocr": "ocr", "extract": "extraction"}
        q = queue_map.get(job.current_step, "orchestration")
        # Reuse schedule_easyocr_retry but maybe make it generic? 
        # For now, let's just publish back with a delay if we had a proper delay queue.
        # We'll just requeue for now or use the existing delayed queue mechanism.
        schedule_easyocr_retry(str(job.id), delay_seconds=delay)
    else:
        job.status = "error"
        job.error_message = f"Max retries reached: {str(e)}"
        session.add(job)
        doc = session.get(Document, job.document_id)
        if doc: doc.status = "error"
        session.commit()
        push_easyocr_dlq(job_id=str(job.id), payload={"error": str(e), "step": job.current_step})
