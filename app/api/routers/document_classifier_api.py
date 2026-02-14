"""
Document Classification API Endpoints

REST API for document type classification with keyword and ML methods.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import get_current_user, get_session
from app.models import User
from app.schemas.document_classification import (
    ClassifierConfigRequest,
    DocumentClassificationRequest,
    DocumentClassificationResponse,
)
from app.services.document_classifier import (
    create_classifier,
    DocumentType,
    KeywordSet,
)

# Module-level state
_classifier = None
_classifier_config = {
    "classifier_type": "hybrid",
    "use_ml": False,
}


def get_classifier():
    """
    Get or create the document classifier instance.

    Uses lazy initialization and caching to avoid recreating on every request.
    """
    global _classifier
    if _classifier is None:
        _classifier = create_classifier(
            classifier_type=_classifier_config["classifier_type"],
            use_ml=_classifier_config["use_ml"],
        )
    return _classifier


def _reset_classifier():
    """Reset cached classifier (used when config changes)."""
    global _classifier
    _classifier = None


router = APIRouter(prefix="/api/classify", tags=["document-classification"])


@router.post("/document", response_model=DocumentClassificationResponse)
async def classify_document(
    request: DocumentClassificationRequest,
    current_user: User = Depends(get_current_user),
) -> DocumentClassificationResponse:
    """
    Classify a document based on OCR output.

    Supports both keyword-based and hybrid (keyword + ML fallback) classification.

    **Input Parameters:**
    - `ocr_lines`: List of text lines from OCR
    - `header_text`: Optional combined header text
    - `keyword_frequency`: Optional pre-computed keyword counts
    - `classifier_type`: "keyword" or "hybrid"

    **Output:**
    - `document_type`: Detected type (invoice, receipt, purchase_order, tax_invoice, unknown)
    - `confidence_score`: 0.0-1.0 confidence value
    - `matched_keywords`: Keywords matching the detected type
    - `evidence`: Details about classification method used
    - `raw_scores`: Scores for all document types

    **Example Request:**
    ```json
    {
        "ocr_lines": [
            "INVOICE",
            "Invoice Number: INV-2026-001",
            "Date: 2026-02-13",
            "Total: 5,000.00"
        ],
        "header_text": "ACME Corp Invoice",
        "classifier_type": "hybrid"
    }
    ```

    **Example Response:**
    ```json
    {
        "document_type": "invoice",
        "confidence_score": 0.92,
        "matched_keywords": {
            "invoice": ["invoice", "invoice number", "total"]
        },
        "evidence": {
            "method": "keyword_high_confidence",
            "threshold": 0.25
        },
        "raw_scores": {
            "invoice": 4.2,
            "receipt": 0.9,
            "purchase_order": 1.5,
            "tax_invoice": 3.8,
            "unknown": 0.0
        }
    }
    ```
    """
    if not request.ocr_lines:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="ocr_lines cannot be empty"
        )

    classifier = get_classifier()

    try:
        result = classifier.classify(
            ocr_lines=request.ocr_lines, header_text=request.header_text
        )

        return DocumentClassificationResponse(
            document_type=result.document_type.value,
            confidence_score=result.confidence_score,
            matched_keywords=result.matched_keywords,
            evidence=result.evidence,
            raw_scores=result.raw_scores,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Classification failed: {str(e)}",
        )


@router.post("/batch")
async def classify_batch(
    requests: list[DocumentClassificationRequest],
    current_user: User = Depends(get_current_user),
) -> list[DocumentClassificationResponse]:
    """
    Classify multiple documents in batch.

    Useful for processing queued or historical documents.

    **Input:** List of classification requests

    **Output:** List of classification responses (same order as input)

    Note: Processing continues even if individual classifications fail.
    Errors are included in responses with document_type="unknown".
    """
    if not requests:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one request is required",
        )

    if len(requests) > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 1000 documents per batch",
        )

    classifier = get_classifier()
    results = []

    for req in requests:
        try:
            if not req.ocr_lines:
                results.append(
                    DocumentClassificationResponse(
                        document_type="unknown",
                        confidence_score=0.0,
                        matched_keywords={},
                        evidence={"error": "empty_ocr_lines"},
                    )
                )
                continue

            result = classifier.classify(
                ocr_lines=req.ocr_lines, header_text=req.header_text
            )

            results.append(
                DocumentClassificationResponse(
                    document_type=result.document_type.value,
                    confidence_score=result.confidence_score,
                    matched_keywords=result.matched_keywords,
                    evidence=result.evidence,
                    raw_scores=result.raw_scores,
                )
            )
        except Exception as e:
            results.append(
                DocumentClassificationResponse(
                    document_type="unknown",
                    confidence_score=0.0,
                    matched_keywords={},
                    evidence={"error": str(e)},
                )
            )

    return results


@router.get("/keywords/{document_type}")
async def get_keywords(
    document_type: Literal[
        "invoice", "receipt", "purchase_order", "tax_invoice"
    ],
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Get keyword configuration for a document type.

    Useful for understanding classifier behavior and for debugging.

    **Returns:**
    - `primary_keywords`: High-confidence keywords (weight 1.0)
    - `secondary_keywords`: Medium-confidence keywords (weight 0.6)
    - `tertiary_keywords`: Low-confidence keywords (weight 0.3)
    - `negative_keywords`: Keywords that reject this type
    - `scoring_explanation`: How keywords are scored

    **Example Response:**
    ```json
    {
        "name": "invoice",
        "primary_keywords": ["invoice", "ใบแจ้งหนี้"],
        "secondary_keywords": ["bill", "vendor", "customer"],
        "tertiary_keywords": ["amount", "price", "quantity"],
        "negative_keywords": ["receipt", "cash register"],
        "weights": {
            "primary": 1.0,
            "secondary": 0.6,
            "tertiary": 0.3,
            "negative": -2.0
        },
        "minimum_score_threshold": 0.25
    }
    ```
    """
    keyword_set_map = {
        "invoice": KeywordSet.for_invoice(),
        "receipt": KeywordSet.for_receipt(),
        "purchase_order": KeywordSet.for_purchase_order(),
        "tax_invoice": KeywordSet.for_tax_invoice(),
    }

    keyword_set = keyword_set_map.get(document_type)
    if not keyword_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown document type: {document_type}",
        )

    return {
        "name": keyword_set.name,
        "primary_keywords": keyword_set.primary_keywords,
        "secondary_keywords": keyword_set.secondary_keywords,
        "tertiary_keywords": keyword_set.tertiary_keywords,
        "negative_keywords": keyword_set.negative_keywords,
        "weights": {
            "primary": 1.0,
            "secondary": 0.6,
            "tertiary": 0.3,
            "negative": -2.0,
        },
        "minimum_score_threshold": keyword_set.minimum_score_threshold,
        "scoring_explanation": "Score = (primary_count * 1.0) + (secondary_count * 0.6) + (tertiary_count * 0.3) - (negative_count * 2.0)",
    }


