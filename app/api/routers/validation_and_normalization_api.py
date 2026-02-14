"""
REST API endpoints for validation and normalization service.

Endpoints:
- POST /api/validate/document - Validate single document
- POST /api/validate/batch - Validate multiple documents
- GET /api/validate/config - Get validation config
- POST /api/validate/config - Update validation config
- GET /api/validate/statistics - View validation statistics
- GET /api/validate/health - Health check
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import Dict, Any, List, Optional
from datetime import datetime
import time

from backend.app.services.validation_and_normalization import (
    create_validation_engine,
    ValidationAndNormalizationEngine,
)
from backend.app.schemas.validation_and_normalization import (
    ValidationRequestSchema,
    DocumentValidationSchema,
    BatchValidationRequestSchema,
    BatchValidationResponseSchema,
    ValidationConfigSchema,
    ValidationStatisticsSchema,
)


# ====== MODULE STATE ======

_engine: Optional[ValidationAndNormalizationEngine] = None
_config: ValidationConfigSchema = ValidationConfigSchema()
_statistics: Dict[str, Any] = {
    "total_documents_validated": 0,
    "total_fields_validated": 0,
    "valid_fields_count": 0,
    "invalid_fields_count": 0,
    "fields_needing_review_count": 0,
    "confidence_adjustments": [],
    "date_fields": {"valid": 0, "invalid": 0, "total": 0},
    "currency_fields": {"valid": 0, "invalid": 0, "total": 0},
    "tax_id_fields": {"valid": 0, "invalid": 0, "total": 0},
    "thai_dates_found": 0,
    "thai_digits_converted": 0,
    "buddhist_years_converted": 0,
    "processing_times": [],
}


# ====== ROUTER ======

router = APIRouter(
    prefix="/api/validate",
    tags=["validation"],
    responses={400: {"description": "Validation error"}, 500: {"description": "Server error"}},
)


# ====== DEPENDENCIES ======

def get_engine() -> ValidationAndNormalizationEngine:
    """Get (or create) validation engine singleton."""
    global _engine
    if _engine is None:
        _engine = create_validation_engine()
    return _engine


# ====== HELPER FUNCTIONS ======

def _record_statistics(report: Dict[str, Any]) -> None:
    """Record statistics about validation operation."""
    _statistics["total_documents_validated"] += 1
    _statistics["total_fields_validated"] += report.get("validation_count", 0)
    _statistics["valid_fields_count"] += report.get("valid_count", 0)
    _statistics["invalid_fields_count"] += report.get("invalid_count", 0)
    _statistics["fields_needing_review_count"] += report.get("needs_review_count", 0)
    _statistics["confidence_adjustments"].append(report.get("overall_confidence_adjustment", 0.0))

    # Record by field type
    for result in report.get("results", []):
        field_type = result.get("evidence", {}).get("field_type", "unknown")
        is_valid = result.get("is_valid", False)

        if field_type == "date":
            _statistics["date_fields"]["total"] += 1
            if is_valid:
                _statistics["date_fields"]["valid"] += 1
            else:
                _statistics["date_fields"]["invalid"] += 1
        elif field_type == "currency":
            _statistics["currency_fields"]["total"] += 1
            if is_valid:
                _statistics["currency_fields"]["valid"] += 1
            else:
                _statistics["currency_fields"]["invalid"] += 1
        elif field_type == "tax_id":
            _statistics["tax_id_fields"]["total"] += 1
            if is_valid:
                _statistics["tax_id_fields"]["valid"] += 1
            else:
                _statistics["tax_id_fields"]["invalid"] += 1


# ====== ENDPOINTS ======

@router.post("/document", response_model=DocumentValidationSchema)
async def validate_document(
    request: ValidationRequestSchema,
    engine: ValidationAndNormalizationEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """
    Validate and normalize a single document.
    
    Takes extracted field values, validates them, normalizes Thai dates/currency,
    and returns updated document with confidence adjustments.
    
    Args:
        request: Document with fields to validate
        engine: Validation engine
        
    Returns:
        Validated and normalized document
        
    Raises:
        400: If document data is invalid
        500: If validation fails unexpectedly
    """
    try:
        start_time = time.time()

        # Build document dict from request
        document = {
            "id": request.document_id,
            **request.fields,
        }

        # Add original confidences if provided
        if request.confidences:
            document["confidence"] = request.confidences

        # Validate and normalize
        report, updated_doc = engine.validate_document_fields(document)

        processing_time = (time.time() - start_time) * 1000

        # Record statistics
        report_dict = {
            "validation_count": report.validation_count,
            "valid_count": report.valid_count,
            "invalid_count": report.invalid_count,
            "needs_review_count": report.needs_review_count,
            "overall_confidence_adjustment": report.overall_confidence_adjustment,
            "results": [
                {
                    "field_name": r.field_name,
                    "is_valid": r.is_valid,
                    "evidence": r.evidence,
                }
                for r in report.results
            ],
        }
        _record_statistics(report_dict)
        _statistics["processing_times"].append(processing_time)

        # Build response
        response = {
            "document_id": request.document_id,
            "overall_valid": report.overall_valid,
            "validation_timestamp": report.timestamp,
            "total_fields_validated": report.validation_count,
            "valid_fields_count": report.valid_count,
            "invalid_fields_count": report.invalid_count,
            "fields_needing_review": report.fields_needing_review,
            "overall_confidence_adjustment": report.overall_confidence_adjustment,
            "field_results": [
                {
                    "field_name": r.field_name,
                    "original_value": r.original_value,
                    "normalized_value": r.normalized_value,
                    "status": r.status,
                    "is_valid": r.is_valid,
                    "confidence_adjustment": r.confidence_adjustment,
                    "needs_review": r.needs_review,
                    "error_message": r.error_message,
                    "evidence": r.evidence,
                }
                for r in report.results
            ],
            "normalized_document": updated_doc,
        }

        return response

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.post("/batch", response_model=BatchValidationResponseSchema)
async def validate_batch(
    request: BatchValidationRequestSchema,
    engine: ValidationAndNormalizationEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """
    Validate and normalize multiple documents (batch).
    
    Args:
        request: List of documents (max 100)
        engine: Validation engine
        
    Returns:
        Batch validation results
        
    Raises:
        400: If batch data is invalid
        500: If validation fails
    """
    try:
        start_time = time.time()
        results = []
        failed_count = 0

        for doc_req in request.documents:
            try:
                # Build document
                document = {
                    "id": doc_req.document_id,
                    **doc_req.fields,
                }

                if doc_req.confidences:
                    document["confidence"] = doc_req.confidences

                # Validate
                report, updated_doc = engine.validate_document_fields(document)

                # Record stats
                report_dict = {
                    "validation_count": report.validation_count,
                    "valid_count": report.valid_count,
                    "invalid_count": report.invalid_count,
                    "needs_review_count": report.needs_review_count,
                    "overall_confidence_adjustment": report.overall_confidence_adjustment,
                    "results": [
                        {
                            "field_name": r.field_name,
                            "is_valid": r.is_valid,
                            "evidence": r.evidence,
                        }
                        for r in report.results
                    ],
                }
                _record_statistics(report_dict)

                # Build result
                result = {
                    "document_id": doc_req.document_id,
                    "overall_valid": report.overall_valid,
                    "validation_timestamp": report.timestamp,
                    "total_fields_validated": report.validation_count,
                    "valid_fields_count": report.valid_count,
                    "invalid_fields_count": report.invalid_count,
                    "fields_needing_review": report.fields_needing_review,
                    "overall_confidence_adjustment": report.overall_confidence_adjustment,
                    "field_results": [
                        {
                            "field_name": r.field_name,
                            "original_value": r.original_value,
                            "normalized_value": r.normalized_value,
                            "status": r.status,
                            "is_valid": r.is_valid,
                            "confidence_adjustment": r.confidence_adjustment,
                            "needs_review": r.needs_review,
                            "error_message": r.error_message,
                            "evidence": r.evidence,
                        }
                        for r in report.results
                    ],
                    "normalized_document": updated_doc,
                }

                results.append(result)

                if not report.overall_valid and request.fail_fast:
                    failed_count += 1
                    break

            except Exception as e:
                failed_count += 1
                if request.fail_fast:
                    break

        processing_time = (time.time() - start_time) * 1000
        _statistics["processing_times"].append(processing_time)

        return {
            "total_documents": len(request.documents),
            "successful_count": len(results),
            "failed_count": failed_count,
            "results": results,
            "processing_time_ms": processing_time,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch validation failed: {str(e)}")


@router.get("/config", response_model=ValidationConfigSchema)
async def get_config() -> Dict[str, Any]:
    """
    Get current validation configuration.
    
    Returns:
        Current validation settings
    """
    return _config.model_dump()


@router.post("/config", response_model=ValidationConfigSchema)
async def update_config(
    config: ValidationConfigSchema,
) -> Dict[str, Any]:
    """
    Update validation configuration.
    
    Args:
        config: New configuration
        
    Returns:
        Updated configuration
    """
    global _config
    _config = config
    return _config.model_dump()


@router.get("/statistics", response_model=ValidationStatisticsSchema)
async def get_statistics() -> Dict[str, Any]:
    """
    Get validation statistics.
    
    Returns statistics about all validation operations performed.
    """
    # Calculate derived statistics
    conf_adjustments = _statistics.get("confidence_adjustments", [])
    mean_conf_adj = sum(conf_adjustments) / len(conf_adjustments) if conf_adjustments else 0.0

    # Sort for median
    sorted_conf = sorted(conf_adjustments) if conf_adjustments else [0.0]
    n = len(sorted_conf)
    median_conf_adj = (
        sorted_conf[n // 2]
        if n % 2 == 1
        else (sorted_conf[n // 2 - 1] + sorted_conf[n // 2]) / 2
    )

    return {
        "total_documents_validated": _statistics["total_documents_validated"],
        "total_fields_validated": _statistics["total_fields_validated"],
        "valid_fields_count": _statistics["valid_fields_count"],
        "invalid_fields_count": _statistics["invalid_fields_count"],
        "mean_confidence_adjustment": mean_conf_adj,
        "median_confidence_adjustment": median_conf_adj,
        "date_fields_validated": _statistics["date_fields"]["total"],
        "date_fields_valid": _statistics["date_fields"]["valid"],
        "currency_fields_validated": _statistics["currency_fields"]["total"],
        "currency_fields_valid": _statistics["currency_fields"]["valid"],
        "tax_id_fields_validated": _statistics["tax_id_fields"]["total"],
        "tax_id_fields_valid": _statistics["tax_id_fields"]["valid"],
        "thai_dates_found": _statistics["thai_dates_found"],
        "thai_digits_converted": _statistics["thai_digits_converted"],
        "buddhist_years_converted": _statistics["buddhist_years_converted"],
        "validation_timestamp": datetime.now(),
    }


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint.
    
    Returns:
        Health status
    """
    return {"status": "healthy", "service": "validation-and-normalization"}
