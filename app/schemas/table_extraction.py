"""
Pydantic schemas for table extraction API.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from enum import Enum
from app.schemas.confidence import ConfidenceScore


class StandardColumnNameSchema(str, Enum):
    """Standard column names."""
    ITEM_NAME = "item_name"
    QUANTITY = "quantity"
    UNIT_PRICE = "unit_price"
    AMOUNT = "amount"
    DESCRIPTION = "description"


class ColumnTypeSchema(str, Enum):
    """Column data types."""
    TEXT = "text"
    NUMERIC = "numeric"
    FLOAT = "float"
    INTEGER = "integer"
    OPTIONAL = "optional"


class ExtractionMethodSchema(str, Enum):
    """Extraction methods."""
    REGEX = "regex"
    CLUSTERING = "clustering"
    ALIGNMENT = "alignment"
    INTERPOLATION = "interpolation"


class BoundingBoxSchema(BaseModel):
    """Bounding box coordinates."""
    x_min: float = Field(..., description="Left edge")
    y_min: float = Field(..., description="Top edge")
    x_max: float = Field(..., description="Right edge")
    y_max: float = Field(..., description="Bottom edge")

    class Config:
        json_schema_extra = {
            "example": {
                "x_min": 10.0,
                "y_min": 20.0,
                "x_max": 100.0,
                "y_max": 40.0
            }
        }


class OCRLineSchema(BaseModel):
    """Single OCR line from document."""
    text: str = Field(..., description="Extracted text")
    x_min: float = Field(..., description="Left edge x-coordinate")
    y_min: float = Field(..., description="Top edge y-coordinate")
    x_max: float = Field(..., description="Right edge x-coordinate")
    y_max: float = Field(..., description="Bottom edge y-coordinate")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="OCR confidence")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "Item Name",
                "x_min": 10.0,
                "y_min": 50.0,
                "x_max": 100.0,
                "y_max": 70.0,
                "confidence": 0.95
            }
        }


class TableExtractionRequest(BaseModel):
    """Request to extract table from document."""
    ocr_lines: List[OCRLineSchema] = Field(
        ...,
        description="OCR-extracted lines with bounding boxes",
        min_items=4
    )
    page_height: float = Field(default=1000.0, description="Page height in pixels")
    page_width: float = Field(default=1000.0, description="Page width in pixels")
    min_table_cells: int = Field(default=4, ge=2, description="Minimum cells for valid table")
    min_rows: int = Field(default=2, ge=1, description="Minimum rows including header")
    include_descriptions: bool = Field(default=True, description="Include optional description column")

    class Config:
        json_schema_extra = {
            "example": {
                "ocr_lines": [
                    {
                        "text": "Item Name",
                        "x_min": 10.0,
                        "y_min": 50.0,
                        "x_max": 100.0,
                        "y_max": 70.0,
                        "confidence": 0.95
                    }
                ],
                "page_height": 1000.0,
                "page_width": 1000.0,
                "min_table_cells": 4,
                "min_rows": 2
            }
        }


class TableCellResponseSchema(BaseModel):
    """Single cell in extracted table."""
    value: str = Field(..., description="Cell content")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence")
    method: ExtractionMethodSchema = Field(..., description="How cell was extracted")
    confidence_details: Optional[ConfidenceScore] = Field(
        None,
        description="Detailed unified confidence scoring information"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "value": "Item A",
                "confidence": 0.92,
                "method": "alignment"
            }
        }


class TableRowResponseSchema(BaseModel):
    """Single row in extracted table."""
    row_index: int = Field(..., description="Row number (0-indexed, excludes header)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Average cell confidence")
    cells: Dict[str, TableCellResponseSchema] = Field(
        ...,
        description="Cells mapped to standard column names"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "row_index": 0,
                "confidence": 0.91,
                "cells": {
                    "item_name": {"value": "Product A", "confidence": 0.95, "method": "alignment"},
                    "quantity": {"value": "10", "confidence": 0.90, "method": "alignment"},
                    "unit_price": {"value": "50.00", "confidence": 0.88, "method": "alignment"},
                    "amount": {"value": "500.00", "confidence": 0.87, "method": "alignment"}
                }
            }
        }


class ColumnMetadataSchema(BaseModel):
    """Metadata for table column."""
    index: int = Field(..., description="Column index")
    detected_name: str = Field(..., description="Name detected in header")
    standard_name: StandardColumnNameSchema = Field(..., description="Mapped standard name")
    type: ColumnTypeSchema = Field(..., description="Column data type")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Mapping confidence")

    class Config:
        json_schema_extra = {
            "example": {
                "index": 0,
                "detected_name": "Item",
                "standard_name": "item_name",
                "type": "text",
                "confidence": 0.95
            }
        }


class TableExtractionResponse(BaseModel):
    """Response from table extraction."""
    table_found: bool = Field(..., description="Whether table was detected")
    table_region: Optional[BoundingBoxSchema] = Field(default=None, description="Coordinates of detected table")
    columns: List[ColumnMetadataSchema] = Field(default_factory=list, description="Column metadata")
    rows: List[TableRowResponseSchema] = Field(default_factory=list, description="Extracted rows")
    overall_confidence: float = Field(..., ge=0.0, le=1.0, description="Average confidence across all rows")
    table_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in table detection")
    header_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in header detection")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    processing_time_ms: float = Field(default=0.0, description="Processing time in milliseconds")

    class Config:
        json_schema_extra = {
            "example": {
                "table_found": True,
                "table_region": {
                    "x_min": 10.0,
                    "y_min": 45.0,
                    "x_max": 200.0,
                    "y_max": 300.0
                },
                "columns": [
                    {
                        "index": 0,
                        "detected_name": "Item Name",
                        "standard_name": "item_name",
                        "type": "text",
                        "confidence": 0.95
                    }
                ],
                "rows": [
                    {
                        "row_index": 0,
                        "confidence": 0.91,
                        "cells": {
                            "item_name": {"value": "Product A", "confidence": 0.95, "method": "alignment"}
                        }
                    }
                ],
                "overall_confidence": 0.87,
                "table_confidence": 0.90,
                "header_confidence": 0.95,
                "metadata": {"num_rows": 5, "num_columns": 4, "num_cells": 20},
                "processing_time_ms": 45.3
            }
        }


class BatchTableExtractionRequest(BaseModel):
    """Batch request for multiple documents."""
    documents: List[TableExtractionRequest] = Field(
        ...,
        description="List of documents to process",
        max_items=100
    )
    fail_fast: bool = Field(default=False, description="Stop on first error")

    class Config:
        json_schema_extra = {
            "example": {
                "documents": [
                    {
                        "ocr_lines": [
                            {"text": "Item Name", "x_min": 10.0, "y_min": 50.0, "x_max": 100.0, "y_max": 70.0, "confidence": 0.95}
                        ]
                    }
                ],
                "fail_fast": False
            }
        }


class BatchTableExtractionResponse(BaseModel):
    """Response containing batch extraction results."""
    total_documents: int = Field(..., description="Total documents processed")
    successful_extractions: int = Field(..., description="Successfully extracted tables")
    failed_extractions: int = Field(..., description="Failed extractions")
    results: List[TableExtractionResponse] = Field(..., description="Individual results")
    errors: List[str] = Field(default_factory=list, description="Error messages")

    class Config:
        json_schema_extra = {
            "example": {
                "total_documents": 2,
                "successful_extractions": 2,
                "failed_extractions": 0,
                "results": [],
                "errors": []
            }
        }


class TableExtractionConfigSchema(BaseModel):
    """Configuration for table extraction engine."""
    distance_threshold: float = Field(default=50.0, description="Distance for bbox clustering")
    vertical_alignment_threshold: float = Field(default=10.0, description="Vertical alignment tolerance")
    min_table_cells: int = Field(default=4, description="Minimum cells for valid table")
    min_rows: int = Field(default=2, description="Minimum rows for valid table")
    enable_header_detection: bool = Field(default=True, description="Enable header row detection")
    enable_numeric_validation: bool = Field(default=True, description="Validate numeric columns")

    class Config:
        json_schema_extra = {
            "example": {
                "distance_threshold": 50.0,
                "vertical_alignment_threshold": 10.0,
                "min_table_cells": 4,
                "min_rows": 2,
                "enable_header_detection": True,
                "enable_numeric_validation": True
            }
        }


class ColumnStatisticsSchema(BaseModel):
    """Statistics for a single column."""
    column_name: StandardColumnNameSchema = Field(..., description="Column standard name")
    detection_rate: float = Field(..., ge=0.0, le=1.0, description="How often column is detected")
    avg_confidence: float = Field(..., ge=0.0, le=1.0, description="Average confidence")
    total_extracted: int = Field(..., description="Total cells extracted")
    extraction_method_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="How many extracted via each method"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "column_name": "item_name",
                "detection_rate": 0.95,
                "avg_confidence": 0.92,
                "total_extracted": 150,
                "extraction_method_distribution": {"alignment": 150}
            }
        }


class ExtractionStatisticsResponse(BaseModel):
    """Overall extraction statistics."""
    total_documents_processed: int = Field(..., description="Total documents processed")
    total_tables_found: int = Field(..., description="Total tables detected")
    table_detection_rate: float = Field(..., ge=0.0, le=1.0, description="Percentage of docs with tables")
    total_rows_extracted: int = Field(..., description="Total rows across all tables")
    total_cells_extracted: int = Field(..., description="Total cells extracted")
    avg_overall_confidence: float = Field(..., ge=0.0, le=1.0, description="Average confidence")
    column_statistics: Dict[str, ColumnStatisticsSchema] = Field(
        default_factory=dict,
        description="Per-column statistics"
    )
    processing_times: Dict[str, float] = Field(
        default_factory=dict,
        description="Average processing times"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "total_documents_processed": 50,
                "total_tables_found": 48,
                "table_detection_rate": 0.96,
                "total_rows_extracted": 512,
                "total_cells_extracted": 2048,
                "avg_overall_confidence": 0.87,
                "column_statistics": {},
                "processing_times": {"avg_ms": 45.3}
            }
        }
