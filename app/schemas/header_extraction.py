"""
Pydantic schemas for header extraction API.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from enum import Enum
from datetime import datetime
from app.schemas.confidence import ConfidenceScore, ExtractedSource, ExtractionStage


# ====== ENUMS ======

class InvoiceFieldTypeSchema(str, Enum):
    """Invoice field types (API version)."""
    INVOICE_NUMBER = "invoice_number"
    INVOICE_DATE = "invoice_date"
    VENDOR_NAME = "vendor_name"
    TAX_ID = "tax_id"
    SUBTOTAL = "subtotal"
    VAT = "vat"
    TOTAL_AMOUNT = "total_amount"


# These are now imported from confidence.py but kept as aliases for backward compatibility if needed
InvoiceFieldTypeSchema = InvoiceFieldTypeSchema # placeholder to show where we are
ExtractionSourceSchema = ExtractedSource
ExtractionStageSchema = ExtractionStage


# ====== BOUNDING BOX ======

class BoundingBoxSchema(BaseModel):
    """Spatial coordinate information."""
    x_min: float = Field(..., description="Left coordinate")
    y_min: float = Field(..., description="Top coordinate")
    x_max: float = Field(..., description="Right coordinate")
    y_max: float = Field(..., description="Bottom coordinate")

    class Config:
        json_schema_extra = {
            "example": {
                "x_min": 100.0,
                "y_min": 50.0,
                "x_max": 450.0,
                "y_max": 100.0
            }
        }


# ====== EXTRACTION REQUEST ======

class HeaderExtractionRequest(BaseModel):
    """Request for header extraction."""
    ocr_lines: List[str] = Field(
        ...,
        description="OCR text lines from invoice",
        example=["INVOICE", "Invoice Number: INV-2024-001", "Date: 2024-02-13"]
    )
    field_types: Optional[List[InvoiceFieldTypeSchema]] = Field(
        None,
        description="Specific fields to extract (all if omitted)",
        example=["invoice_number", "vendor_name", "total_amount"]
    )
    ocr_confidence_scores: Optional[Dict[int, float]] = Field(
        None,
        description="OCR confidence per line index"
    )
    enable_llm: bool = Field(
        False,
        description="Enable LLM fallback for low-confidence fields"
    )
    confidence_threshold_for_llm: float = Field(
        0.5,
        description="Invoke LLM if confidence below threshold",
        ge=0.0,
        le=1.0
    )

    class Config:
        json_schema_extra = {
            "example": {
                "ocr_lines": [
                    "ACME Corporation",
                    "INVOICE",
                    "Invoice Number: INV-2024-001",
                    "Date: 02/13/2024",
                    "Tax ID: 12-3456789",
                    "Subtotal: 1000.00",
                    "VAT (20%): 200.00",
                    "Total: 1200.00"
                ],
                "field_types": ["invoice_number", "invoice_date", "vendor_name", "tax_id", "subtotal", "vat", "total_amount"],
                "enable_llm": False
            }
        }


# ====== EXTRACTION RESULT ======

class ExtractionResultSchema(BaseModel):
    """Single field extraction result."""
    field_type: InvoiceFieldTypeSchema
    value: Optional[str] = Field(
        ...,
        description="Extracted field value"
    )
    confidence: float = Field(
        ...,
        description="Confidence score (0.0-1.0)",
        ge=0.0,
        le=1.0
    )
    source: ExtractionSourceSchema = Field(
        ...,
        description="Source of extraction (template, regex, ml, llm)"
    )
    stage: ExtractionStageSchema = Field(
        ...,
        description="Pipeline stage that performed extraction"
    )
    bbox: Optional[BoundingBoxSchema] = Field(
        None,
        description="Bounding box of extracted value in document"
    )
    raw_text: Optional[str] = Field(
        None,
        description="Full OCR text containing the value"
    )
    evidence: Dict[str, Any] = Field(
        default_factory=dict,
        description="Scoring breakdown and evidence"
    )
    confidence_details: Optional[ConfidenceScore] = Field(
        None,
        description="Detailed unified confidence scoring information"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "field_type": "invoice_number",
                "value": "INV-2024-001",
                "confidence": 0.95,
                "source": "template",
                "stage": "stage_1_template",
                "bbox": {
                    "x_min": 200.0,
                    "y_min": 150.0,
                    "x_max": 400.0,
                    "y_max": 180.0
                },
                "raw_text": "Invoice Number: INV-2024-001",
                "evidence": {
                    "pattern": "(?:invoice\\s+(?:number|no\\.?|#))\\s*[:]:([A-Z0-9\\-/]+)",
                    "template_confidence": 0.95
                }
            }
        }


# ====== EXTRACTION RESPONSE ======

class HeaderExtractionResponse(BaseModel):
    """Complete extraction response."""
    fields: Dict[InvoiceFieldTypeSchema, ExtractionResultSchema] = Field(
        ...,
        description="Extracted fields with results"
    )
    overall_confidence: float = Field(
        ...,
        description="Overall extraction confidence (average)",
        ge=0.0,
        le=1.0
    )
    extracted_at_stage: ExtractionStageSchema = Field(
        ...,
        description="Final stage that completed extraction"
    )
    processing_time_ms: float = Field(
        ...,
        description="Total processing time in milliseconds"
    )
    high_confidence_fields: Optional[Dict[InvoiceFieldTypeSchema, ExtractionResultSchema]] = Field(
        None,
        description="Fields with confidence >= 0.7"
    )
    all_results: Optional[List[ExtractionResultSchema]] = Field(
        None,
        description="All extraction attempts from all stages"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "fields": {
                    "invoice_number": {
                        "field_type": "invoice_number",
                        "value": "INV-2024-001",
                        "confidence": 0.95,
                        "source": "template",
                        "stage": "stage_1_template",
                        "evidence": {
                            "pattern": ".*",
                            "template_confidence": 0.95
                        }
                    },
                    "total_amount": {
                        "field_type": "total_amount",
                        "value": "1200.00",
                        "confidence": 0.88,
                        "source": "regex",
                        "stage": "stage_2_regex",
                        "evidence": {
                            "anchor": "total",
                            "regex_score": 0.9,
                            "proximity_score": 0.98
                        }
                    }
                },
                "overall_confidence": 0.915,
                "extracted_at_stage": "stage_2_regex",
                "processing_time_ms": 12.5
            }
        }


# ====== BATCH EXTRACTION ======

class BatchExtractionRequest(BaseModel):
    """Request for batch header extraction."""
    documents: List[HeaderExtractionRequest] = Field(
        ...,
        description="Multiple documents to extract",
        max_items=100
    )
    enable_llm: bool = Field(False, description="Enable LLM for all documents")

    class Config:
        json_schema_extra = {
            "example": {
                "documents": [
                    {
                        "ocr_lines": ["INVOICE", "INV-001"]
                    },
                    {
                        "ocr_lines": ["RECEIPT", "RCP-001"]
                    }
                ]
            }
        }


class BatchExtractionResponse(BaseModel):
    """Response for batch extraction."""
    results: List[HeaderExtractionResponse] = Field(
        ...,
        description="Results for each document"
    )
    total_processed: int
    total_time_ms: float
    success_count: int = Field(
        ...,
        description="Documents with >= 1 field extracted"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "results": [],
                "total_processed": 2,
                "total_time_ms": 45.3,
                "success_count": 2
            }
        }


# ====== CONFIGURATION ======

class ExtractionEngineConfig(BaseModel):
    """Engine configuration."""
    enable_template: bool = Field(True, description="Enable template extractor")
    enable_regex: bool = Field(True, description="Enable regex extractor")
    enable_ml: bool = Field(False, description="Enable ML extractor")
    enable_llm: bool = Field(False, description="Enable LLM extractor")
    confidence_threshold_template: float = Field(
        0.5,
        description="Minimum template confidence",
        ge=0.0,
        le=1.0
    )
    confidence_threshold_regex: float = Field(
        0.4,
        description="Minimum regex confidence",
        ge=0.0,
        le=1.0
    )
    confidence_threshold_llm: float = Field(
        0.5,
        description="Invoke LLM if confidence below threshold",
        ge=0.0,
        le=1.0
    )
    llm_api_key: Optional[str] = Field(None, description="API key for LLM service")

    class Config:
        json_schema_extra = {
            "example": {
                "enable_template": True,
                "enable_regex": True,
                "enable_ml": False,
                "enable_llm": False,
                "confidence_threshold_template": 0.5,
                "confidence_threshold_regex": 0.4,
                "confidence_threshold_llm": 0.5
            }
        }


# ====== STATISTICS ======

class ExtractionStatisticsResponse(BaseModel):
    """Extraction statistics."""
    total_requests: int = Field(..., description="Total extraction requests")
    total_fields_extracted: int
    average_confidence: float = Field(..., ge=0.0, le=1.0)
    average_processing_time_ms: float
    field_success_rate: Dict[InvoiceFieldTypeSchema, float] = Field(
        ...,
        description="Success rate (0.0-1.0) per field type"
    )
    stage_distribution: Dict[ExtractionStageSchema, int] = Field(
        ...,
        description="Count of documents completed at each stage"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "total_requests": 100,
                "total_fields_extracted": 650,
                "average_confidence": 0.82,
                "average_processing_time_ms": 15.5,
                "field_success_rate": {
                    "invoice_number": 0.98,
                    "vendor_name": 0.92,
                    "total_amount": 0.89
                },
                "stage_distribution": {
                    "stage_1_template": 65,
                    "stage_2_regex": 30,
                    "stage_3_ml": 4,
                    "stage_4_llm": 1
                }
            }
        }


# ====== FIELD CONFIDENCE REPORT ======

class FieldConfidenceReport(BaseModel):
    """Confidence analysis for specific field."""
    field_type: InvoiceFieldTypeSchema
    total_extractions: int
    total_found: int
    success_rate: float = Field(..., ge=0.0, le=1.0)
    average_confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_distribution: Dict[str, int] = Field(
        ...,
        description="Histogram of confidence ranges"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "field_type": "invoice_number",
                "total_extractions": 100,
                "total_found": 98,
                "success_rate": 0.98,
                "average_confidence": 0.93,
                "confidence_distribution": {
                    "0.0-0.25": 0,
                    "0.25-0.5": 1,
                    "0.5-0.75": 3,
                    "0.75-1.0": 94
                }
            }
        }
