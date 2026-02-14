"""
Document Correction API Schemas

Pydantic models for:
1. Request schemas (input validation)
2. Response schemas (output formatting)
3. Filter/query schemas
4. Batch operation schemas
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ====== REQUEST SCHEMAS ======

class SubmitCorrectionRequest(BaseModel):
    """Request to submit a single field correction."""

    # What to correct
    field_name: str = Field(
        ...,
        min_length=1,
        description="Name of the field to correct"
    )

    # New value
    corrected_value: str | float | int | bool | None = Field(
        ...,
        description="The corrected value"
    )

    # Why
    correction_reason: str = Field(
        ...,
        description="Reason for correction (e.g., 'ocr_error', 'extraction_error')"
    )
    reason_details: Optional[str] = Field(
        None,
        max_length=500,
        description="Additional explanation"
    )

    # Training feedback (optional but encouraged)
    feedback_sentiment: Optional[str] = Field(
        None,
        description="Quality assessment (excellent, good, poor, unusable)"
    )
    feedback_comment: Optional[str] = Field(
        None,
        max_length=1000,
        description="Comments for training dataset"
    )

    # Flags
    is_critical: bool = Field(
        False,
        description="Whether this affects compliance/audit"
    )

    # Verification
    confidence_adjustment: Optional[float] = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="Optional confidence score adjustment"
    )

    model_config = {
        "example": {
            "field_name": "invoice_number",
            "corrected_value": "INV-2024-001",
            "correction_reason": "format_error",
            "reason_details": "Corrected from numeric-only to standard invoice format",
            "feedback_sentiment": "good",
            "feedback_comment": "OCR misread hyphens as spaces",
            "is_critical": False,
            "confidence_adjustment": -0.1
        }
    }


class BatchCorrectionRequest(BaseModel):
    """Request to submit multiple corrections for a document."""

    corrections: list[SubmitCorrectionRequest] = Field(
        ...,
        min_items=1,
        max_items=100,
        description="List of corrections to apply"
    )

    session_notes: Optional[str] = Field(
        None,
        max_length=1000,
        description="Notes about this correction session"
    )

    verify_corrections: bool = Field(
        False,
        description="Whether to validate corrections before applying"
    )

    model_config = {
        "example": {
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
            "session_notes": "Corrected several format issues",
            "verify_corrections": True
        }
    }


class UndoCorrectionRequest(BaseModel):
    """Request to undo a previous correction."""

    correction_id: UUID = Field(
        ...,
        description="ID of the correction to undo"
    )

    reason: str = Field(
        ...,
        max_length=500,
        description="Reason for undoing correction"
    )


class VerifyCorrectionRequest(BaseModel):
    """Request to verify/approve a correction."""

    correction_id: UUID = Field(
        ...,
        description="ID of the correction to verify"
    )

    verified_value: Optional[str | float | int | bool] = Field(
        None,
        description="Verified value (can differ from correction if needed)"
    )

    comment: Optional[str] = Field(
        None,
        max_length=500,
        description="Verification comment"
    )


class ExportTrainingDataRequest(BaseModel):
    """Request to export corrections as training data."""

    document_ids: Optional[list[UUID]] = Field(
        None,
        description="Specific documents (if None, exports all)"
    )

    date_range: Optional[dict[str, datetime]] = Field(
        None,
        description="Filter by correction date: {'start': ..., 'end': ...}"
    )

    correction_reasons: Optional[list[str]] = Field(
        None,
        description="Filter by correction reason"
    )

    min_feedback_sentiment: Optional[str] = Field(
        None,
        description="Minimum sentiment level (good, poor, unusable)"
    )

    include_metadata: bool = Field(
        True,
        description="Include document/field context"
    )

    format: str = Field(
        default="jsonl",
        description="Output format: jsonl, csv, parquet"
    )


# ====== RESPONSE SCHEMAS ======

class CorrectionResponse(BaseModel):
    """Response after submitting a correction."""

    correction_id: UUID = Field(
        ...,
        description="Unique ID of the created correction"
    )

    field_name: str = Field(...)

    # Values
    original_value: str | float | int | bool | None = Field(...)
    corrected_value: str | float | int | bool | None = Field(...)

    # Metadata
    corrected_at: datetime = Field(...)
    corrected_by: str = Field(
        description="User ID who made correction"
    )

    correction_reason: str = Field(...)

    # Status
    is_applied: bool = Field(
        True,
        description="Whether correction is active"
    )

    confidence_adjustment: Optional[float] = Field(None)
    feedback_sentiment: Optional[str] = Field(None)

    model_config = {"from_attributes": True}


class CorrectionHistoryResponse(BaseModel):
    """Response showing full correction history for a field."""

    field_name: str = Field(...)

    # Original extraction
    original_extraction: str | float | int | bool | None = Field(...)
    original_confidence: Optional[float] = Field(...)
    original_source: Optional[str] = Field(...)

    # Current state
    current_value: str | float | int | bool | None = Field(...)
    is_corrected: bool = Field(...)
    correction_count: int = Field(...)

    # Timeline
    corrections: list[CorrectionResponse] = Field(
        default_factory=list,
        description="All corrections in chronological order"
    )

    # Severity
    correction_severity: str = Field(
        description="none, low, medium, high, critical"
    )


class DocumentCorrectionSummaryResponse(BaseModel):
    """Response with document-level correction statistics."""

    document_id: UUID = Field(...)

    # Counts
    total_fields: int = Field(...)
    total_corrected_fields: int = Field(...)
    total_corrections: int = Field(...)
    correction_rate: float = Field(
        ...,
        description="Percentage of fields corrected (0-100)"
    )

    # Breakdown
    corrections_by_reason: dict[str, int] = Field(
        default_factory=dict,
        description="Count of each correction reason"
    )
    corrections_by_type: dict[str, int] = Field(
        default_factory=dict,
        description="Count of each correction type"
    )

    # Severity
    has_critical: bool = Field(...)
    critical_count: int = Field(...)

    # Training metrics
    feedback_provided_count: int = Field(...)
    feedback_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Sentiment distribution (excellent, good, poor, unusable)"
    )

    # Timeline
    first_correction_at: Optional[datetime] = Field(None)
    last_correction_at: Optional[datetime] = Field(None)

    # Requires attention?
    requires_review: bool = Field(
        description="Whether document needs human review"
    )

    model_config = {"from_attributes": True}


class DocumentWithCorrectionsResponse(BaseModel):
    """Response with document data including corrections."""

    document_id: UUID = Field(...)
    document_type: str = Field(...)

    # Field data with corrections applied
    fields: dict[str, Any] = Field(
        description="Field values (already has corrections applied)"
    )

    # Correction info
    correction_summary: DocumentCorrectionSummaryResponse = Field(...)

    # Options
    include_audit_trail: bool = Field(
        False,
        description="Whether full audit trail is included"
    )

    model_config = {"from_attributes": True}


class TrainingDataRecordResponse(BaseModel):
    """Single training data record for ML pipelines."""

    record_id: UUID = Field(...)

    # Context
    document_id: UUID = Field(...)
    document_type: str = Field(...)
    page_number: Optional[int] = Field(None)

    # Extraction
    field_name: str = Field(...)
    extracted_value: str | float | int | bool | None = Field(...)
    extraction_confidence: Optional[float] = Field(...)
    extraction_method: str = Field(...)

    # True value
    corrected_value: str | float | int | bool | None = Field(...)
    correction_reason: str = Field(...)

    # Quality
    was_correct: bool = Field(...)
    feedback_sentiment: Optional[str] = Field(None)

    # Context
    field_characteristics: Optional[dict[str, Any]] = Field(None)
    document_characteristics: Optional[dict[str, Any]] = Field(None)

    model_config = {"from_attributes": True}


# ====== FILTER/QUERY SCHEMAS ======

class CorrectionFilterRequest(BaseModel):
    """Query parameters for filtering corrections."""

    field_names: Optional[list[str]] = Field(
        None,
        description="Filter by specific fields"
    )

    correction_reasons: Optional[list[str]] = Field(
        None,
        description="Filter by correction reason"
    )

    date_from: Optional[datetime] = Field(
        None,
        description="Corrections made after this date"
    )

    date_to: Optional[datetime] = Field(
        None,
        description="Corrections made before this date"
    )

    user_ids: Optional[list[str]] = Field(
        None,
        description="Corrections made by these users"
    )

    with_feedback: Optional[bool] = Field(
        None,
        description="Include only corrections with training feedback"
    )

    is_critical: Optional[bool] = Field(
        None,
        description="Filter by critical flag"
    )

    is_verified: Optional[bool] = Field(
        None,
        description="Filter by verification status"
    )

    limit: int = Field(
        100,
        ge=1,
        le=1000,
        description="Result limit"
    )

    offset: int = Field(
        0,
        ge=0,
        description="Result offset for pagination"
    )


class CorrectionAnalyticsRequest(BaseModel):
    """Request for correction statistics and analytics."""

    group_by: str = Field(
        default="reason",
        description="Group results by: reason, user, field, date"
    )

    aggregate: list[str] = Field(
        default=["count"],
        description="Aggregations: count, avg_confidence, critical_rate"
    )

    date_range: Optional[dict[str, datetime]] = Field(
        None,
        description="Time range for analysis"
    )

    document_types: Optional[list[str]] = Field(
        None,
        description="Limit to document types"
    )


# ====== ERROR RESPONSES ======

class CorrectionErrorResponse(BaseModel):
    """Error response from correction operation."""

    error_code: str = Field(
        description="Error type (e.g., 'field_not_found', 'invalid_value')"
    )

    message: str = Field(
        description="Human-readable error message"
    )

    details: Optional[dict[str, Any]] = Field(
        None,
        description="Additional error context"
    )

    timestamp: datetime = Field(default_factory=datetime.now)


# ====== BATCH OPERATION RESPONSES ======

class BatchCorrectionResponse(BaseModel):
    """Response after batch correction submission."""

    total_submissions: int = Field(...)
    successful: int = Field(...)
    failed: int = Field(...)

    # Results
    results: list[CorrectionResponse | CorrectionErrorResponse] = Field(...)

    # Stats
    total_corrections_applied: int = Field(...)
    session_duration_seconds: float = Field(...)

    model_config = {
        "example": {
            "total_submissions": 5,
            "successful": 4,
            "failed": 1,
            "results": [
                {
                    "correction_id": "550e8400-e29b-41d4-a716-446655440000",
                    "field_name": "invoice_number",
                    "original_value": "NV2024001",
                    "corrected_value": "INV-2024-001",
                    "corrected_at": "2024-01-15T10:30:00Z",
                    "corrected_by": "user@example.com",
                    "correction_reason": "format_error",
                    "is_applied": True
                },
                {
                    "error_code": "field_not_found",
                    "message": "Field 'invoice_date' not found in document"
                }
            ],
            "total_corrections_applied": 4,
            "session_duration_seconds": 12.5
        }
    }


# ====== EXPORT RESPONSES ======

class TrainingDataExportResponse(BaseModel):
    """Response after exporting training data."""

    export_id: UUID = Field(...)
    record_count: int = Field(...)
    file_url: str = Field(
        description="URL to download exported file"
    )

    file_format: str = Field(
        description="Format of exported file"
    )

    file_size_bytes: int = Field(...)

    # Metadata
    created_at: datetime = Field(...)
    expires_at: datetime = Field(
        description="When the temporary file will be deleted"
    )

    # Statistics
    documents_included: int = Field(...)
    correction_types_included: list[str] = Field(...)
    feedback_records: int = Field(
        description="Number of records with training feedback"
    )

    model_config = {
        "example": {
            "export_id": "550e8400-e29b-41d4-a716-446655440000",
            "record_count": 1250,
            "file_url": "https://api.example.com/exports/training-data/550e8400.jsonl",
            "file_format": "jsonl",
            "file_size_bytes": 2500000,
            "created_at": "2024-01-15T10:30:00Z",
            "expires_at": "2024-01-22T10:30:00Z",
            "documents_included": 150,
            "correction_types_included": ["value_change", "format_corrected"],
            "feedback_records": 450
        }
    }


# ====== STATISTICS/ANALYTICS RESPONSES ======

class CorrectionStatisticsResponse(BaseModel):
    """Correction statistics and trends."""

    period: str = Field(
        description="Time period analyzed (e.g., 'last_7_days', 'last_month')"
    )

    # Overall metrics
    total_corrections: int = Field(...)
    total_corrected_fields: int = Field(...)
    unique_documents: int = Field(...)
    unique_users: int = Field(...)

    # Breakdown
    corrections_by_reason: dict[str, int] = Field(...)
    corrections_by_type: dict[str, int] = Field(...)
    corrections_by_user: dict[str, int] = Field(...)

    # Quality metrics
    avg_corrections_per_document: float = Field(...)
    correction_rate_by_field: dict[str, float] = Field(...)

    # Feedback insights
    feedback_coverage: float = Field(
        description="% of corrections with training feedback"
    )
    feedback_sentiment_distribution: dict[str, int] = Field(...)

    # Trending
    daily_corrections: dict[str, int] = Field(
        description="Corrections per day (last 30 days)"
    )

    model_config = {
        "example": {
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
                "user1@example.com": 120,
                "user2@example.com": 85,
                "user3@example.com": 40
            },
            "avg_corrections_per_document": 4.9,
            "feedback_coverage": 0.72,
            "feedback_sentiment_distribution": {
                "excellent": 50,
                "good": 120,
                "poor": 50,
                "unusable": 25
            }
        }
    }
