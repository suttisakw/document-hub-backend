"""
Confidence Routing API Router

Routes documents based on confidence scores:
- confidence > 0.85 → auto approve
- 0.6–0.85 → flag for review
- < 0.6 → force manual review

Apply to: header fields, table rows, whole document
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from datetime import datetime
import logging

from app.schemas.confidence_routing import (
    ConfidenceRoutingRequest,
    ConfidenceRoutingResponse,
    BulkRoutingRequest,
    BulkRoutingResponse,
    RoutingRule,
    RoutingStatus,
)
from app.services.confidence_routing_service import ConfidenceRoutingService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/documents/routing",
    tags=["routing"],
    responses={
        404: {"description": "Document not found"},
        422: {"description": "Invalid request"},
    },
)

# Initialize service
routing_service = ConfidenceRoutingService()


@router.get("/info")
async def get_routing_info() -> dict:
    """
    Get information about confidence routing.
    
    Returns:
    - Available routing rules (default, strict, lenient)
    - Confidence thresholds
    - Routing statuses
    - Feature capabilities
    """
    rules = routing_service.get_routing_rules()
    
    return {
        "available_rules": list(rules.keys()),
        "default_rule": "default",
        "confidence_thresholds": {
            "default": {
                "high_confidence": (
                    f"> {rules['default'].high_confidence_threshold}"
                ),
                "medium_confidence": (
                    f"{rules['default'].medium_confidence_threshold} - "
                    f"{rules['default'].high_confidence_threshold}"
                ),
                "low_confidence": (
                    f"< {rules['default'].medium_confidence_threshold}"
                ),
            }
        },
        "routing_statuses": [s.value for s in RoutingStatus],
        "features": {
            "header_field_routing": True,
            "table_row_routing": True,
            "document_confidence_routing": True,
            "corrected_field_tracking": True,
            "bulk_routing": True,
            "custom_rules": True,
        },
    }


@router.post("/route")
async def route_document(request: ConfidenceRoutingRequest) -> ConfidenceRoutingResponse:
    """
    Route a single document based on confidence scores.
    
    Routes document to: approved, review_required, or rejected
    based on confidence thresholds.
    
    Applies routing to:
    1. Header fields - individual field confidence scores
    2. Table rows - per-row and per-field confidence scores
    3. Document score - overall document confidence
    
    Example:
    ```json
    {
        "document_id": "doc_123",
        "document_type": "invoice",
        "extracted_fields": {
            "invoice_number": "INV-001",
            "invoice_date": "2026-02-13",
            "total_amount": "1500.00"
        },
        "field_confidences": {
            "invoice_number": 0.95,
            "invoice_date": 0.92,
            "total_amount": 0.75
        },
        "document_confidence": 0.88,
        "routing_rule": "default"
    }
    ```
    
    Response:
    ```json
    {
        "document_id": "doc_123",
        "routing_status": "approved",
        "confidence_score": {...},
        "requires_attention": false,
        "recommended_actions": [
            "Document automatically approved - proceed to processing"
        ]
    }
    ```
    """
    try:
        response = routing_service.route_document(request)
        return response
    except Exception as e:
        logger.error(f"Error routing document {request.document_id}: {e}")
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/route/bulk")
async def route_bulk_documents(request: BulkRoutingRequest) -> BulkRoutingResponse:
    """
    Route multiple documents at once.
    
    Batch process documents with same routing rule.
    
    Example:
    ```json
    {
        "requests": [
            {
                "document_id": "doc_1",
                "document_type": "invoice",
                "extracted_fields": {...},
                "field_confidences": {...},
                "document_confidence": 0.88
            },
            {
                "document_id": "doc_2",
                ...
            }
        ],
        "routing_rule": "default"
    }
    ```
    
    Returns:
    - batch_id: Identifier for tracking
    - total_documents: Number processed
    - approved/review_required/rejected: Counts by status
    - results: List of individual routing responses
    """
    try:
        response = routing_service.route_bulk_documents(
            request.requests,
            request.routing_rule
        )
        logger.info(
            f"Bulk routing completed: batch_id={response.batch_id}, "
            f"approved={response.approved}, "
            f"review_required={response.review_required}, "
            f"rejected={response.rejected}"
        )
        return response
    except Exception as e:
        logger.error(f"Error in bulk routing: {e}")
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/statistics")
async def get_routing_statistics(
    days: Optional[int] = None
) -> dict:
    """
    Get routing statistics.
    
    Returns:
    - Total documents routed
    - Count by status (approved, review_required, rejected)
    - Approval/review/rejection rates
    - Confidence distribution
    """
    stats = routing_service.get_statistics(days)
    
    return {
        **stats,
        "timestamp": datetime.utcnow().isoformat(),
        "interpretation": {
            "high_approval_rate": stats["approval_rate"] > 0.7,
            "high_rejection_rate": stats["rejection_rate"] > 0.2,
            "balanced_review_queue": (
                0.2 < stats["review_rate"] < 0.5
            ),
        }
    }


@router.get("/rules")
async def list_routing_rules() -> dict:
    """
    List all available routing rules.
    
    Returns details for each rule:
    - high_confidence_threshold
    - medium_confidence_threshold
    - low_confidence_action
    - which components to apply to
    """
    rules = routing_service.get_routing_rules()
    
    rules_dict = {}
    for rule_name, rule_obj in rules.items():
        rules_dict[rule_name] = {
            "name": rule_obj.name,
            "high_confidence_threshold": rule_obj.high_confidence_threshold,
            "medium_confidence_threshold": rule_obj.medium_confidence_threshold,
            "low_confidence_action": rule_obj.low_confidence_action,
            "apply_to_header": rule_obj.apply_to_header,
            "apply_to_rows": rule_obj.apply_to_rows,
            "apply_to_document": rule_obj.apply_to_document,
            "require_all_approved": rule_obj.require_all_approved,
        }
    
    return {
        "available_rules": rules_dict,
        "total_rules": len(rules),
        "default_rule": "default",
    }


@router.get("/rules/{rule_name}")
async def get_routing_rule(rule_name: str) -> dict:
    """Get details for a specific routing rule."""
    rules = routing_service.get_routing_rules()
    
    if rule_name not in rules:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_name}' not found")
    
    rule = rules[rule_name]
    return {
        "name": rule.name,
        "high_confidence_threshold": rule.high_confidence_threshold,
        "medium_confidence_threshold": rule.medium_confidence_threshold,
        "low_confidence_action": rule.low_confidence_action,
        "apply_to_header": rule.apply_to_header,
        "apply_to_rows": rule.apply_to_rows,
        "apply_to_document": rule.apply_to_document,
        "require_all_approved": rule.require_all_approved,
    }


@router.post("/rules")
async def create_routing_rule(rule: RoutingRule) -> dict:
    """
    Create or update a routing rule.
    
    Example:
    ```json
    {
        "name": "custom_rule",
        "high_confidence_threshold": 0.88,
        "medium_confidence_threshold": 0.65,
        "low_confidence_action": "review",
        "apply_to_header": true,
        "apply_to_rows": true,
        "apply_to_document": true,
        "require_all_approved": false
    }
    ```
    """
    try:
        routing_service.add_or_update_rule(rule)
        return {
            "status": "success",
            "message": f"Rule '{rule.name}' created/updated",
            "rule": {
                "name": rule.name,
                "high_confidence_threshold": rule.high_confidence_threshold,
                "medium_confidence_threshold": rule.medium_confidence_threshold,
            }
        }
    except Exception as e:
        logger.error(f"Error creating rule '{rule.name}': {e}")
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/rules/{rule_name}")
async def delete_routing_rule(rule_name: str) -> dict:
    """Delete a routing rule."""
    if rule_name in ["default", "strict", "lenient"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete built-in rules (default, strict, lenient)"
        )
    
    success = routing_service.delete_rule(rule_name)
    
    if success:
        return {
            "status": "success",
            "message": f"Rule '{rule_name}' deleted"
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Rule '{rule_name}' not found"
        )


@router.post("/validate")
async def validate_confidence_scores(
    document_id: str,
    field_confidences: dict
) -> dict:
    """
    Validate confidence scores for a document.
    
    Check if all field confidences are within valid range [0, 1].
    
    Query parameters:
    - document_id: Document identifier
    - field_confidences: Map of field_name -> confidence_score
    """
    try:
        invalid_fields = []
        
        for field_name, confidence in field_confidences.items():
            if not isinstance(confidence, (int, float)):
                invalid_fields.append(
                    f"{field_name}: not a number"
                )
            elif confidence < 0.0 or confidence > 1.0:
                invalid_fields.append(
                    f"{field_name}: {confidence} not in range [0, 1]"
                )
        
        is_valid = len(invalid_fields) == 0
        
        return {
            "document_id": document_id,
            "is_valid": is_valid,
            "total_fields": len(field_confidences),
            "invalid_count": len(invalid_fields),
            "invalid_fields": invalid_fields,
        }
    except Exception as e:
        logger.error(f"Error validating confidence scores: {e}")
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/thresholds")
async def get_confidence_thresholds() -> dict:
    """
    Get confidence thresholds for all rules.
    
    Shows:
    - Auto approve threshold (high confidence)
    - Manual review threshold (medium confidence)
    - Force manual review threshold (low confidence)
    """
    rules = routing_service.get_routing_rules()
    
    thresholds = {}
    for rule_name, rule in rules.items():
        thresholds[rule_name] = {
            "auto_approve": f"> {rule.high_confidence_threshold}",
            "flag_for_review": f"{rule.medium_confidence_threshold} - {rule.high_confidence_threshold}",
            "force_manual_review": f"< {rule.medium_confidence_threshold}",
        }
    
    return {
        "thresholds_by_rule": thresholds,
        "routing_logic": {
            "approved": "Confidence > high_threshold (auto-routed)",
            "review_required": (
                "Confidence between medium and high (flagged for human review)"
            ),
            "rejected": (
                "Confidence < medium_threshold (requires manual intervention)"
            ),
        }
    }
