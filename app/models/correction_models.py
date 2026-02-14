"""
Document Correction Database Models

SQLModel definitions for:
1. FieldCorrection - stores individual corrections
2. DocumentCorrectionAudit - audit trail

These extend the existing ExtractedField model with correction capabilities.
Maintains backward compatibility through optional fields.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlmodel import Column, Field, ForeignKey, Relationship, SQLModel


# ====== DATABASE MODELS ======

class FieldCorrectionRecord(SQLModel, table=True):
    """
    Database table for individual field corrections.
    
    Links to ExtractedField to track what was corrected.
    Maintains complete audit trail with metadata.
    """

    __tablename__ = "field_corrections"

    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Foreign keys
    extracted_field_id: int = Field(
        foreign_key="extracted_field.id",
        index=True,
        description="Links to the field that was corrected"
    )
    corrected_by_user_id: Optional[int] = Field(
        foreign_key="user.id",
        description="User who made the correction"
    )

    # Correction values
    original_value: Optional[str] = Field(
        default=None,
        description="Original extracted value"
    )
    corrected_value: Optional[str] = Field(
        default=None,
        description="Corrected value"
    )

    # Correction metadata
    correction_type: str = Field(
        default="value_change",
        description="Type of correction (value_change, value_cleared, etc.)"
    )
    correction_reason: str = Field(
        default="other",
        description="Why the correction was made"
    )
    reason_details: Optional[str] = Field(
        default=None,
        description="Extended explanation or context"
    )

    # Confidence adjustment
    confidence_adjustment: Optional[float] = Field(
        default=None,
        description="Adjustment to confidence score"
    )

    # Timestamps
    corrected_at: datetime = Field(
        default_factory=datetime.utcnow,
        index=True,
        description="When the correction was made"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When record was created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow
    )

    # Training feedback
    feedback_sentiment: Optional[str] = Field(
        default=None,
        description="User sentiment about extraction quality"
    )
    feedback_comment: Optional[str] = Field(
        default=None,
        description="User feedback for training"
    )

    # Flags
    is_critical: bool = Field(
        default=False,
        description="Whether this correction affects compliance"
    )
    is_verified: bool = Field(
        default=False,
        description="Whether correction was verified by second user"
    )

    # Relationships
    extracted_field: Optional["ExtractedField"] = Relationship(
        back_populates="corrections"
    )
    corrected_by: Optional["User"] = Relationship(
        back_populates="corrections_made"
    )

    def __str__(self) -> str:
        return (
            f"Correction(field_id={self.extracted_field_id}, "
            f"corrected_at={self.corrected_at})"
        )


class DocumentCorrectionAudit(SQLModel, table=True):
    """
    Audit record for document-level corrections.
    
    Tracks when documents are corrected, by whom, and provides
    summary statistics for analytical queries.
    """

    __tablename__ = "document_correction_audits"

    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Foreign keys
    document_id: int = Field(
        foreign_key="document.id",
        index=True,
        description="Document that was corrected"
    )
    corrected_by_user_id: Optional[int] = Field(
        foreign_key="user.id",
        description="User who initiated corrections"
    )

    # Correction statistics
    total_fields_corrected: int = Field(
        default=0,
        description="Number of fields corrected in this session"
    )
    total_corrections: int = Field(
        default=0,
        description="Total correction records created"
    )

    # Breakdown by type
    corrections_by_reason: Optional[str] = Field(
        default=None,
        description="JSON dict of correction counts by reason"
    )

    # Severity
    has_critical_corrections: bool = Field(
        default=False,
        description="Whether any corrections are marked critical"
    )
    critical_correction_count: int = Field(
        default=0
    )

    # Feedback metrics
    feedback_provided_count: int = Field(
        default=0,
        description="Number of corrections with training feedback"
    )

    # Timestamps
    correction_started_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When correction session started"
    )
    correction_completed_at: Optional[datetime] = Field(
        default=None,
        description="When correction session was completed"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow
    )

    # Notes
    session_notes: Optional[str] = Field(
        default=None,
        description="Notes about the correction session"
    )

    # Relationships
    document: Optional["Document"] = Relationship(
        back_populates="correction_audits"
    )
    corrected_by: Optional["User"] = Relationship(
        back_populates="correction_audits"
    )

    @property
    def duration_minutes(self) -> Optional[float]:
        """Calculate how long the correction session took."""
        if not self.correction_completed_at:
            return None
        delta = self.correction_completed_at - self.correction_started_at
        return delta.total_seconds() / 60

    def __str__(self) -> str:
        return (
            f"CorrectionAudit(doc_id={self.document_id}, "
            f"corrections={self.total_corrections})"
        )


# ====== EXTENSION FIELDS IN EXISTING MODELS ======

# To be added to ExtractedField model (existing):
#   is_corrected: bool = Field(default=False)
#   - Whether this field has any corrections
#   - Enables quick filtering: SELECT * FROM extracted_field WHERE is_corrected=True
#
#   correction_version: Optional[int] = Field(default=None)
#   - Version number of correction (0=extracted, 1+=corrected)
#   - Allows tracking if field was corrected multiple times
#
#   Relationship:
#   corrections: List[FieldCorrectionRecord] = Relationship(
#       back_populates="extracted_field",
#       cascade_delete=True
#   )

# To be added to Document model (existing):
#   has_corrections: bool = Field(default=False, index=True)
#   - Whether document has any corrections
#   - Enables fast filtering for reporting/analytics
#
#   correction_status: str = Field(
#       default="pending",
#       description="Status: pending, in_progress, completed, verified"
#   )
#   - Tracks workflow of correction process
#
#   Relationships:
#   correction_audits: List[DocumentCorrectionAudit] = Relationship(
#       back_populates="document",
#       cascade_delete=True
#   )

# To be added to User model (existing):
#   Relationships:
#   corrections_made: List[FieldCorrectionRecord] = Relationship(
#       back_populates="corrected_by"
#   )
#   correction_audits: List[DocumentCorrectionAudit] = Relationship(
#       back_populates="corrected_by"
#   )


# ====== BACKUP OF CORRECTION DATA ======

class CorrectionSnapshot(SQLModel, table=True):
    """
    Snapshot of entire document state at time of correction.
    
    Useful for:
    - Recovering previous states
    - Understanding change impact
    - Training data preservation
    - Compliance/audit trail
    """

    __tablename__ = "correction_snapshots"

    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Reference
    document_id: int = Field(
        foreign_key="document.id",
        index=True
    )
    correction_audit_id: Optional[int] = Field(
        foreign_key="document_correction_audits.id"
    )

    # Snapshot data
    snapshot_data: str = Field(
        description="JSON dump of document state before corrections"
    )
    corrected_data: str = Field(
        description="JSON dump of document state after corrections"
    )

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    retention_until: datetime = Field(
        description="When this snapshot can be deleted for storage optimization"
    )

    # Relationships
    document: Optional["Document"] = Relationship()


# ====== TRAINING DATA EXPORT ======

class CorrectionTrainingDataRecord(SQLModel, table=True):
    """
    Pre-processed training record exported for ML pipelines.
    
    Denormalized record containing:
    - Extraction info
    - Correction info
    - Document context
    - Field context
    
    Optimized for direct consumption by training loops.
    """

    __tablename__ = "correction_training_data"

    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)

    # References
    field_correction_id: int = Field(
        foreign_key="field_corrections.id",
        index=True
    )
    document_id: int = Field(
        foreign_key="document.id",
        index=True
    )

    # Extraction context
    field_name: str = Field(index=True)
    extracted_value: Optional[str] = Field(default=None)
    extraction_confidence: Optional[float] = Field(default=None)
    extraction_method: str = Field(default="ocr")

    # Correction context
    corrected_value: Optional[str] = Field(default=None)
    correction_type: str = Field()
    correction_reason: str = Field()

    # Quality metadata
    was_correct: bool = Field(
        description="whether extraction was correct"
    )
    feedback_sentiment: Optional[str] = Field(default=None)

    # Document context
    document_type: str = Field(index=True)
    page_number: Optional[int] = Field(default=None)

    # Serialized context (for flexibility)
    field_characteristics: Optional[str] = Field(
        default=None,
        description="JSON serialized field bbox, font, etc."
    )
    document_characteristics: Optional[str] = Field(
        default=None,
        description="JSON serialized document properties"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    # Training pipeline status
    exported: bool = Field(default=False, index=True)
    export_version: Optional[str] = Field(
        default=None,
        description="Training dataset version exported to"
    )

