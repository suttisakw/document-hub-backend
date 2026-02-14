"""
FastAPI router for table extraction endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from collections import defaultdict
import statistics

from app.services.table_extraction_engine import (
    create_table_extraction_engine,
    TableExtractionEngine,
    BoundingBox,
    table_extraction_output_to_json
)
from app.schemas.table_extraction import (
    TableExtractionRequest,
    TableExtractionResponse,
    BatchTableExtractionRequest,
    BatchTableExtractionResponse,
    TableExtractionConfigSchema,
    ExtractionStatisticsResponse,
    ColumnStatisticsSchema,
    StandardColumnNameSchema,
    OCRLineSchema,
)

router = APIRouter(prefix="/api/extract/table", tags=["table-extraction"])

# Module-level state
_engine: TableExtractionEngine = None
_statistics: Dict[str, Any] = {
    "total_documents_processed": 0,
    "total_tables_found": 0,
    "total_rows_extracted": 0,
    "total_cells_extracted": 0,
    "confidences": [],  # Track all confidences for averaging
    "column_statistics": defaultdict(lambda: {
        "detection_count": 0,
        "total_count": 0,
        "confidence_values": [],
        "extraction_methods": defaultdict(int)
    }),
    "processing_times": []
}

_config = TableExtractionConfigSchema()


def get_engine() -> TableExtractionEngine:
    """Get or create table extraction engine."""
    global _engine
    if _engine is None:
        _engine = create_table_extraction_engine()
    return _engine


@router.post("/extract", response_model=TableExtractionResponse, summary="Extract table from document")
async def extract_table(
    request: TableExtractionRequest,
    engine: TableExtractionEngine = Depends(get_engine)
) -> Dict[str, Any]:
    """
    Extract table from OCR-extracted document.
    
    Pipeline:
    1. Detect table region via bbox clustering
    2. Detect header row
    3. Map columns to standard schema
    4. Extract rows by vertical alignment
    5. Validate numeric columns
    6. Return structured JSON with confidence scores
    
    Args:
        request: OCR lines and configuration
        engine: Extraction engine
        
    Returns:
        Table extraction result
    """
    try:
        # Convert request to engine format
        ocr_output = [
            (line.text, BoundingBox(
                x_min=line.x_min,
                y_min=line.y_min,
                x_max=line.x_max,
                y_max=line.y_max
            ))
            for line in request.ocr_lines
        ]

        # Extract tables
        tables = engine.extract_tables(
            ocr_output=ocr_output,
            page_height=request.page_height,
            page_width=request.page_width
        )

        # Return first table (most prominent)
        if tables:
            result = tables[0]
            response_json = table_extraction_output_to_json(result)
            
            # Record statistics
            _record_statistics(result)
            
            return response_json
        else:
            return {
                "table_found": False,
                "error": "No table detected in document"
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction error: {str(e)}")


@router.post("/extract/batch", response_model=BatchTableExtractionResponse, summary="Extract tables from multiple documents")
async def extract_batch(
    request: BatchTableExtractionRequest,
    engine: TableExtractionEngine = Depends(get_engine)
) -> Dict[str, Any]:
    """
    Extract tables from multiple documents (batch processing).
    
    Args:
        request: List of documents with OCR lines
        engine: Extraction engine
        
    Returns:
        Batch extraction results
    """
    try:
        results = []
        errors = []

        for idx, doc in enumerate(request.documents):
            try:
                # Convert request to engine format
                ocr_output = [
                    (line.text, BoundingBox(
                        x_min=line.x_min,
                        y_min=line.y_min,
                        x_max=line.x_max,
                        y_max=line.y_max
                    ))
                    for line in doc.ocr_lines
                ]

                # Extract
                tables = engine.extract_tables(
                    ocr_output=ocr_output,
                    page_height=doc.page_height,
                    page_width=doc.page_width
                )

                if tables:
                    result = tables[0]
                    response_json = table_extraction_output_to_json(result)
                    results.append(response_json)
                    _record_statistics(result)
                else:
                    results.append({"table_found": False, "error": "No table detected"})

            except Exception as e:
                error_msg = f"Document {idx}: {str(e)}"
                errors.append(error_msg)
                if request.fail_fast:
                    raise HTTPException(status_code=400, detail=error_msg)

        return {
            "total_documents": len(request.documents),
            "successful_extractions": len([r for r in results if r.get("table_found", False)]),
            "failed_extractions": len([r for r in results if not r.get("table_found", False)]),
            "results": results,
            "errors": errors
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch extraction error: {str(e)}")


@router.get("/config", response_model=TableExtractionConfigSchema, summary="Get current configuration")
async def get_config() -> Dict[str, Any]:
    """Get current table extraction configuration."""
    return _config.model_dump()


@router.post("/config", response_model=TableExtractionConfigSchema, summary="Update configuration")
async def update_config(config: TableExtractionConfigSchema) -> Dict[str, Any]:
    """
    Update table extraction configuration.
    
    Args:
        config: New configuration
        
    Returns:
        Updated configuration
    """
    global _config, _engine
    _config = config
    # Reset engine to rebuild with new config
    _engine = create_table_extraction_engine()
    return _config.model_dump()


@router.get("/statistics", response_model=ExtractionStatisticsResponse, summary="Get extraction statistics")
async def get_statistics() -> Dict[str, Any]:
    """Get cumulative extraction statistics."""
    # Calculate averages
    avg_confidence = (
        sum(_statistics["confidences"]) / len(_statistics["confidences"])
        if _statistics["confidences"]
        else 0.0
    )

    # Calculate detection rates
    table_detection_rate = (
        _statistics["total_tables_found"] / _statistics["total_documents_processed"]
        if _statistics["total_documents_processed"] > 0
        else 0.0
    )

    # Build column statistics
    column_stats = {}
    for col_name, col_data in _statistics["column_statistics"].items():
        detection_rate = (
            col_data["detection_count"] / col_data["total_count"]
            if col_data["total_count"] > 0
            else 0.0
        )
        avg_col_confidence = (
            sum(col_data["confidence_values"]) / len(col_data["confidence_values"])
            if col_data["confidence_values"]
            else 0.0
        )

        column_stats[col_name] = {
            "column_name": col_name,
            "detection_rate": detection_rate,
            "avg_confidence": avg_col_confidence,
            "total_extracted": col_data["detection_count"],
            "extraction_method_distribution": dict(col_data["extraction_methods"])
        }

    # Calculate average processing time
    avg_processing_time = (
        sum(_statistics["processing_times"]) / len(_statistics["processing_times"])
        if _statistics["processing_times"]
        else 0.0
    )

    return {
        "total_documents_processed": _statistics["total_documents_processed"],
        "total_tables_found": _statistics["total_tables_found"],
        "table_detection_rate": table_detection_rate,
        "total_rows_extracted": _statistics["total_rows_extracted"],
        "total_cells_extracted": _statistics["total_cells_extracted"],
        "avg_overall_confidence": avg_confidence,
        "column_statistics": column_stats,
        "processing_times": {
            "avg_ms": avg_processing_time
        }
    }


@router.get("/statistics/column/{column_type}", summary="Get statistics for specific column type")
async def get_column_statistics(column_type: StandardColumnNameSchema) -> Dict[str, Any]:
    """
    Get statistics for a specific column type.
    
    Args:
        column_type: Standard column name
        
    Returns:
        Column-specific statistics
    """
    col_name = column_type.value
    col_data = _statistics["column_statistics"].get(col_name)

    if not col_data:
        return {
            "column_name": col_name,
            "detection_rate": 0.0,
            "avg_confidence": 0.0,
            "total_extracted": 0,
            "extraction_method_distribution": {}
        }

    detection_rate = (
        col_data["detection_count"] / col_data["total_count"]
        if col_data["total_count"] > 0
        else 0.0
    )
    avg_confidence = (
        sum(col_data["confidence_values"]) / len(col_data["confidence_values"])
        if col_data["confidence_values"]
        else 0.0
    )

    return {
        "column_name": col_name,
        "detection_rate": detection_rate,
        "avg_confidence": avg_confidence,
        "total_extracted": col_data["detection_count"],
        "extraction_method_distribution": dict(col_data["extraction_methods"])
    }


@router.get("/health", summary="Health check")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "table-extraction"}


# ====== HELPER FUNCTIONS ======

def _record_statistics(extraction_output) -> None:
    """Record extraction statistics."""
    if not extraction_output.table_found:
        return

    _statistics["total_documents_processed"] += 1
    _statistics["total_tables_found"] += 1
    _statistics["total_rows_extracted"] += len(extraction_output.rows)
    _statistics["processing_times"].append(extraction_output.processing_time_ms)

    # Track confidences
    _statistics["confidences"].append(extraction_output.overall_confidence)
    _statistics["confidences"].extend(extraction_output.row_confidences)

    # Track cell confidences by column
    for row in extraction_output.rows:
        _statistics["total_cells_extracted"] += len(row.cells)
        
        for col_name, cell in row.cells.items():
            col_key = col_name.value
            _statistics["column_statistics"][col_key]["detection_count"] += 1
            _statistics["column_statistics"][col_key]["confidence_values"].append(cell.confidence)
            _statistics["column_statistics"][col_key]["extraction_methods"][cell.method.value] += 1

    # Track total possible columns (for detection rate calculation)
    for col in extraction_output.columns:
        col_key = col.standard_name.value
        _statistics["column_statistics"][col_key]["total_count"] += len(extraction_output.rows)


def auto_extract_invoice_tables(ocr_output: List[tuple]) -> List[Dict[str, Any]]:
    """
    Convenience function: auto-extract all tables from OCR output.
    
    Args:
        ocr_output: List of (text, bbox) tuples
        
    Returns:
        List of extracted tables as JSON
    """
    engine = get_engine()
    bboxes = [(text, bbox) for text, bbox in ocr_output]
    
    tables = engine.extract_tables(ocr_output=bboxes)
    
    return [table_extraction_output_to_json(table) for table in tables]
