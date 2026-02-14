"""
Migration Guide: Converting Existing OCR Structures to Unified Document Schema

This module provides utilities and examples for converting existing
OCR data structures to the new unified document schema.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.models import Document as DocumentModel
from app.models import DocumentPage as DocumentPageModel
from app.models import ExtractedField as ExtractedFieldModel
from app.schemas.unified_document import (
    BoundingBox,
    DocumentPage,
    ExtractedTable,
    ExtractedValue,
    ExtractionSource,
    TableCell,
    TableRow,
    UnifiedDocument,
)


def convert_extracted_field_to_value(field: ExtractedFieldModel) -> ExtractedValue:
    """
    Convert legacy ExtractedField model to unified ExtractedValue.
    
    Args:
        field: ExtractedField database model instance
    
    Returns:
        ExtractedValue with mapped data
    """
    bbox = None
    if all(
        v is not None
        for v in [field.bbox_x, field.bbox_y, field.bbox_width, field.bbox_height]
    ):
        bbox = BoundingBox(
            x=field.bbox_x,
            y=field.bbox_y,
            width=field.bbox_width,
            height=field.bbox_height,
            page_number=field.page_number,
        )

    # Determine source based on field metadata
    # If is_edited is True, source is manual
    # Otherwise, default to OCR (can be enhanced with additional metadata)
    source = ExtractionSource.MANUAL if field.is_edited else ExtractionSource.OCR

    return ExtractedValue(
        name=field.field_name,
        value=field.field_value,
        bbox=bbox,
        confidence=field.confidence,
        source=source,
        page_number=field.page_number,
        is_edited=field.is_edited,
        data_type="text",  # Can be inferred from field_name or value type
    )


def convert_document_page_to_unified(page: DocumentPageModel) -> DocumentPage:
    """
    Convert legacy DocumentPage model to unified DocumentPage.
    
    Args:
        page: DocumentPage database model instance
    
    Returns:
        DocumentPage with mapped data
    """
    return DocumentPage(
        page_number=page.page_number,
        width=page.width,
        height=page.height,
        image_path=page.image_path,
        raw_text=None,  # Not stored in legacy model
    )


def convert_document_to_unified(
    doc: DocumentModel,
    extracted_fields: list[ExtractedFieldModel] | None = None,
    pages: list[DocumentPageModel] | None = None,
    raw_ocr_data: dict | None = None,
) -> UnifiedDocument:
    """
    Convert legacy Document model to unified UnifiedDocument.
    
    Args:
        doc: Document database model instance
        extracted_fields: List of extracted fields (if loaded)
        pages: List of document pages (if loaded)
        raw_ocr_data: Original OCR output data (from OcrJob.result_json)
    
    Returns:
        UnifiedDocument with all data mapped
    """
    # Convert pages
    unified_pages = []
    if pages:
        unified_pages = [convert_document_page_to_unified(p) for p in pages]

    # Convert extracted fields to header_fields
    # Note: In the current system, all extracted fields are treated as header fields
    # If we need to separate line items, we'd need additional logic
    header_fields = []
    if extracted_fields:
        header_fields = [convert_extracted_field_to_value(f) for f in extracted_fields]

    # Tables would need to be extracted from structured data
    # For now, we don't have table extraction in the current system
    tables: list[ExtractedTable] = []

    return UnifiedDocument(
        document_id=doc.id,
        document_type=doc.type,
        confidence_score=doc.confidence,
        processing_status=doc.status,
        processed_at=doc.scanned_at,
        pages=unified_pages,
        header_fields=header_fields,
        tables=tables,
        raw_ocr=raw_ocr_data,
        applied_template_id=doc.applied_template_id,
        applied_template_name=doc.applied_template_name,
        extraction_engine=None,  # Not tracked in current system
    )


def convert_easyocr_result_to_unified(
    document_id: UUID,
    document_type: str,
    easyocr_results: list[dict],
    page_width: int | None = None,
    page_height: int | None = None,
) -> UnifiedDocument:
    """
    Convert EasyOCR raw results to unified document format.
    
    EasyOCR results format:
    [
        {
            "bbox": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]],
            "text": "extracted text",
            "confidence": 0.95
        },
        ...
    ]
    
    Args:
        document_id: Document UUID
        document_type: Document type
        easyocr_results: Raw EasyOCR results
        page_width: Optional page width
        page_height: Optional page height
    
    Returns:
        UnifiedDocument with OCR results
    """
    header_fields = []

    for i, result in enumerate(easyocr_results):
        bbox_coords = result.get("bbox", [])
        text = result.get("text", "")
        confidence = result.get("confidence")

        # Calculate bounding box from coordinates
        bbox = None
        if bbox_coords and len(bbox_coords) == 4:
            xs = [p[0] for p in bbox_coords]
            ys = [p[1] for p in bbox_coords]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)

            bbox = BoundingBox(
                x=float(x1),
                y=float(y1),
                width=float(x2 - x1),
                height=float(y2 - y1),
                page_number=1,
            )

        header_fields.append(
            ExtractedValue(
                name=f"text_{i}",
                value=text,
                bbox=bbox,
                confidence=float(confidence) if confidence is not None else None,
                source=ExtractionSource.OCR,
                page_number=1,
                is_edited=False,
                data_type="text",
            )
        )

    pages = []
    if page_width and page_height:
        pages = [
            DocumentPage(
                page_number=1, width=page_width, height=page_height, image_path=None
            )
        ]

    return UnifiedDocument(
        document_id=document_id,
        document_type=document_type,
        confidence_score=None,
        processing_status="completed",
        processed_at=datetime.utcnow(),
        pages=pages,
        header_fields=header_fields,
        tables=[],
        raw_ocr={"provider": "easyocr", "results": easyocr_results},
        extraction_engine="easyocr",
    )


def convert_paddleocr_result_to_unified(
    document_id: UUID,
    document_type: str,
    paddleocr_results: list[list],
    page_width: int | None = None,
    page_height: int | None = None,
) -> UnifiedDocument:
    """
    Convert PaddleOCR raw results to unified document format.
    
    PaddleOCR results format (per page):
    [
        [
            [bbox_coords, [text, confidence]],
            ...
        ],
        ...  # additional pages
    ]
    
    Args:
        document_id: Document UUID
        document_type: Document type
        paddleocr_results: Raw PaddleOCR results
        page_width: Optional page width
        page_height: Optional page height
    
    Returns:
        UnifiedDocument with OCR results
    """
    header_fields = []
    field_counter = 0

    # PaddleOCR returns results per page
    for page_idx, page_results in enumerate(paddleocr_results):
        page_number = page_idx + 1

        for entry in page_results or []:
            if not entry or len(entry) < 2:
                continue

            bbox_coords = entry[0]
            text_data = entry[1]

            if not text_data or len(text_data) < 1:
                continue

            text = str(text_data[0]).strip()
            confidence = float(text_data[1]) if len(text_data) > 1 else None

            # Calculate bounding box
            bbox = None
            if bbox_coords and len(bbox_coords) == 4:
                xs = [p[0] for p in bbox_coords]
                ys = [p[1] for p in bbox_coords]
                x1, x2 = min(xs), max(xs)
                y1, y2 = min(ys), max(ys)

                bbox = BoundingBox(
                    x=float(x1),
                    y=float(y1),
                    width=float(x2 - x1),
                    height=float(y2 - y1),
                    page_number=page_number,
                )

            header_fields.append(
                ExtractedValue(
                    name=f"text_{field_counter}",
                    value=text,
                    bbox=bbox,
                    confidence=confidence,
                    source=ExtractionSource.OCR,
                    page_number=page_number,
                    is_edited=False,
                    data_type="text",
                )
            )
            field_counter += 1

    pages = []
    if page_width and page_height:
        # Create page metadata for each page in results
        pages = [
            DocumentPage(
                page_number=i + 1,
                width=page_width,
                height=page_height,
                image_path=None,
            )
            for i in range(len(paddleocr_results))
        ]

    return UnifiedDocument(
        document_id=document_id,
        document_type=document_type,
        confidence_score=None,
        processing_status="completed",
        processed_at=datetime.utcnow(),
        pages=pages,
        header_fields=header_fields,
        tables=[],
        raw_ocr={
            "provider": "paddleocr",
            "results": paddleocr_results,
        },
        extraction_engine="paddleocr",
    )


def create_table_from_extracted_fields(
    fields: list[ExtractedFieldModel],
    table_id: str,
    page_number: int,
    columns: list[str],
    rows_per_item: int = 1,
) -> ExtractedTable:
    """
    Create a table from extracted fields (for line items).
    
    This is useful when line items are stored as individual ExtractedField
    records with naming patterns like:
    - item_0_description, item_0_quantity, item_0_price
    - item_1_description, item_1_quantity, item_1_price
    
    Args:
        fields: List of ExtractedField models
        table_id: Table identifier
        page_number: Page where table is located
        columns: Column names
        rows_per_item: Number of fields per row
    
    Returns:
        ExtractedTable with structured data
    """
    # Group fields by row index (extracted from field name)
    row_data: dict[int, dict[str, ExtractedFieldModel]] = {}

    for field in fields:
        # Try to extract row index from field name (e.g., "item_0_description")
        parts = field.field_name.split("_")
        if len(parts) >= 3 and parts[0] == "item":
            try:
                row_idx = int(parts[1])
                col_name = "_".join(parts[2:])

                if row_idx not in row_data:
                    row_data[row_idx] = {}

                row_data[row_idx][col_name] = field
            except ValueError:
                continue

    # Build table rows
    rows = []
    for row_idx in sorted(row_data.keys()):
        cells = []
        row_fields = row_data[row_idx]

        for col_name in columns:
            field = row_fields.get(col_name)
            if field:
                bbox = None
                if all(
                    v is not None
                    for v in [
                        field.bbox_x,
                        field.bbox_y,
                        field.bbox_width,
                        field.bbox_height,
                    ]
                ):
                    bbox = BoundingBox(
                        x=field.bbox_x,
                        y=field.bbox_y,
                        width=field.bbox_width,
                        height=field.bbox_height,
                        page_number=field.page_number,
                    )

                cells.append(
                    TableCell(
                        value=field.field_value,
                        confidence=field.confidence,
                        bbox=bbox,
                        column_name=col_name,
                        is_header=False,
                    )
                )
            else:
                # Empty cell
                cells.append(TableCell(value=None, column_name=col_name))

        # Calculate row confidence (average of cell confidences)
        confidences = [c.confidence for c in cells if c.confidence is not None]
        row_confidence = sum(confidences) / len(confidences) if confidences else None

        rows.append(TableRow(row_index=row_idx, cells=cells, confidence=row_confidence))

    # Calculate table confidence
    row_confidences = [r.confidence for r in rows if r.confidence is not None]
    table_confidence = (
        sum(row_confidences) / len(row_confidences) if row_confidences else None
    )

    return ExtractedTable(
        table_id=table_id,
        page_number=page_number,
        bbox=None,
        columns=columns,
        rows=rows,
        confidence=table_confidence,
        source=ExtractionSource.OCR,
    )


# Example usage in API endpoint:
"""
from sqlmodel import Session, select
from app.models import Document, ExtractedField, DocumentPage, OcrJob
from app.schemas.unified_document_migration import convert_document_to_unified

@router.get("/documents/{document_id}/unified")
async def get_unified_document(
    document_id: UUID,
    session: Session = Depends(get_session),
):
    # Get document
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get extracted fields
    fields = session.exec(
        select(ExtractedField).where(ExtractedField.document_id == document_id)
    ).all()
    
    # Get pages
    pages = session.exec(
        select(DocumentPage).where(DocumentPage.document_id == document_id)
    ).all()
    
    # Get raw OCR data (if available)
    ocr_job = session.exec(
        select(OcrJob)
        .where(OcrJob.document_id == document_id)
        .where(OcrJob.status == "completed")
    ).first()
    
    raw_ocr = ocr_job.result_json if ocr_job else None
    
    # Convert to unified format
    unified_doc = convert_document_to_unified(
        doc=doc,
        extracted_fields=fields,
        pages=pages,
        raw_ocr_data=raw_ocr,
    )
    
    return unified_doc
"""