@router.post("/configure")
async def configure_classifier(
    config: ClassifierConfigRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Configure classifier behavior.

    **Parameters:**
    - `classifier_type`: "keyword" (fast, rule-based) or "hybrid" (keyword + ML fallback)
    - `use_ml_fallback`: Whether to use ML when keyword confidence is low
    - `confidence_threshold_low`: Below this score, try ML classifier
    - `confidence_threshold_high`: Above this, accept keyword result immediately

    **Configuration Strategy:**
    - For high precision: Set threshold_high to 0.85+
    - For high recall: Set threshold_low to 0.2 and use_ml_fallback=true
    - For speed: Use "keyword" only
    - For balanced: Use "hybrid" with defaults

    **Example:**
    ```json
    {
        "classifier_type": "hybrid",
        "use_ml_fallback": true,
        "confidence_threshold_low": 0.35,
        "confidence_threshold_high": 0.85
    }
    ```
    """
    if config.confidence_threshold_low > config.confidence_threshold_high:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="threshold_low must be <= threshold_high",
        )

    global _classifier_config
    _classifier_config = {
        "classifier_type": config.classifier_type,
        "use_ml": config.use_ml_fallback,
    }

    _reset_classifier()

    return {
        "status": "configured",
        "classifier_type": config.classifier_type,
        "use_ml_fallback": config.use_ml_fallback,
        "confidence_threshold_low": config.confidence_threshold_low,
        "confidence_threshold_high": config.confidence_threshold_high,
    }


@router.get("/health")
async def classifier_health(
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Check classifier health and readiness.

    **Response:**
    - `status`: "ready" or "error"
    - `classifier_type`: Current classifier type
    - `last_error`: Last error if any
    """
    try:
        classifier = get_classifier()
        return {
            "status": "ready",
            "classifier_type": _classifier_config["classifier_type"],
            "use_ml_fallback": _classifier_config["use_ml"],
        }
    except Exception as e:
        return {
            "status": "error",
            "last_error": str(e),
            "classifier_type": _classifier_config["classifier_type"],
        }


# Optional: Integration with document processing workflow
# This would be called after OCR is complete


async def auto_classify_from_ocr(
    ocr_lines: list[str], header_text: str | None = None
) -> DocumentType:
    """
    Helper function to classify document from OCR results.

    Can be called from OCR processing pipeline.

    Args:
        ocr_lines: OCR extracted lines
        header_text: Optional header text

    Returns:
        Detected document type
    """
    classifier = get_classifier()
    result = classifier.classify(ocr_lines=ocr_lines, header_text=header_text)
    return result.document_type


# Note: To integrate these endpoints into your application:
# 1. Import this router in your main.py or API router setup:
#
#    from app.api.routers import document_classifier_api
#    app.include_router(document_classifier_api.router)
#
# 2. Endpoints will be available at:
#    POST /api/classify/document
#    POST /api/classify/batch
#    GET  /api/classify/keywords/{document_type}
#    POST /api/classify/configure
#    GET  /api/classify/health
