"""
Document Classification Schemas

Pydantic models for document classification requests and responses.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DocumentClassificationRequest(BaseModel):
    """Request for document classification."""

    ocr_lines: list[str] = Field(
        ..., description="List of OCR-extracted text lines"
    )
    header_text: str | None = Field(
        None, description="Combined header text (optional)"
    )
    keyword_frequency: dict[str, int] | None = Field(
        None, description="Pre-computed keyword frequency counts"
    )
    classifier_type: Literal["keyword", "hybrid"] = Field(
        "hybrid", description="Classification method to use"
    )


class DocumentClassificationResponse(BaseModel):
    """Response with document classification result."""

    document_type: Literal[
        "invoice", "receipt", "purchase_order", "tax_invoice", "unknown"
    ] = Field(..., description="Detected document type")
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score (0.0 to 1.0)"
    )
    matched_keywords: dict[str, list[str]] = Field(
        default_factory=dict, description="Keywords that matched for the detected type"
    )
    evidence: dict = Field(
        default_factory=dict,
        description="Classification evidence and method details",
    )
    raw_scores: dict[str, float] = Field(
        default_factory=dict, description="Scores for all document types"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "document_type": "invoice",
                "confidence_score": 0.92,
                "matched_keywords": {
                    "invoice": ["invoice", "invoice number", "bill"]
                },
                "evidence": {
                    "method": "keyword_high_confidence",
                    "threshold": 0.25,
                },
                "raw_scores": {
                    "invoice": 4.2,
                    "receipt": 0.9,
                    "purchase_order": 1.5,
                    "tax_invoice": 3.8,
                    "unknown": 0.0,
                },
            }
        }


class ClassifierConfigRequest(BaseModel):
    """Configuration for classifier behavior."""

    classifier_type: Literal["keyword", "hybrid"] = Field(
        "hybrid", description="Type of classifier"
    )
    use_ml_fallback: bool = Field(
        False, description="Use ML classifier for low-confidence cases"
    )
    confidence_threshold_low: float = Field(
        0.4, ge=0.0, le=1.0, description="Threshold for ML fallback"
    )
    confidence_threshold_high: float = Field(
        0.8, ge=0.0, le=1.0, description="Threshold for accepting keyword result"
    )


class ClassifierStatisticsResponse(BaseModel):
    """Statistics about classifier performance."""

    total_classifications: int = Field(default=0, description="Total classifications performed")
    accuracy_by_type: dict[str, float] = Field(
        default_factory=dict, description="Accuracy per document type"
    )
    average_confidence: float = Field(
        default=0.0, description="Average confidence across all classifications"
    )
    confidence_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Distribution of confidence scores (e.g., '0.9-1.0': 45)",
    )
    most_common_type: str | None = Field(None, description="Most frequently detected type")
