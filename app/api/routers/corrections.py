"""
Document Correction API Endpoints

REST API for:
1. Submitting corrections
2. Viewing correction history
3. Exporting training data
4. Correction analytics
5. Batch operations
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from uuid import UUID

from app.api.deps import get_db
from app.services.correction_service import CorrectionService
from app.schemas.correction_api import (
    BatchCorrectionRequest,
    BatchCorrectionResponse,
    CorrectionErrorResponse,
    CorrectionFilterRequest,
    CorrectionHistoryResponse,
    CorrectionResponse,
    CorrectionStatisticsResponse,
    DocumentCorrectionSummaryResponse,
    ExportTrainingDataRequest,
    SubmitCorrectionRequest,
    TrainingDataExportResponse,
)

router = APIRouter(prefix="/documents", tags=["corrections"])


# ====== SINGLE CORRECTION ======

@router.post(
    "/{document_id}/corrections",
    response_model=CorrectionResponse,
    summary="Submit a field correction",
    responses={
        200: {"description": "Correction applied successfully"},
        404: {"description": "Document or field not found"},
        422: {"description": "Invalid correction data"},
    },
)
async def submit_correction(
    document_id: int,
    request: SubmitCorrectionRequest,
    db=Depends(get_db),
) -> CorrectionResponse:
    """
    Submit a correction for a field in a document.

    The corrected value will override the extracted value in:
    - API responses
    - Document storage
    - Downstream processing

    The original extracted value is preserved for:
    - Audit trail
    - Training data generation
    - Compliance reporting

    **Request Body:**
    ```json
    {
      "field_name": "invoice_number",
      "corrected_value": "INV-2024-001",
      "correction_reason": "format_error",
      "reason_details": "OCR output was numeric only",
      "feedback_sentiment": "good",
      "feedback_comment": "For training: OCR misread hyphens",
      "is_critical": false,
      "confidence_adjustment": -0.1
    }
    ```

    **Returns:**
    - `correction_id`: Unique ID for this correction (for audit trail)
    - `field_name`: The field corrected
    - `original_value`: Previous extracted value
    - `corrected_value`: New value applied
    - `corrected_at`: Timestamp of correction
    - `is_applied`: Whether correction is active

    **Training Support:**
    - Include `feedback_sentiment` + `feedback_comment` to tag for training
    - Use `correction_reason` to categorize errors (ocr_error, extraction_error, etc.)
    - Data will be automatically exported for model improvement
    """
    service = CorrectionService(db)

    try:
        response = service.apply_correction(
            document_id=document_id,
            extracted_field_id=None,  # Find by name
            request=request,
        )
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


# ====== BATCH CORRECTIONS ======

@router.post(
    "/{document_id}/corrections/batch",
    response_model=BatchCorrectionResponse,
    summary="Submit multiple corrections for a document",
    responses={
        200: {"description": "Batch submitted (check results for individual statuses)"},
        404: {"description": "Document not found"},
        422: {"description": "Invalid batch request"},
    },
)
async def submit_batch_corrections(
    document_id: int,
    request: BatchCorrectionRequest,
    db=Depends(get_db),
) -> BatchCorrectionResponse:
    """
    Submit multiple corrections for a document in a single operation.

    Useful for:
    - Correcting multiple fields from a review session
    - Bulk import of manual corrections
    - Coordinated updates to related fields

    **Request Body:**
    ```json
    {
      "corrections": [
        {
          "field_name": "invoice_number",
          "corrected_value": "INV-2024-001",
          "correction_reason": "format_error"
        },
        {
          "field_name": "total_amount",
          "corrected_value": 1500.50,
          "correction_reason": "extraction_error",
          "feedback_sentiment": "good"
        }
      ],
      "session_notes": "Reviewed and corrected 2 fields",
      "verify_corrections": true
    }
    ```

    **Returns:**
    - Summary with success/failure counts
    - Individual results for each correction
    - Session duration and statistics

    **Note:**
    - Corrections are applied independently (one failure doesn't block others)
    - Check `results` array for per-field status
    - Entire batch is tracked in audit trail
    """
    service = CorrectionService(db)

    try:
        response = service.apply_batch_corrections(
            document_id=document_id,
            requests=request.corrections,
            session_notes=request.session_notes,
        )
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


# ====== CORRECTION HISTORY ======

@router.get(
    "/{document_id}/corrections/{field_name}",
    response_model=CorrectionHistoryResponse,
    summary="Get correction history for a field",
    responses={
        200: {"description": "Complete correction history"},
        404: {"description": "Document or field not found"},
    },
)
async def get_field_correction_history(
    document_id: int,
    field_name: str,
    db=Depends(get_db),
) -> CorrectionHistoryResponse:
    """
    Retrieve complete correction history for a specific field.

    Shows:
    - Original extracted value
    - All corrections applied (in chronological order)
    - Current effective value (original or latest correction)
    - Correction severity assessment

    **Returns:**
    - `original_extraction`: Original OCR/extracted value
    - `corrections`: Array of all corrections (* newest last)
    - `current_value`: Value after all corrections applied
    - `correction_severity`: Assessment (none, low, medium, high, critical)

    **Usage:**
    ```bash
    GET /documents/123/corrections/invoice_number
    ```

    **Returns:**
    ```json
    {
      "field_name": "invoice_number",
      "original_extraction": "NV2024001",
      "current_value": "INV-2024-001",
      "is_corrected": true,
      "correction_count": 1,
      "correction_severity": "medium",
      "corrections": [
        {
          "correction_id": "550e8400-e29b-...",
          "original_value": "NV2024001",
          "corrected_value": "INV-2024-001",
          "corrected_at": "2024-01-15T10:30:00Z",
          "correction_reason": "format_error"
        }
      ]
    }
    ```

    **API Notes:**
    - Use for detailed audit of field changes
    - Training data includes all corrections in sequence
    - Original value is preserved (never overwritten)
    """
    service = CorrectionService(db)

    try:
        response = service.get_field_correction_history(
            document_id=document_id,
            field_name=field_name,
        )
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ====== DOCUMENT CORRECTION SUMMARY ======

@router.get(
    "/{document_id}/corrections/summary",
    response_model=DocumentCorrectionSummaryResponse,
    summary="Get correction summary for a document",
    responses={
        200: {"description": "Document-level correction statistics"},
        404: {"description": "Document not found"},
    },
)
async def get_document_correction_summary(
    document_id: int,
    db=Depends(get_db),
) -> DocumentCorrectionSummaryResponse:
    """
    Get aggregated correction statistics for an entire document.

    Provides:
    - Total corrections count
    - Breakdown by type and reason
    - Critical corrections flagging
    - Training feedback metrics
    - Timeline of corrections

    **Returns:**
    ```json
    {
      "document_id": "550e8400-...",
      "total_fields": 25,
      "total_corrected_fields": 5,
      "total_corrections": 6,
      "correction_rate": 20.0,
      "has_critical": false,
      "critical_count": 0,
      "feedback_provided_count": 4,
      "corrections_by_reason": {
        "ocr_error": 3,
        "format_error": 2,
        "extraction_error": 1
      },
      "first_correction_at": "2024-01-15T10:00:00Z",
      "last_correction_at": "2024-01-15T11:30:00Z",
      "requires_review": false,
      "feedback_distribution": {
        "good": 4
      }
    }
    ```

    **Usage:**
    - Check `correction_rate` to understand quality issues
    - Check `requires_review` flag for workflow
    - Use `corrections_by_reason` to identify systemic OCR/ML issues
    - Track `feedback_provided_count` for training data coverage
    """
    service = CorrectionService(db)

    try:
        response = service.get_document_correction_summary(
            document_id=document_id,
        )
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ====== TRAINING DATA EXPORT ======

@router.post(
    "/corrections/export/training-data",
    response_model=TrainingDataExportResponse,
    summary="Export corrections as training data",
    responses={
        200: {"description": "Training data export created"},
        422: {"description": "Invalid export parameters"},
    },
)
async def export_training_data(
    request: ExportTrainingDataRequest,
    db=Depends(get_db),
) -> TrainingDataExportResponse:
    """
    Export corrections as training records for ML improvement.

    Creates a dataset containing:
    - Original extracted values
    - Corrections applied
    - User feedback (sentiment + comments)
    - Document and field context

    **Request:**
    ```json
    {
      "document_ids": ["550e8400-...", "..."],
      "date_range": {
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-01-31T23:59:59Z"
      },
      "correction_reasons": ["ocr_error", "extraction_error"],
      "min_feedback_sentiment": "good",
      "include_metadata": true,
      "format": "jsonl"
    }
    ```

    **Returns:**
    - `export_id`: Unique export reference
    - `file_url`: Download link (expires in 7 days)
    - `record_count`: Number of training records
    - `file_size_bytes`: Size of export
    - `documents_included`: Documents represented
    - `feedback_records`: Records with user feedback

    **Formats Supported:**
    - `jsonl`: JSON Lines (one record per line) - recommended
    - `csv`: Comma-separated values (flattened)
    - `parquet`: Apache Parquet (for data pipelines)

    **Training Data Uses:**
    - Fine-tune field extraction models
    - Identify systematic OCR errors
    - Improve confidence calibration
    - Analyze error patterns by document type

    **Example Output (JSONL):**
    ```json
    {"field_name": "invoice_number", "extracted": "NV2024001", "corrected": "INV-2024-001", "reason": "format_error", "feedback": "good", "document_type": "invoice"}
    {"field_name": "total_amount", "extracted": "1,500", "corrected": 1500.0, "reason": "ocr_error", "feedback": "excellent"}
    ```
    """
    service = CorrectionService(db)

    try:
        response = service.export_training_data(
            document_ids=request.document_ids,
            date_range=(
                {"start": request.date_range["start"], "end": request.date_range["end"]}
                if request.date_range
                else None
            ),
            correction_reasons=request.correction_reasons,
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


# ====== STATISTICS AND ANALYTICS ======

@router.get(
    "/corrections/statistics",
    response_model=CorrectionStatisticsResponse,
    summary="Get correction statistics",
    responses={
        200: {"description": "Correction statistics"},
    },
)
async def get_correction_statistics(
    days: int = Query(7, ge=1, le=365, description="Days to analyze"),
    db=Depends(get_db),
) -> CorrectionStatisticsResponse:
    """
    Get aggregated correction statistics for the given time period.

    Provides insights into:
    - Common error types
    - User correction patterns
    - Training data volume
    - Quality trends

    **Returns:**
    ```json
    {
      "period": "last_7_days",
      "total_corrections": 245,
      "total_corrected_fields": 180,
      "unique_documents": 50,
      "unique_users": 8,
      "corrections_by_reason": {
        "ocr_error": 95,
        "extraction_error": 85,
        "format_error": 40,
        "other": 25
      },
      "corrections_by_user": {
        "alice@example.com": 120,
        "bob@example.com": 85,
        "charlie@example.com": 40
      },
      "avg_corrections_per_document": 4.9,
      "feedback_coverage": 0.72,
      "feedback_sentiment_distribution": {
        "excellent": 50,
        "good": 120,
        "poor": 50,
        "unusable": 25
      },
      "daily_corrections": {
        "2024-01-09": 35,
        "2024-01-10": 42,
        ...
      }
    }
    ```

    **Usage:**
    - Identify most common error types (for model improvement)
    - Track user correction patterns (performance metrics)
    - Monitor training data accumulation
    - Assess OCR/ML quality trends over time

    **Queries:**
    ```bash
    # Last 7 days (default)
    GET /documents/corrections/statistics

    # Last 30 days
    GET /documents/corrections/statistics?days=30

    # Last quarter
    GET /documents/corrections/statistics?days=90
    ```
    """
    service = CorrectionService(db)

    try:
        response = service.get_correction_statistics(days=days)
        return response
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


# ====== CONFIGURATION & INFO ======

@router.get(
    "/corrections/info",
    summary="Get correction system information",
    responses={
        200: {"description": "System info"},
    },
)
async def get_correction_system_info():
    """
    Get information about the correction system.

    Returns:
    - Supported correction reasons
    - Supported feedback sentiments
    - Export formats available
    - Field name constraints

    **Usage:**
    - For UI dropdown population
    - For validation rules
    - For feature discovery
    """
    return {
        "correction_reasons": [
            "extraction_error",
            "ocr_error",
            "wrong_field",
            "typo",
            "ambiguous",
            "missing",
            "format_error",
            "incomplete",
            "validation_failure",
            "confidence_low",
            "other",
        ],
        "feedback_sentiments": [
            "excellent",
            "good",
            "poor",
            "unusable",
        ],
        "export_formats": [
            "jsonl",
            "csv",
            "parquet",
        ],
        "max_batch_size": 100,
        "training_data_enabled": True,
        "version": "1.0.0",
    }
