"""
Unified Document Schema for OCR Results

This module defines a unified structure for OCR results that:
1. Wraps existing OCR outputs in raw_ocr field
2. Provides structured extraction with source attribution
3. Supports tables with per-cell confidence
4. Maintains backward compatibility with existing ExtractedField model
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ExtractionSource(str, Enum):
    """Source method used for field extraction."""

    TEMPLATE = "template"  # Extracted using predefined template zones
    REGEX = "regex"  # Extracted using regex pattern matching
    ML = "ml"  # Extracted using ML model (e.g., form understanding)
    LLM = "llm"  # Extracted using LLM (e.g., GPT-4 Vision, Claude)
    MANUAL = "manual"  # Manually edited by user
    OCR = "ocr"  # Direct OCR text detection (no extraction logic)


class BoundingBox(BaseModel):
    """Bounding box coordinates for a field or cell."""

    x: float = Field(..., description="Top-left X coordinate")
    y: float = Field(..., description="Top-left Y coordinate")
    width: float = Field(..., description="Width of bounding box")
    height: float = Field(..., description="Height of bounding box")
    page_number: int | None = Field(None, description="Page number (1-indexed)")

    @classmethod
    def from_components(
        cls,
        x: float,
        y: float,
        width: float,
        height: float,
        page_number: int | None = None,
    ) -> BoundingBox:
        """Create BoundingBox from individual components."""
        return cls(x=x, y=y, width=width, height=height, page_number=page_number)


class ExtractedValue(BaseModel):
    """
    A single extracted field value with metadata.
    
    This represents any extracted piece of information from a document,
    whether it's a header field, line item, or other data point.
    """

    name: str = Field(..., description="Field name (e.g., 'invoice_number', 'total_amount')")
    value: str | float | int | bool | None = Field(
        None, description="Extracted value (can be string, number, boolean, or null)"
    )
    bbox: BoundingBox | None = Field(None, description="Location of this field in the document")
    confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Confidence score (0.0 to 1.0)"
    )
    source: ExtractionSource = Field(
        ..., description="Method used to extract this field"
    )
    page_number: int | None = Field(None, description="Page number where field was found (1-indexed)")
    is_edited: bool = Field(False, description="Whether this value was manually edited")
    data_type: Literal["text", "number", "date", "boolean", "currency"] = Field(
        "text", description="Semantic type of the value"
    )


class TableCell(BaseModel):
    """A single cell in a table with its value and metadata."""

    value: str | float | int | None = Field(None, description="Cell value")
    confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Confidence score for this cell"
    )
    bbox: BoundingBox | None = Field(None, description="Location of this cell")
    column_name: str | None = Field(None, description="Mapped column name (if header mapped)")
    is_header: bool = Field(False, description="Whether this cell is a header cell")


class TableRow(BaseModel):
    """A single row in a table."""

    row_index: int = Field(..., description="0-indexed row number")
    cells: list[TableCell] = Field(default_factory=list, description="Cells in this row")
    confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Average confidence for this row"
    )


class ExtractedTable(BaseModel):
    """
    A table extracted from the document.
    
    Tables can be extracted from invoices (line items), receipts,
    or any structured tabular data in documents.
    """

    table_id: str = Field(..., description="Unique identifier for this table within the document")
    page_number: int = Field(..., description="Page number where table is located (1-indexed)")
    bbox: BoundingBox | None = Field(None, description="Bounding box of entire table")
    columns: list[str] = Field(
        default_factory=list,
        description="Column names (mapped field names from header row)",
    )
    rows: list[TableRow] = Field(default_factory=list, description="Table rows")
    confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Average confidence for entire table"
    )
    source: ExtractionSource = Field(
        ExtractionSource.OCR, description="Method used to extract this table"
    )


class DocumentPage(BaseModel):
    """Metadata about a single page in the document."""

    page_number: int = Field(..., description="Page number (1-indexed)")
    width: int | None = Field(None, description="Page width in pixels")
    height: int | None = Field(None, description="Page height in pixels")
    image_path: str | None = Field(None, description="Path to rendered page image")
    raw_text: str | None = Field(None, description="Full extracted text from this page")


class UnifiedDocument(BaseModel):
    """
    Unified document schema that wraps OCR results with structured extraction.
    
    This schema provides:
    1. Structured header fields with source attribution
    2. Table extraction with per-cell confidence
    3. Raw OCR output preservation (backward compatibility)
    4. Document-level metadata and confidence scoring
    
    Example usage:
        doc = UnifiedDocument(
            document_id=uuid4(),
            document_type="invoice",
            pages=[...],
            header_fields=[
                ExtractedValue(
                    name="invoice_number",
                    value="INV-2026-001",
                    confidence=0.95,
                    source=ExtractionSource.TEMPLATE,
                    bbox=BoundingBox(x=100, y=50, width=200, height=30)
                )
            ],
            raw_ocr={...existing ocr output...}
        )
    """

    # Core identifiers
    document_id: UUID = Field(..., description="Unique document identifier")
    document_type: str = Field(
        ..., description="Document type (e.g., 'invoice', 'receipt', 'contract')"
    )

    # Document metadata
    confidence_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Overall confidence score for the entire document",
    )
    processing_status: str = Field(
        "completed", description="Processing status (pending, processing, completed, error)"
    )
    processed_at: datetime | None = Field(None, description="When OCR processing completed")

    # Page information
    pages: list[DocumentPage] = Field(
        default_factory=list, description="Metadata for each page in the document"
    )

    # Structured extraction results
    header_fields: list[ExtractedValue] = Field(
        default_factory=list,
        description="Extracted header/metadata fields (invoice number, date, vendor, etc.)",
    )

    tables: list[ExtractedTable] = Field(
        default_factory=list,
        description="Extracted tables (line items, expense details, etc.)",
    )

    # Raw OCR preservation (backward compatibility)
    raw_ocr: dict[str, Any] | None = Field(
        None,
        description="Original OCR output (PaddleOCR, EasyOCR, external provider, etc.)",
    )

    # Optional metadata
    applied_template_id: UUID | None = Field(
        None, description="ID of OCR template used (if any)"
    )
    applied_template_name: str | None = Field(
        None, description="Name of OCR template used (if any)"
    )
    extraction_engine: str | None = Field(
        None, description="Engine used for extraction (easyocr, paddleocr, azure, etc.)"
    )

    model_config = {"from_attributes": True}


class UnifiedDocumentCreate(BaseModel):
    """Request schema for creating a unified document result."""

    document_id: UUID
    document_type: str
    pages: list[DocumentPage] = Field(default_factory=list)
    header_fields: list[ExtractedValue] = Field(default_factory=list)
    tables: list[ExtractedTable] = Field(default_factory=list)
    raw_ocr: dict[str, Any] | None = None
    confidence_score: float | None = None
    applied_template_id: UUID | None = None
    applied_template_name: str | None = None
    extraction_engine: str | None = None


class UnifiedDocumentResponse(UnifiedDocument):
    """Response schema for unified document (includes all fields)."""

    pass


# Helper functions for converting existing data structures


def extract_value_from_field(
    field_name: str,
    field_value: str | None,
    confidence: float | None,
    bbox_x: float | None,
    bbox_y: float | None,
    bbox_width: float | None,
    bbox_height: float | None,
    source: ExtractionSource,
    page_number: int | None = None,
    is_edited: bool = False,
) -> ExtractedValue:
    """
    Convert legacy ExtractedField model to ExtractedValue.
    
    This helper maintains backward compatibility with the existing
    ExtractedField database model.
    """
    bbox = None
    if all(
        v is not None for v in [bbox_x, bbox_y, bbox_width, bbox_height]
    ):
        bbox = BoundingBox(
            x=bbox_x,
            y=bbox_y,
            width=bbox_width,
            height=bbox_height,
            page_number=page_number,
        )

    return ExtractedValue(
        name=field_name,
        value=field_value,
        bbox=bbox,
        confidence=confidence,
        source=source,
        page_number=page_number,
        is_edited=is_edited,
        data_type="text",  # Default, can be inferred
    )


def create_table_from_rows(
    table_id: str,
    page_number: int,
    columns: list[str],
    rows_data: list[list[Any]],
    source: ExtractionSource = ExtractionSource.OCR,
) -> ExtractedTable:
    """
    Create an ExtractedTable from simple row data.
    
    Args:
        table_id: Unique table identifier
        page_number: Page where table is located
        columns: Column names
        rows_data: List of rows, where each row is a list of cell values
        source: Extraction source
    
    Returns:
        ExtractedTable object
    """
    rows = []
    for row_idx, row_values in enumerate(rows_data):
        cells = [
            TableCell(
                value=val,
                column_name=columns[cell_idx] if cell_idx < len(columns) else None,
            )
            for cell_idx, val in enumerate(row_values)
        ]
        rows.append(TableRow(row_index=row_idx, cells=cells))

    return ExtractedTable(
        table_id=table_id, page_number=page_number, columns=columns, rows=rows, source=source
    )
