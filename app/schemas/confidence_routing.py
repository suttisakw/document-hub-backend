"""
Confidence Routing Schemas

Routes documents based on confidence scores:
- confidence > 0.85 → auto approve
- 0.6–0.85 → flag for review
- < 0.6 → force manual review

Apply to: header fields, table rows, whole document
"""

from typing import Any, Dict, List, Optional, Literal
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class RoutingStatus(str, Enum):
    """Document routing status based on confidence."""
    APPROVED = "approved"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


class ConfidenceLevel(str, Enum):
    """Confidence level categories."""
    HIGH = "high"  # > 0.85
    MEDIUM = "medium"  # 0.6-0.85
    LOW = "low"  # < 0.6


class RoutingRule(BaseModel):
    """
    Confidence routing rule.
    
    Defines thresholds and actions for different confidence levels.
    """
    name: str = Field(..., description="Rule name (e.g., 'default', 'strict')")
    high_confidence_threshold: float = Field(
        default=0.85, ge=0.0, le=1.0,
        description="Confidence > this → auto approve"
    )
    medium_confidence_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0,
        description="Confidence between this and high → review required"
    )
    low_confidence_action: Literal["reject", "review"] = Field(
        default="review",
        description="Action for confidence < medium_threshold"
    )
    apply_to_header: bool = Field(
        default=True,
        description="Whether to apply routing to header fields"
    )
    apply_to_rows: bool = Field(
        default=True,
        description="Whether to apply routing to table rows"
    )
    apply_to_document: bool = Field(
        default=True,
        description="Whether to apply routing to whole document score"
    )
    require_all_approved: bool = Field(
        default=False,
        description="Whether all components must be approved for document approval"
    )


class FieldConfidence(BaseModel):
    """Confidence score for a single field."""
    field_name: str
    field_value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel
    routing_status: RoutingStatus
    is_corrected: bool = Field(default=False)
    correction_version: Optional[int] = None
    flags: List[str] = Field(default_factory=list)


class TableRowConfidence(BaseModel):
    """Confidence score for a table row."""
    row_index: int
    row_data: Dict[str, Any]
    average_confidence: float = Field(ge=0.0, le=1.0)
    field_confidences: List[FieldConfidence]
    confidence_level: ConfidenceLevel
    routing_status: RoutingStatus
    min_field_confidence: float = Field(ge=0.0, le=1.0)
    max_field_confidence: float = Field(ge=0.0, le=1.0)
    flags: List[str] = Field(default_factory=list)


class HeaderConfidence(BaseModel):
    """Confidence scores for document header."""
    field_confidences: List[FieldConfidence]
    average_confidence: float = Field(ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel
    routing_status: RoutingStatus
    min_field_confidence: float = Field(ge=0.0, le=1.0)
    max_field_confidence: float = Field(ge=0.0, le=1.0)
    all_fields_approved: bool
    flags: List[str] = Field(default_factory=list)


class DocumentConfidenceScore(BaseModel):
    """Overall document confidence score."""
    document_id: str
    document_type: str
    overall_confidence: float = Field(ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel
    routing_status: RoutingStatus
    header_confidence: Optional[HeaderConfidence] = None
    row_confidences: List[TableRowConfidence] = Field(default_factory=list)
    document_confidence_details: Optional[Dict[str, float]] = None
    average_component_confidence: float = Field(ge=0.0, le=1.0)
    has_low_confidence_fields: bool
    low_confidence_fields: List[str] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


class ConfidenceRoutingRequest(BaseModel):
    """Request to route document based on confidence."""
    document_id: str
    document_type: str
    extracted_fields: Dict[str, Any] = Field(
        ..., description="Header fields with confidence scores"
    )
    field_confidences: Dict[str, float] = Field(
        ..., description="Field name -> confidence score"
    )
    table_rows: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Table rows if applicable"
    )
    row_confidences: Optional[List[Dict[str, float]]] = Field(
        default=None, description="Per-row field confidences"
    )
    document_confidence: float = Field(
        ge=0.0, le=1.0,
        description="Overall document confidence score"
    )
    routing_rule: str = Field(
        default="default",
        description="Name of routing rule to apply"
    )


class ConfidenceRoutingResponse(BaseModel):
    """Response from confidence routing."""
    document_id: str
    routing_status: RoutingStatus
    confidence_score: DocumentConfidenceScore
    routing_reason: str = Field(
        description="Explanation of routing decision"
    )
    requires_attention: bool
    attention_fields: List[str] = Field(default_factory=list)
    attention_rows: List[int] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    processed_at: datetime = Field(default_factory=datetime.utcnow)


class RoutingStatistics(BaseModel):
    """Statistics about document routing."""
    total_documents_routed: int
    approved_count: int
    review_required_count: int
    rejected_count: int
    approval_rate: float = Field(ge=0.0, le=1.0)
    review_rate: float = Field(ge=0.0, le=1.0)
    rejection_rate: float = Field(ge=0.0, le=1.0)
    average_confidence: float = Field(ge=0.0, le=1.0)
    high_confidence_fields: int
    medium_confidence_fields: int
    low_confidence_fields: int
    period: str = Field(default="all_time")


class RoutingHistoryEntry(BaseModel):
    """History entry for document routing."""
    document_id: str
    routing_status: RoutingStatus
    confidence_score: float
    routing_rule_applied: str
    routed_at: datetime
    final_status: Optional[RoutingStatus] = None
    final_status_set_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    review_notes: Optional[str] = None


class BulkRoutingRequest(BaseModel):
    """Request to route multiple documents at once."""
    requests: List[ConfidenceRoutingRequest]
    routing_rule: str = Field(default="default")


class BulkRoutingResponse(BaseModel):
    """Response from bulk routing."""
    batch_id: str
    total_documents: int
    processed_documents: int
    approved: int
    review_required: int
    rejected: int
    results: List[ConfidenceRoutingResponse]
    processed_at: datetime = Field(default_factory=datetime.utcnow)


class RoutingRuleUpdate(BaseModel):
    """Update to routing rule."""
    name: str
    high_confidence_threshold: Optional[float] = None
    medium_confidence_threshold: Optional[float] = None
    low_confidence_action: Optional[str] = None
    apply_to_header: Optional[bool] = None
    apply_to_rows: Optional[bool] = None
    apply_to_document: Optional[bool] = None
    require_all_approved: Optional[bool] = None


class RoutingConfiguration(BaseModel):
    """Complete routing configuration."""
    config_version: str = Field(default="1.0")
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    rules: Dict[str, RoutingRule] = Field(default_factory=dict)
    default_rule: str = Field(default="default")
    enable_auto_approval: bool = Field(default=True)
    enable_auto_rejection: bool = Field(default=False)
    track_history: bool = Field(default=True)
    max_history_days: int = Field(default=90)


class RoutingDecisionLog(BaseModel):
    """Log entry for routing decision."""
    document_id: str
    decision_timestamp: datetime
    confidence_scores: Dict[str, float]
    routing_status: RoutingStatus
    rule_name: str
    decision_details: Dict[str, Any]
    user_override: Optional[bool] = None
    override_by: Optional[str] = None
    override_reason: Optional[str] = None
