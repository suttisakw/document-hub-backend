"""
Document Correction & Feedback Schema

Extends Document schema to support:
1. Manual field corrections with history tracking
2. High-fidelity feedback for training data improvement
3. Correction metadata (who, when, why)
4. Override mechanism (corrected values override extraction)
5. Audit trail for compliance and analytics

Design allows future integration with feedback training pipelines
to improve document extraction models.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ====== ENUMS ======

class CorrectionReason(str, Enum):
    """Reason why a field was corrected."""

    EXTRACTION_ERROR = "extraction_error"  # Wrong value extracted
    OCR_ERROR = "ocr_error"  # OCR misread text
    WRONG_FIELD = "wrong_field"  # Extracted from wrong location
    TYPO = "typo"  # User typo during manual entry
    AMBIGUOUS = "ambiguous"  # Value was ambiguous in document
    MISSING = "missing"  # Field was missing from extraction
    FORMAT_ERROR = "format_error"  # Value format was incorrect
    INCOMPLETE = "incomplete"  # Value was truncated
    VALIDATION_FAILURE = "validation_failure"  # Failed validation check
    CONFIDENCE_LOW = "confidence_low"  # Low confidence extraction
    OTHER = "other"  # Other reason


class CorrectionType(str, Enum):
    """Type of correction made."""

    VALUE_CHANGE = "value_change"  # Value itself was changed
    VALUE_CLEARED = "value_cleared"  # Value was cleared/removed
    VALUE_ADDED = "value_added"  # Missing field was added
    CONFIDENCE_ADJUSTED = "confidence_adjusted"  # Confidence was updated
    TYPE_CHANGED = "type_changed"  # Field type was corrected
    FORMAT_CORRECTED = "format_corrected"  # Value format was fixed


class FeedbackSentiment(str, Enum):
    """User sentiment about extraction quality for training."""

    EXCELLENT = "excellent"  # Extraction was correct and complete
    GOOD = "good"  # Minor corrections needed
    POOR = "poor"  # Multiple corrections needed
    UNUSABLE = "unusable"  # Value was completely wrong


# ====== CORE CORRECTION CLASSES ======

class FieldCorrection(BaseModel):
    """
    Represents a single correction to a field.
    
    This is the primary correction record, capturing what changed,
    who changed it, and why - for audit trail and training purposes.
    """

    # Correction identifiers
    correction_id: UUID = Field(
        ...,
        description="Unique ID for this correction event"
    )
    field_name: str = Field(
        ...,
        description="Name of the field that was corrected"
    )

    # What was corrected
    original_value: str | float | int | bool | None = Field(
        ...,
        description="Original extracted value before correction"
    )
    corrected_value: str | float | int | bool | None = Field(
        ...,
        description="New value after correction (can be same as original for validation fixes)"
    )
    correction_type: CorrectionType = Field(
        ...,
        description="Type of correction made"
    )

    # Why it was corrected
    correction_reason: CorrectionReason = Field(
        ...,
        description="Primary reason for the correction"
    )
    reason_details: str | None = Field(
        None,
        description="Extended explanation (e.g., 'OCR misread 'S' as '5'')"
    )

    # Who corrected it
    corrected_by: str | UUID = Field(
        ...,
        description="User ID or email who made the correction"
    )
    corrected_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When the correction was made"
    )

    # Confidence adjustment
    confidence_adjustment: float | None = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="Adjustment to field confidence (e.g., -0.2 if low confidence OCR was wrong)"
    )

    # Training feedback
    feedback_sentiment: FeedbackSentiment | None = Field(
        None,
        description="User assessment of extraction quality for training"
    )
    feedback_comment: str | None = Field(
        None,
        description="User comments for training dataset annotation"
    )

    # Additional metadata
    is_critical: bool = Field(
        False,
        description="Whether this correction affects compliance/audit"
    )
    related_corrections: list[UUID] = Field(
        default_factory=list,
        description="IDs of related corrections in same document"
    )

    model_config = {"use_enum_values": True}


class CorrectionHistory(BaseModel):
    """
    Complete history of corrections for a single field.
    
    Maintains audit trail showing:
    - Original extraction
    - All corrections applied
    - Current corrected value
    - Override behavior
    """

    field_name: str = Field(
        ...,
        description="Field name"
    )

    # Original extraction
    original_extraction: str | float | int | bool | None = Field(
        ...,
        description="Original extracted value from OCR"
    )
    original_confidence: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Original extraction confidence"
    )
    original_source: str | None = Field(
        None,
        description="Original extraction source (template, ml, ocr, etc.)"
    )

    # Correction timeline
    corrections: list[FieldCorrection] = Field(
        default_factory=list,
        description="All corrections applied to this field, in chronological order"
    )

    # Current state
    current_value: str | float | int | bool | None = Field(
        None,
        description="Current value after all corrections applied"
    )
    is_corrected: bool = Field(
        False,
        description="Whether any corrections have been applied"
    )
    correction_count: int = Field(
        0,
        description="Number of distinct corrections"
    )

    # Aggregated metadata
    total_corrections_by_user: dict[str, int] = Field(
        default_factory=dict,
        description="Count of corrections per user (for training analytics)"
    )
    last_correction_timestamp: datetime | None = Field(
        None,
        description="When the most recent correction was made"
    )

    @property
    def requires_override(self) -> bool:
        """Check if corrected value should override extraction."""
        return self.is_corrected

    @property
    def feedback_collected(self) -> int:
        """Count of corrections with sentiment feedback for training."""
        return sum(
            1 for c in self.corrections
            if c.feedback_sentiment is not None
        )

    @property
    def correction_severity(self) -> str:
        """Assess severity of corrections (for prioritization)."""
        if not self.corrections:
            return "none"

        critical_count = sum(1 for c in self.corrections if c.is_critical)
        if critical_count > 0:
            return "critical"
        elif self.correction_count > 2:
            return "high"
        elif self.correction_count > 0:
            return "medium"
        return "low"

    def apply_correction(self, correction: FieldCorrection) -> None:
        """
        Apply a new correction to this field.
        
        Args:
            correction: The correction to apply
            
        Updates:
            - Adds to corrections list
            - Updates current_value
            - Updates is_corrected flag
            - Updates statistics
        """
        self.corrections.append(correction)
        self.current_value = correction.corrected_value
        self.is_corrected = True
        self.correction_count = len(self.corrections)
        self.last_correction_timestamp = correction.corrected_timestamp

        # Update user statistics
        user_id = str(correction.corrected_by)
        self.total_corrections_by_user[user_id] = (
            self.total_corrections_by_user.get(user_id, 0) + 1
        )

    def get_latest_correction(self) -> FieldCorrection | None:
        """Get the most recent correction."""
        return self.corrections[-1] if self.corrections else None

    def get_corrections_by_user(self, user_id: str) -> list[FieldCorrection]:
        """Get all corrections made by a specific user."""
        return [
            c for c in self.corrections
            if str(c.corrected_by) == user_id
        ]

    def get_corrections_by_reason(
        self, reason: CorrectionReason
    ) -> list[FieldCorrection]:
        """Get corrections grouped by reason (for analytics)."""
        return [c for c in self.corrections if c.correction_reason == reason]

    def get_training_feedback(self) -> list[FieldCorrection]:
        """Get corrections with training feedback sentiment."""
        return [c for c in self.corrections if c.feedback_sentiment is not None]


class CorrectionFeedback(BaseModel):
    """
    Standalone feedback record for training.
    
    Decoupled from individual corrections, allows bulk feedback
    on extraction quality for training pipeline consumption.
    """

    field_name: str = Field(
        ...,
        description="Field name"
    )
    document_id: UUID = Field(
        ...,
        description="Document ID"
    )

    # Was extraction correct?
    extraction_was_correct: bool = Field(
        ...,
        description="Whether original extraction was accurate"
    )

    # Feedback details
    feedback_sentiment: FeedbackSentiment = Field(
        ...,
        description="User assessment of extraction quality"
    )
    comment: str | None = Field(
        None,
        description="Additional comments for annotation"
    )

    # Training context
    extraction_confidence: float | None = Field(
        None,
        description="Original extraction confidence (for binning)"
    )
    extraction_method: str | None = Field(
        None,
        description="How field was originally extracted"
    )
    document_type: str | None = Field(
        None,
        description="Type of document (invoice, receipt, contract, etc.)"
    )

    # Metadata
    feedback_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When feedback was provided"
    )
    feedback_user: str | UUID = Field(
        ...,
        description="User who provided feedback"
    )

    # Correction reference (if applicable)
    related_correction_id: UUID | None = Field(
        None,
        description="Correction ID if feedback was from correction"
    )


# ====== DOCUMENT-LEVEL CORRECTION TRACKING ======

class DocumentCorrectionSummary(BaseModel):
    """
    Summarized correction information for a document.
    
    Provides document-level correction metrics and status
    without full correction details (use separately).
    """

    document_id: UUID = Field(
        ...,
        description="Document ID"
    )

    # Overall correction status
    total_fields_processed: int = Field(
        0,
        description="Total number of fields in document"
    )
    total_fields_corrected: int = Field(
        0,
        description="How many fields had at least one correction"
    )
    total_corrections_made: int = Field(
        0,
        description="Total number of individual corrections"
    )

    # Severity assessment
    has_critical_corrections: bool = Field(
        False,
        description="Whether any corrections are marked critical"
    )
    critical_correction_count: int = Field(
        0,
        description="Number of critical corrections"
    )

    # Correction breakdown by type
    corrections_by_type: dict[str, int] = Field(
        default_factory=dict,
        description="Count of corrections by type"
    )
    corrections_by_reason: dict[str, int] = Field(
        default_factory=dict,
        description="Count of corrections by reason"
    )

    # Training metrics
    feedback_provided_count: int = Field(
        0,
        description="Number of corrections with training feedback"
    )
    feedback_sentiment_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Distribution of feedback sentiments"
    )

    # Timeline
    correction_timeline: dict[str, int] = Field(
        default_factory=dict,
        description="Corrections per day (for trend analysis)"
    )
    first_correction_timestamp: datetime | None = Field(
        None,
        description="When first correction was made"
    )
    last_correction_timestamp: datetime | None = Field(
        None,
        description="When last correction was made"
    )

    # Correction metadata
    corrected_by_users: list[str] = Field(
        default_factory=list,
        description="List of users who made corrections"
    )

    # Confidence impact
    avg_confidence_adjustment: float | None = Field(
        None,
        description="Average confidence adjustment across corrections"
    )

    def get_correction_rate(self) -> float:
        """Calculate percentage of fields that were corrected."""
        if self.total_fields_processed == 0:
            return 0.0
        return (self.total_fields_corrected / self.total_fields_processed) * 100

    def is_fully_corrected(self) -> bool:
        """Check if all fields have been corrected."""
        return self.total_fields_corrected == self.total_fields_processed

    def requires_review(self) -> bool:
        """Check if document requires human review due to corrections."""
        return (
            self.has_critical_corrections
            or self.total_corrections_made > 5
            or self.get_correction_rate() > 50
        )


# ====== TRAINING DATA SUPPORT ======

class CorrectionTrainingRecord(BaseModel):
    """
    Complete record for training ML models on corrections.
    
    Groups all correction and feedback information needed to:
    1. Understand what went wrong
    2. Improve extraction models
    3. Identify systematic errors
    4. Optimize field detection
    """

    # Document context
    document_id: UUID = Field(...)
    document_type: str = Field(...)
    page_number: int | None = Field(None)

    # Extraction context
    field_name: str = Field(...)
    extracted_value: str | float | int | bool | None = Field(...)
    extraction_confidence: float | None = Field(None)
    extraction_method: str = Field(...)

    # True value (correction)
    corrected_value: str | float | int | bool | None = Field(...)
    correction_reason: str = Field(...)

    # Quality metrics
    was_correct: bool = Field(..., description="True if extraction was correct")
    feedback_sentiment: str | None = Field(None)

    # Contextual information for learning
    document_characteristics: dict[str, Any] = Field(
        default_factory=dict,
        description="Document properties (language, layout, etc.)"
    )
    field_characteristics: dict[str, Any] = Field(
        default_factory=dict,
        description="Field properties (bbox, font, color, etc.)"
    )
    surrounding_context: str | None = Field(
        None,
        description="Surrounding text for contextual understanding"
    )

    # Metadata
    timestamp: datetime = Field(default_factory=datetime.now)


# ====== OVERRIDE MECHANISM ======

class FieldValue(BaseModel):
    """
    Complete field value with override support.
    
    Combines extraction and correction information,
    with logic to use corrected value if available.
    """

    field_name: str = Field(...)
    data_type: str = Field(default="text")

    # Extraction
    extracted_value: str | float | int | bool | None = Field(None)
    extraction_confidence: float | None = Field(None)
    extraction_method: str = Field(default="ocr")

    # Correction (optional)
    correction_history: CorrectionHistory | None = Field(None)

    @property
    def value(self) -> str | float | int | bool | None:
        """
        Get the effective value (corrected if available, else extracted).
        
        This is the value that should be used in:
        - API responses
        - Document storage
        - Downstream processing
        """
        if self.correction_history and self.correction_history.is_corrected:
            return self.correction_history.current_value
        return self.extracted_value

    @property
    def confidence(self) -> float | None:
        """
        Get effective confidence (adjusted if corrected).
        """
        base_conf = self.extraction_confidence or 0.0

        if self.correction_history and self.correction_history.is_corrected:
            latest = self.correction_history.get_latest_correction()
            if latest and latest.confidence_adjustment is not None:
                return max(0.0, min(1.0, base_conf + latest.confidence_adjustment))

        return self.extraction_confidence

    @property
    def is_correction_applied(self) -> bool:
        """Check if correction has overridden extraction."""
        return (
            self.correction_history is not None
            and self.correction_history.is_corrected
        )

    @property
    def source(self) -> Literal["extracted", "corrected"]:
        """Get source of current value."""
        if self.is_correction_applied:
            return "corrected"
        return "extracted"

    def to_dict(self, include_history: bool = False) -> dict[str, Any]:
        """
        Serialize field value to dictionary.
        
        Args:
            include_history: If True, include full correction history (for audit)
                           If False, omit history (for API responses)
        """
        result = {
            "field_name": self.field_name,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "is_corrected": self.is_correction_applied,
        }

        if include_history and self.correction_history:
            result["correction_history"] = self.correction_history.model_dump()

        return result


# ====== DOCUMENT EXTENSION ======

class DocumentWithCorrections(BaseModel):
    """
    Extended document schema with correction support.
    
    Usage:
        # Create with corrections
        doc = DocumentWithCorrections(
            document_id=...,
            fields=[
                FieldValue(
                    field_name="invoice_number",
                    extracted_value="NV2024001",
                    extraction_confidence=0.92,
                    correction_history=CorrectionHistory(
                        original_extraction="NV2024001",
                        corrections=[
                            FieldCorrection(
                                correction_id=uuid4(),
                                field_name="invoice_number",
                                original_value="NV2024001",
                                corrected_value="INV-2024-001",
                                correction_type=CorrectionType.FORMAT_CORRECTED,
                                correction_reason=CorrectionReason.FORMAT_ERROR,
                                corrected_by="user@example.com",
                                feedback_sentiment=FeedbackSentiment.GOOD
                            )
                        ]
                    )
                )
            ],
            correction_summary=DocumentCorrectionSummary(
                document_id=...,
                total_fields_processed=10,
                total_fields_corrected=1,
                total_corrections_made=1
            )
        )
        
        # Use corrected values (automatically overrides extraction)
        for field in doc.fields:
            print(f"{field.field_name}: {field.value}")  # Uses corrected if available
    """

    # Core identifiers
    document_id: UUID = Field(...)
    document_type: str = Field(...)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    corrected_at: datetime | None = Field(None)

    # Fields with correction support
    fields: list[FieldValue] = Field(default_factory=list)

    # Correction summary (denormalized for quick access)
    correction_summary: DocumentCorrectionSummary | None = Field(None)

    # Raw extraction for reference
    raw_extraction: dict[str, Any] | None = Field(None)

    model_config = {"use_enum_values": True}

    @property
    def get_corrected_fields(self) -> dict[str, Any]:
        """
        Get effective field values (with corrections applied).
        
        Returns:
            Dictionary of field names to corrected values
        """
        return {field.field_name: field.value for field in self.fields}

    @property
    def get_extracted_only(self) -> dict[str, Any]:
        """Get original extracted values (without corrections)."""
        return {field.field_name: field.extracted_value for field in self.fields}

    @property
    def get_audit_trail(self) -> dict[str, list[FieldCorrection]]:
        """
        Get complete audit trail of all corrections.
        
        Useful for compliance and analytics.
        """
        return {
            field.field_name: (
                field.correction_history.corrections
                if field.correction_history
                else []
            )
            for field in self.fields
        }
