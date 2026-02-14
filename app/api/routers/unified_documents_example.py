"""
Sample API Endpoint Implementation for Unified Document Schema

This module demonstrates how to integrate the unified document schema
into existing API endpoints.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.deps import get_current_user, get_session
from app.models import Document, DocumentPage, ExtractedField, OcrJob, User
from app.schemas import UnifiedDocument, UnifiedDocumentResponse
from app.schemas.unified_document_migration import (
    convert_document_to_unified,
    create_table_from_extracted_fields,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/{document_id}/unified", response_model=UnifiedDocumentResponse)
async def get_document_unified_format(
    document_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get document in unified format with structured extraction.
    
    This endpoint returns the document in the new unified schema format,
    which includes:
    - Structured header fields with source attribution
    - Tables with per-cell confidence
    - Original OCR output preserved in raw_ocr
    - Document-level metadata and confidence scores
    
    Example response structure is available in UNIFIED_DOCUMENT_EXAMPLES.md
    """
    # Get document
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Security check: ensure user owns this document
    if doc.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get extracted fields
    stmt = select(ExtractedField).where(ExtractedField.document_id == document_id)
    extracted_fields = list(session.exec(stmt).all())

    # Get pages
    stmt = select(DocumentPage).where(DocumentPage.document_id == document_id)
    pages = list(session.exec(stmt).all())

    # Get raw OCR data from most recent completed job
    stmt = (
        select(OcrJob)
        .where(OcrJob.document_id == document_id)
        .where(OcrJob.status == "completed")
        .order_by(OcrJob.completed_at.desc())
    )
    ocr_job = session.exec(stmt).first()
    raw_ocr = ocr_job.result_json if ocr_job else None

    # Convert to unified format
    unified_doc = convert_document_to_unified(
        doc=doc,
        extracted_fields=extracted_fields,
        pages=pages,
        raw_ocr_data=raw_ocr,
    )

    return unified_doc


@router.get("/{document_id}/unified/with-tables", response_model=UnifiedDocumentResponse)
async def get_document_unified_with_tables(
    document_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get document in unified format with table extraction from line items.
    
    This endpoint demonstrates how to extract tables from ExtractedField records
    that follow a naming pattern (e.g., item_0_description, item_0_quantity).
    
    Use this endpoint when you have line items stored as individual fields
    and want to present them as a structured table in the unified format.
    """
    # Get document
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Security check
    if doc.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get all extracted fields
    stmt = select(ExtractedField).where(ExtractedField.document_id == document_id)
    all_fields = list(session.exec(stmt).all())

    # Separate header fields from line item fields
    header_fields = []
    line_item_fields = []

    for field in all_fields:
        if field.field_name.startswith("item_"):
            line_item_fields.append(field)
        else:
            header_fields.append(field)

    # Get pages
    stmt = select(DocumentPage).where(DocumentPage.document_id == document_id)
    pages = list(session.exec(stmt).all())

    # Get raw OCR data
    stmt = (
        select(OcrJob)
        .where(OcrJob.document_id == document_id)
        .where(OcrJob.status == "completed")
        .order_by(OcrJob.completed_at.desc())
    )
    ocr_job = session.exec(stmt).first()
    raw_ocr = ocr_job.result_json if ocr_job else None

    # Convert to unified format
    unified_doc = convert_document_to_unified(
        doc=doc,
        extracted_fields=header_fields,  # Only header fields
        pages=pages,
        raw_ocr_data=raw_ocr,
    )

    # Extract table from line item fields
    if line_item_fields:
        # Define table columns based on your document type
        # This should be customized based on document type
        columns = ["description", "quantity", "unit_price", "amount"]

        table = create_table_from_extracted_fields(
            fields=line_item_fields,
            table_id="line_items",
            page_number=1,  # Adjust based on actual page location
            columns=columns,
        )

        unified_doc.tables = [table]

    return unified_doc


# Additional helper endpoints


@router.get("/{document_id}/extraction-sources")
async def get_extraction_sources_summary(
    document_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get summary of extraction sources for a document.
    
    Returns counts of fields by extraction source (template, regex, ML, LLM, manual).
    Useful for quality tracking and debugging extraction accuracy.
    """
    doc = session.get(Document, document_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    stmt = select(ExtractedField).where(ExtractedField.document_id == document_id)
    fields = list(session.exec(stmt).all())

    # Count by source
    sources = {
        "manual": sum(1 for f in fields if f.is_edited),
        "ocr": sum(1 for f in fields if not f.is_edited),
        # Add other sources when we implement template/regex/ML/LLM extraction
    }

    # Calculate average confidence
    confidences = [f.confidence for f in fields if f.confidence is not None]
    avg_confidence = sum(confidences) / len(confidences) if confidences else None

    return {
        "document_id": document_id,
        "total_fields": len(fields),
        "sources": sources,
        "average_confidence": avg_confidence,
        "has_manual_edits": sources["manual"] > 0,
    }


@router.get("/{document_id}/confidence-report")
async def get_confidence_report(
    document_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed confidence report for a document.
    
    Returns confidence scores grouped by:
    - Overall document confidence
    - Per-page confidence
    - Per-field confidence distribution
    - Low confidence fields (< 0.8)
    """
    doc = session.get(Document, document_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    stmt = select(ExtractedField).where(ExtractedField.document_id == document_id)
    fields = list(session.exec(stmt).all())

    # Calculate per-page confidence
    page_confidence = {}
    for field in fields:
        if field.page_number and field.confidence is not None:
            if field.page_number not in page_confidence:
                page_confidence[field.page_number] = []
            page_confidence[field.page_number].append(field.confidence)

    page_avg = {
        page: sum(scores) / len(scores) if scores else None
        for page, scores in page_confidence.items()
    }

    # Find low confidence fields
    low_confidence_fields = [
        {
            "field_name": f.field_name,
            "field_value": f.field_value,
            "confidence": f.confidence,
            "page_number": f.page_number,
        }
        for f in fields
        if f.confidence is not None and f.confidence < 0.8
    ]

    # Confidence distribution
    all_confidences = [f.confidence for f in fields if f.confidence is not None]
    distribution = {
        "high (>= 0.9)": sum(1 for c in all_confidences if c >= 0.9),
        "medium (0.7-0.9)": sum(1 for c in all_confidences if 0.7 <= c < 0.9),
        "low (< 0.7)": sum(1 for c in all_confidences if c < 0.7),
    }

    return {
        "document_id": document_id,
        "overall_confidence": doc.confidence,
        "page_confidence": page_avg,
        "confidence_distribution": distribution,
        "low_confidence_fields": low_confidence_fields,
        "total_fields": len(fields),
        "fields_with_confidence": len(all_confidences),
    }


# Note: To integrate these endpoints into your application:
# 1. Import this router in your main.py or API router setup
# 2. Register it with your FastAPI app:
#
#    from app.api.routers import unified_documents
#    app.include_router(unified_documents.router)
#
# 3. Access the endpoints at:
#    GET /api/documents/{document_id}/unified
#    GET /api/documents/{document_id}/unified/with-tables
#    GET /api/documents/{document_id}/extraction-sources
#    GET /api/documents/{document_id}/confidence-report
