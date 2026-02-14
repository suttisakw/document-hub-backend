"""
Pydantic schemas for validation and normalization API.

Request/Response types for validation endpoints with OpenAPI documentation.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, List, Any
from datetime import date, datetime
from enum import Enum


class ValidationStatusSchema(str, Enum):
    """Validation result status."""
    VALID = "valid"
    INVALID = "invalid"
    PARTIAL = "partial"
    WARNING = "warning"
    NEEDS_REVIEW = "needs_review"


class FieldTypeSchema(str, Enum):
    """Field data types."""
    DATE = "date"
    CURRENCY = "currency"
    INTEGER = "integer"
    TAX_ID = "tax_id"
    TEXT = "text"


class FieldResultSchema(BaseModel):
    """Result of validating single field."""
    field_name: str = Field(..., description="Field name")
    original_value: str = Field(..., description="Original extracted value")
    normalized_value: Optional[str] = Field(None, description="Normalized/corrected value")
    status: ValidationStatusSchema = Field(..., description="Validation status")
    is_valid: bool = Field(..., description="Whether field passed validation")
    confidence_adjustment: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Reduction in confidence (0-1.0)"
    )
    needs_review: bool = Field(False, description="Requires manual review")
    error_message: Optional[str] = Field(None, description="Error details if invalid")
    evidence: Dict[str, Any] = Field(
        default_factory=dict,
        description="Validation evidence (format detected, confidence scores, etc.)"
    )


class ValidationRequestSchema(BaseModel):
    """Request to validate and normalize document."""
    document_id: str = Field(..., description="Document ID")
    fields: Dict[str, str] = Field(..., description="Field names and values to validate")
    field_types: Dict[str, FieldTypeSchema] = Field(
        ...,
        description="Field type mapping (e.g., {'invoice_date': 'date', 'tax_id': 'tax_id'})"
    )
    confidences: Optional[Dict[str, float]] = Field(
        None,
        description="Original extraction confidence per field"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "document_id": "doc_12345",
                    "fields": {
                        "invoice_date": "15/02/2567",
                        "vendor_tax_id": "1234567890123",
                        "total_amount": "5,500.00"
                    },
                    "field_types": {
                        "invoice_date": "date",
                        "vendor_tax_id": "tax_id",
                        "total_amount": "currency"
                    },
                    "confidences": {
                        "invoice_date": 0.95,
                        "vendor_tax_id": 0.92,
                        "total_amount": 0.98
                    }
                }
            ]
        }
    }


class BoundingBoxSchema(BaseModel):
    """Bounding box for field location."""
    x_min: float = Field(..., description="Left edge (pixels from left)")
    y_min: float = Field(..., description="Top edge (pixels from top)")
    x_max: float = Field(..., description="Right edge")
    y_max: float = Field(..., description="Bottom edge")


class FieldExtractionSchema(BaseModel):
    """Extracted field with location."""
    name: str = Field(..., description="Field name")
    value: str = Field(..., description="Extracted value")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence")
    field_type: FieldTypeSchema = Field(..., description="Field type")
    bbox: Optional[BoundingBoxSchema] = Field(None, description="Field location in document")


class DocumentValidationSchema(BaseModel):
    """Full document validation result schema."""
    document_id: str = Field(..., description="Document ID")
    overall_valid: bool = Field(..., description="Whether entire document passed validation")
    validation_timestamp: datetime = Field(..., description="When validation occurred")
    
    # Statistics
    total_fields_validated: int = Field(..., ge=0, description="Total fields checked")
    valid_fields_count: int = Field(..., ge=0, description="Passed validation")
    invalid_fields_count: int = Field(..., ge=0, description="Failed validation")
    fields_needing_review: List[str] = Field(
        default_factory=list,
        description="Fields that should be manually reviewed"
    )
    
    # Confidence adjustment
    overall_confidence_adjustment: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Overall confidence reduction (0-1.0)"
    )
    
    # Detailed results
    field_results: List[FieldResultSchema] = Field(
        ...,
        description="Validation result for each field"
    )
    
    # Normalized document
    normalized_document: Dict[str, Any] = Field(
        ...,
        description="Updated document with normalized values"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "document_id": "doc_12345",
                    "overall_valid": True,
                    "validation_timestamp": "2025-02-13T10:30:00",
                    "total_fields_validated": 3,
                    "valid_fields_count": 3,
                    "invalid_fields_count": 0,
                    "fields_needing_review": [],
                    "overall_confidence_adjustment": 0.02,
                    "field_results": [
                        {
                            "field_name": "invoice_date",
                            "original_value": "15/02/2567",
                            "normalized_value": "2024-02-15",
                            "status": "valid",
                            "is_valid": True,
                            "confidence_adjustment": 0.0,
                            "needs_review": False,
                            "error_message": None,
                            "evidence": {
                                "format_detected": "DD/MM/YYYY",
                                "parse_confidence": 0.95
                            }
                        }
                    ],
                    "normalized_document": {
                        "id": "doc_12345",
                        "invoice_date": "2024-02-15",
                        "vendor_tax_id": "1234567890123",
                        "total_amount": "5500.0",
                        "confidence": {
                            "invoice_date": 0.95,
                            "vendor_tax_id": 0.92,
                            "total_amount": 0.98
                        }
                    }
                }
            ]
        }
    }


class BatchValidationRequestSchema(BaseModel):
    """Request to validate multiple documents."""
    documents: List[ValidationRequestSchema] = Field(
        ...,
        description="List of documents to validate",
        max_items=100
    )
    fail_fast: bool = Field(
        False,
        description="Stop on first error or process all"
    )


class BatchValidationResponseSchema(BaseModel):
    """Response with batch validation results."""
    total_documents: int = Field(..., ge=1, description="Total documents processed")
    successful_count: int = Field(..., ge=0, description="Successfully validated")
    failed_count: int = Field(..., ge=0, description="Had validation issues")
    results: List[DocumentValidationSchema] = Field(
        ...,
        description="Validation result for each document"
    )
    processing_time_ms: float = Field(..., ge=0, description="Total processing time")


class ValidationConfigSchema(BaseModel):
    """Configuration for validation behavior."""
    check_thai_dates: bool = Field(True, description="Parse Thai date formats")
    check_thai_digits: bool = Field(True, description="Convert Thai digits")
    check_buddhist_years: bool = Field(True, description="Convert Buddhist year")
    check_currency_formats: bool = Field(True, description="Parse currency values")
    check_tax_id_checksum: bool = Field(True, description="Validate tax ID checksum")
    check_amount_relationships: bool = Field(True, description="Validate amount logic")
    min_confidence_adjustment: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Only reduce confidence if adjustment >= this"
    )
    strict_mode: bool = Field(
        False,
        description="In strict mode, any invalid field fails entire document"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "check_thai_dates": True,
                    "check_thai_digits": True,
                    "check_buddhist_years": True,
                    "check_currency_formats": True,
                    "check_tax_id_checksum": True,
                    "check_amount_relationships": True,
                    "min_confidence_adjustment": 0.05,
                    "strict_mode": False
                }
            ]
        }
    }


class ValidationStatisticsSchema(BaseModel):
    """Statistics on validation operations."""
    total_documents_validated: int = Field(..., ge=0, description="Total docs processed")
    total_fields_validated: int = Field(..., ge=0, description="Total fields checked")
    valid_fields_count: int = Field(..., ge=0, description="Fields that passed")
    invalid_fields_count: int = Field(..., ge=0, description="Fields that failed")
    
    # Confidence adjustments
    mean_confidence_adjustment: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Average confidence reduction"
    )
    median_confidence_adjustment: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Median confidence reduction"
    )
    
    # Field types
    date_fields_validated: int = Field(..., ge=0, description="Date fields checked")
    date_fields_valid: int = Field(..., ge=0, description="Valid dates")
    currency_fields_validated: int = Field(..., ge=0, description="Currency fields checked")
    currency_fields_valid: int = Field(..., ge=0, description="Valid currencies")
    tax_id_fields_validated: int = Field(..., ge=0, description="Tax IDs checked")
    tax_id_fields_valid: int = Field(..., ge=0, description="Valid tax IDs")
    
    # Thai-specific
    thai_dates_found: int = Field(..., ge=0, description="Thai date formats found")
    thai_digits_converted: int = Field(..., ge=0, description="Thai digits converted")
    buddhist_years_converted: int = Field(..., ge=0, description="Buddhist years converted")
    
    validation_timestamp: datetime = Field(..., description="When stats generated")


class FieldValidationExampleSchema(BaseModel):
    """Example field validation result."""
    field_name: str
    field_type: FieldTypeSchema
    original_value: str
    normalized_value: str
    status: ValidationStatusSchema
    confidence_adjustment: float
