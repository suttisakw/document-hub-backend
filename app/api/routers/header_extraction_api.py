"""
REST API router for header extraction engine.

Provides endpoints for:
- Single document extraction
- Batch extraction
- Configuration management
- Statistics and monitoring
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, Dict, List
import time
from statistics import mean

from app.services.header_extraction_engine import (
    HeaderExtractionEngine,
    create_extraction_engine,
    InvoiceFieldType,
    ExtractionResult,
)
from app.schemas.header_extraction import (
    HeaderExtractionRequest,
    HeaderExtractionResponse,
    ExtractionResultSchema,
    InvoiceFieldTypeSchema,
    ExtractionSourceSchema,
    ExtractionStageSchema,
    BoundingBoxSchema,
    BatchExtractionRequest,
    BatchExtractionResponse,
    ExtractionEngineConfig,
    ExtractionStatisticsResponse,
    FieldConfidenceReport,
)

router = APIRouter(prefix="/api/extract", tags=["header_extraction"])

# ====== MODULE-LEVEL STATE ======

_engine: Optional[HeaderExtractionEngine] = None
_statistics = {
    "total_requests": 0,
    "total_fields_extracted": 0,
    "total_processing_time_ms": 0.0,
    "field_stats": {field.value: {"found": 0, "total": 0, "confidence_sum": 0.0} for field in InvoiceFieldType},
    "stage_stats": {},
}


def get_engine() -> HeaderExtractionEngine:
    """Get or create extraction engine."""
    global _engine
    if _engine is None:
        _engine = create_extraction_engine(
            enable_template=True,
            enable_regex=True,
            enable_ml=False,
            enable_llm=False
        )
    return _engine


def _convert_result_to_schema(result: ExtractionResult) -> ExtractionResultSchema:
    """Convert internal ExtractionResult to Pydantic schema."""
    bbox_schema = None
    if result.bbox:
        bbox_schema = BoundingBoxSchema(
            x_min=result.bbox.x_min,
            y_min=result.bbox.y_min,
            x_max=result.bbox.x_max,
            y_max=result.bbox.y_max
        )

    return ExtractionResultSchema(
        field_type=InvoiceFieldTypeSchema(result.field_type.value),
        value=result.value,
        confidence=result.confidence,
        source=ExtractionSourceSchema(result.source.value),
        stage=ExtractionStageSchema(result.stage.value),
        bbox=bbox_schema,
        raw_text=result.raw_text,
        evidence=result.evidence
    )


def _record_statistics(response: HeaderExtractionResponse) -> None:
    """Record extraction statistics."""
    global _statistics

    _statistics["total_requests"] += 1
    _statistics["total_processing_time_ms"] += response.processing_time_ms

    for field_type, result in response.fields.items():
        field_key = field_type.value
        _statistics["field_stats"][field_key]["total"] += 1

        if result.value is not None:
            _statistics["field_stats"][field_key]["found"] += 1
            _statistics["field_stats"][field_key]["confidence_sum"] += result.confidence

    # Record stage distribution
    stage_key = response.extracted_at_stage.value
    _statistics["stage_stats"][stage_key] = _statistics["stage_stats"].get(stage_key, 0) + 1


# ====== ENDPOINTS ======

@router.post(
    "/header",
    response_model=HeaderExtractionResponse,
    summary="Extract invoice header fields",
    description="Extract header fields from OCR text using multi-stage pipeline"
)
async def extract_header(
    request: HeaderExtractionRequest,
    engine: HeaderExtractionEngine = Depends(get_engine)
) -> HeaderExtractionResponse:
    """
    Extract invoice header fields from OCR text.
    
    Pipeline order:
    1. Template extraction (fastest)
    2. Regex anchor extraction (flexible)
    3. ML extraction (adaptive)
    4. LLM extraction (optional fallback)
    
    Returns:
    - Extracted fields with confidence scores
    - Bounding boxes (if available)
    - Evidence and scoring breakdown
    - Overall confidence and processing time
    """
    try:
        # Parse field types
        field_types = None
        if request.field_types:
            field_types = [InvoiceFieldType(ft.value) for ft in request.field_types]

        # Extract headers
        output = engine.extract_invoice_header(
            ocr_lines=request.ocr_lines,
            field_types=field_types,
            ocr_confidence_scores=request.ocr_confidence_scores
        )

        # Convert results to schema
        fields_response = {
            InvoiceFieldTypeSchema(ft.value): _convert_result_to_schema(result)
            for ft, result in output.fields.items()
        }

        # Get high-confidence fields
        high_confidence = {
            ft: result for ft, result in output.fields.items()
            if result.confidence >= 0.7
        }
        high_confidence_response = {
            InvoiceFieldTypeSchema(ft.value): _convert_result_to_schema(result)
            for ft, result in high_confidence.items()
        }

        response = HeaderExtractionResponse(
            fields=fields_response,
            overall_confidence=output.overall_confidence,
            extracted_at_stage=ExtractionStageSchema(output.extracted_at_stage.value),
            processing_time_ms=output.processing_time_ms,
            high_confidence_fields=high_confidence_response if high_confidence_response else None,
            all_results=[_convert_result_to_schema(r) for r in output.all_results] if output.all_results else None
        )

        # Record statistics
        _record_statistics(response)

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


@router.post(
    "/header/batch",
    response_model=BatchExtractionResponse,
    summary="Extract headers from multiple documents",
    description="Batch extract headers from multiple OCR documents (up to 100)"
)
async def extract_header_batch(
    request: BatchExtractionRequest,
    engine: HeaderExtractionEngine = Depends(get_engine)
) -> BatchExtractionResponse:
    """
    Extract headers from multiple documents in batch.
    
    Limits:
    - Maximum 100 documents per request
    - Each document up to 10,000 OCR lines
    
    Returns:
    - Results for each document
    - Total processing time
    - Success count
    """
    if len(request.documents) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 documents per batch")

    start_time = time.time()
    results = []
    success_count = 0

    for doc_request in request.documents:
        try:
            # Parse field types
            field_types = None
            if doc_request.field_types:
                field_types = [InvoiceFieldType(ft.value) for ft in doc_request.field_types]

            # Extract
            output = engine.extract_invoice_header(
                ocr_lines=doc_request.ocr_lines,
                field_types=field_types,
                ocr_confidence_scores=doc_request.ocr_confidence_scores
            )

            # Convert to schema
            fields_response = {
                InvoiceFieldTypeSchema(ft.value): _convert_result_to_schema(result)
                for ft, result in output.fields.items()
            }

            response = HeaderExtractionResponse(
                fields=fields_response,
                overall_confidence=output.overall_confidence,
                extracted_at_stage=ExtractionStageSchema(output.extracted_at_stage.value),
                processing_time_ms=output.processing_time_ms
            )

            results.append(response)

            if output.fields:
                success_count += 1

            _record_statistics(response)

        except Exception as e:
            # Include blank result for failed documents
            results.append(HeaderExtractionResponse(
                fields={},
                overall_confidence=0.0,
                extracted_at_stage=ExtractionStageSchema("stage_1_template"),
                processing_time_ms=0.0
            ))

    total_time = (time.time() - start_time) * 1000

    return BatchExtractionResponse(
        results=results,
        total_processed=len(request.documents),
        total_time_ms=total_time,
        success_count=success_count
    )


@router.get(
    "/config",
    response_model=ExtractionEngineConfig,
    summary="Get engine configuration"
)
async def get_configuration(engine: HeaderExtractionEngine = Depends(get_engine)) -> ExtractionEngineConfig:
    """Get current extraction engine configuration."""
    return ExtractionEngineConfig(
        enable_template=engine.template_extractor is not None,
        enable_regex=engine.regex_extractor is not None,
        enable_ml=engine.ml_extractor is not None,
        enable_llm=engine.enable_llm,
        confidence_threshold_template=0.5,
        confidence_threshold_regex=0.4,
        confidence_threshold_llm=engine.confidence_threshold_for_llm
    )


@router.post(
    "/config",
    response_model=ExtractionEngineConfig,
    summary="Update engine configuration"
)
async def update_configuration(
    config: ExtractionEngineConfig
) -> ExtractionEngineConfig:
    """Update extraction engine configuration."""
    global _engine

    _engine = create_extraction_engine(
        enable_template=config.enable_template,
        enable_regex=config.enable_regex,
        enable_ml=config.enable_ml,
        enable_llm=config.enable_llm,
        llm_api_key=config.llm_api_key,
        confidence_threshold_for_llm=config.confidence_threshold_llm
    )

    return config


@router.get(
    "/statistics",
    response_model=ExtractionStatisticsResponse,
    summary="Get extraction statistics"
)
async def get_statistics() -> ExtractionStatisticsResponse:
    """Get extraction statistics and performance metrics."""
    global _statistics

    # Calculate field success rates
    field_success_rates = {}
    for field_type in InvoiceFieldType:
        field_key = field_type.value
        stats = _statistics["field_stats"][field_key]
        if stats["total"] > 0:
            success_rate = stats["found"] / stats["total"]
        else:
            success_rate = 0.0
        field_success_rates[field_type] = success_rate

    # Calculate average confidence
    total_found = sum(s["found"] for s in _statistics["field_stats"].values())
    total_confidence_sum = sum(s["confidence_sum"] for s in _statistics["field_stats"].values())

    if total_found > 0:
        average_confidence = total_confidence_sum / total_found
    else:
        average_confidence = 0.0

    # Calculate average processing time
    if _statistics["total_requests"] > 0:
        average_processing_time = _statistics["total_processing_time_ms"] / _statistics["total_requests"]
    else:
        average_processing_time = 0.0

    # Convert stage stats
    stage_distribution = {
        "stage_1_template": _statistics["stage_stats"].get("stage_1_template", 0),
        "stage_2_regex": _statistics["stage_stats"].get("stage_2_regex", 0),
        "stage_3_ml": _statistics["stage_stats"].get("stage_3_ml", 0),
        "stage_4_llm": _statistics["stage_stats"].get("stage_4_llm", 0),
    }

    return ExtractionStatisticsResponse(
        total_requests=_statistics["total_requests"],
        total_fields_extracted=total_found,
        average_confidence=average_confidence,
        average_processing_time_ms=average_processing_time,
        field_success_rate=field_success_rates,
        stage_distribution=stage_distribution
    )


@router.get(
    "/statistics/field/{field_type}",
    response_model=FieldConfidenceReport,
    summary="Get statistics for specific field"
)
async def get_field_statistics(field_type: InvoiceFieldTypeSchema) -> FieldConfidenceReport:
    """Get detailed statistics for specific field type."""
    global _statistics

    field_key = field_type.value
    stats = _statistics["field_stats"][field_key]

    # Calculate success rate
    if stats["total"] > 0:
        success_rate = stats["found"] / stats["total"]
        average_confidence = stats["confidence_sum"] / stats["found"] if stats["found"] > 0 else 0.0
    else:
        success_rate = 0.0
        average_confidence = 0.0

    # Create confidence distribution (placeholder)
    confidence_distribution = {
        "0.0-0.25": 0,
        "0.25-0.5": 0,
        "0.5-0.75": 0,
        "0.75-1.0": stats["found"]
    }

    return FieldConfidenceReport(
        field_type=field_type,
        total_extractions=stats["total"],
        total_found=stats["found"],
        success_rate=success_rate,
        average_confidence=average_confidence,
        confidence_distribution=confidence_distribution
    )


@router.get(
    "/health",
    summary="Health check",
    description="Check if extraction engine is operational"
)
async def health_check(engine: HeaderExtractionEngine = Depends(get_engine)) -> Dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "operational",
        "template_enabled": engine.template_extractor is not None,
        "regex_enabled": engine.regex_extractor is not None,
        "ml_enabled": engine.ml_extractor is not None,
        "llm_enabled": engine.enable_llm
    }


# ====== HELPER FUNCTIONS ======

def auto_extract_invoice_header(
    ocr_lines: List[str],
    field_types: Optional[List[InvoiceFieldType]] = None
) -> Dict[str, any]:
    """
    Helper function for pipeline integration.
    Automatically extract invoice headers without API call.
    
    Example:
        result = auto_extract_invoice_header(ocr_lines)
        print(result["fields"]["invoice_number"]["value"])
    """
    engine = get_engine()
    output = engine.extract_invoice_header(ocr_lines=ocr_lines, field_types=field_types)

    return {
        "fields": {
            ft.value: {
                "value": result.value,
                "confidence": result.confidence,
                "source": result.source.value,
                "stage": result.stage.value,
                "bbox": result.bbox.__dict__ if result.bbox else None,
                "evidence": result.evidence
            }
            for ft, result in output.fields.items()
        },
        "overall_confidence": output.overall_confidence,
        "extracted_at_stage": output.extracted_at_stage.value,
        "processing_time_ms": output.processing_time_ms
    }
