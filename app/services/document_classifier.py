"""
Document Type Classification Module

Provides a modular, pluggable document classification system using:
1. Keyword-based scoring (primary method)
2. Optional ML classifier fallback
3. Configurable classifiers for different document types

Supported document types:
- invoice: Sales invoice from vendor
- receipt: Point-of-sale or service receipt
- purchase_order: Purchase order / PO
- tax_invoice: Tax/VAT invoice (common in Thailand)
- unknown: Unable to classify
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Protocol

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    """Supported document types for classification."""

    INVOICE = "invoice"
    RECEIPT = "receipt"
    PURCHASE_ORDER = "purchase_order"
    TAX_INVOICE = "tax_invoice"
    UNKNOWN = "unknown"


@dataclass
class ClassificationResult:
    """Result of document classification."""

    document_type: DocumentType
    confidence_score: float  # 0.0 to 1.0
    matched_keywords: dict[str, list[str]]  # {doc_type: [keywords]}
    evidence: dict[str, Any]  # {method: details}
    raw_scores: dict[str, float]  # {doc_type: score}


class KeywordSet(BaseModel):
    """Configuration for keyword-based classification."""

    name: str = Field(..., description="Document type name")
    primary_keywords: list[str] = Field(
        ..., description="High-confidence keywords (weight 1.0)"
    )
    secondary_keywords: list[str] = Field(
        default_factory=list, description="Medium-confidence keywords (weight 0.6)"
    )
    tertiary_keywords: list[str] = Field(
        default_factory=list, description="Low-confidence keywords (weight 0.3)"
    )
    negative_keywords: list[str] = Field(
        default_factory=list, description="Keywords that reject this type"
    )
    minimum_score_threshold: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Minimum score to consider this type"
    )

    @classmethod
    def for_invoice(cls) -> KeywordSet:
        """Create keyword set for invoice detection."""
        return cls(
            name="invoice",
            primary_keywords=[
                "invoice",
                "ใบแจ้งหนี้",  # Thai: invoice
                "ืบแจ้งหนี้",  # Alt Thai spelling
                "invoice number",
                "inv",
                "inv-",
                "inv.",
            ],
            secondary_keywords=[
                "bill",
                "vendor",
                "supplier",
                "customer",
                "amount due",
                "total amount",
                "due date",
                "payment terms",
                "tax",
                "เลขที่",  # Thai: number
                "วันที่",  # Thai: date
                "ผู้ขาย",  # Thai: seller
                "ผู้ซื้อ",  # Thai: buyer
            ],
            tertiary_keywords=[
                "amount",
                "price",
                "quantity",
                "description",
                "total",
                "subtotal",
                "discount",
                "vat",
                "บาท",  # Thai: baht
                "จำนวน",  # Thai: quantity
                "ราคา",  # Thai: price
            ],
            negative_keywords=["receipt", "cash register", "pos", "store receipt"],
            minimum_score_threshold=0.25,
        )

    @classmethod
    def for_receipt(cls) -> KeywordSet:
        """Create keyword set for receipt detection."""
        return cls(
            name="receipt",
            primary_keywords=[
                "receipt",
                "ใบเสร็จ",  # Thai: receipt
                "ใบเสร็จรับเงิน",  # Thai: receipts
                "thank you",
                "paid",
                "cash",
                "payment received",
            ],
            secondary_keywords=[
                "store",
                "shop",
                "counter",
                "cashier",
                "transaction",
                "items",
                "subtotal",
                "change",
                "customer",
                "บริษัท",  # Thai: company/store
                "ขอบคุณ",  # Thai: thank you
                "ชำระแล้ว",  # Thai: paid
            ],
            tertiary_keywords=[
                "item",
                "qty",
                "price",
                "total",
                "amount",
                "date",
                "time",
                "number",
                "bill",
                "ราคา",  # Thai: price
                "จำนวน",  # Thai: quantity
                "วันที่",  # Thai: date
            ],
            negative_keywords=["invoice", "invoice number", "po", "purchase order"],
            minimum_score_threshold=0.2,
        )

    @classmethod
    def for_purchase_order(cls) -> KeywordSet:
        """Create keyword set for PO detection."""
        return cls(
            name="purchase_order",
            primary_keywords=[
                "purchase order",
                "po",
                "po.",
                "p.o.",
                "purchase requisition",
                "order form",
                "order number",
            ],
            secondary_keywords=[
                "vendor",
                "supplier",
                "ship to",
                "deliver to",
                "delivery date",
                "expected delivery",
                "terms",
                "condition",
                "order date",
                "requested by",
                "approved by",
                "ส่ง",  # Thai: ship
                "ผู้จัดจำหน่าย",  # Thai: supplier
            ],
            tertiary_keywords=[
                "item",
                "description",
                "quantity",
                "unit price",
                "total",
                "amount",
                "specification",
                "qty",
                "ราคา",  # Thai: price
                "จำนวน",  # Thai: quantity
                "รวม",  # Thai: total
            ],
            negative_keywords=["invoice", "receipt", "paid", "payment"],
            minimum_score_threshold=0.3,
        )

    @classmethod
    def for_tax_invoice(cls) -> KeywordSet:
        """Create keyword set for tax invoice detection (VAT invoice)."""
        return cls(
            name="tax_invoice",
            primary_keywords=[
                "tax",
                "vat",
                "vat invoice",
                "ใบกำกับภาษีอากร",  # Thai: vat/tax invoice
                "ใบแจ้งหนี้",  # Thai: tax invoice
                "tax id",
                "tax number",
                "tin",
                "เลขที่ประจำตัวผู้เสียภาษีอากร",  # Thai: tax id
            ],
            secondary_keywords=[
                "invoice",
                "bill",
                "tax rate",
                "total tax",
                "amount including tax",
                "net amount",
                "customer",
                "vendor",
                "ภาษีมูลค่าเพิ่ม",  # Thai: VAT
                "สำนักพิมพ์",  # Thai: print
                "ผู้เสียภาษี",  # Thai: taxpayer
            ],
            tertiary_keywords=[
                "amount",
                "total",
                "price",
                "item",
                "quantity",
                "date",
                "number",
                "by order",
                "authorized",
                "บาท",  # Thai: baht
                "รวม",  # Thai: total
            ],
            negative_keywords=["receipt", "pos", "cash register"],
            minimum_score_threshold=0.35,
        )


class ClassifierStrategy(Protocol):
    """Protocol for pluggable classifier strategies."""

    def classify(
        self, ocr_lines: list[str], header_text: str | None = None
    ) -> ClassificationResult:
        """
        Classify document type.

        Args:
            ocr_lines: Extracted OCR text lines
            header_text: Combined header text (optional)

        Returns:
            ClassificationResult with type and confidence
        """
        ...


class KeywordClassifier:
    """
    Keyword-based document classifier using configurable keyword sets.

    Scoring algorithm:
    1. Normalize and prepare text from OCR lines
    2. Count keyword matches at each weight level
    3. Calculate score for each document type
    4. Apply negative keyword penalties
    5. Normalize scores to 0.0-1.0 range
    """

    def __init__(self, keyword_sets: dict[str, KeywordSet] | None = None):
        """
        Initialize classifier with keyword sets.

        Args:
            keyword_sets: Dict mapping doc type names to KeywordSet configs.
                         If None, uses default sets for all supported types.
        """
        if keyword_sets is None:
            keyword_sets = {
                "invoice": KeywordSet.for_invoice(),
                "receipt": KeywordSet.for_receipt(),
                "purchase_order": KeywordSet.for_purchase_order(),
                "tax_invoice": KeywordSet.for_tax_invoice(),
            }
        self.keyword_sets = keyword_sets

    def classify(
        self, ocr_lines: list[str], header_text: str | None = None, **kwargs
    ) -> ClassificationResult:
        """
        Classify document using keyword scoring.

        Args:
            ocr_lines: List of OCR-extracted text lines
            header_text: Optional combined header text
            **kwargs: Additional arguments (ignored for compatibility)

        Returns:
            ClassificationResult with matched keywords and confidence
        """
        # Combine all text
        all_text = " ".join(ocr_lines)
        if header_text:
            all_text = f"{header_text} {all_text}"

        # Normalize text for matching
        normalized_text = self._normalize_text(all_text)

        # Score each document type
        scores: dict[str, float] = {}
        matched: dict[str, list[str]] = {}
        weights_used: dict[str, dict[str, int]] = {}

        for doc_type, keyword_set in self.keyword_sets.items():
            score, matches, weights = self._score_document_type(
                normalized_text, keyword_set
            )
            scores[doc_type] = score
            matched[doc_type] = matches
            weights_used[doc_type] = weights

        # Find best match
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        # Check if best match meets minimum threshold
        keyword_set = self.keyword_sets[best_type]
        if best_score < keyword_set.minimum_score_threshold:
            best_type = "unknown"
            best_score = 0.0
            matched = {}

        # Normalize score to 0.0-1.0
        normalized_score = min(1.0, max(0.0, best_score))

        # Build matched keywords dict (only for winning type)
        winning_matches = {}
        if best_type != "unknown":
            winning_matches = {best_type: matched[best_type]}

        return ClassificationResult(
            document_type=DocumentType(best_type),
            confidence_score=normalized_score,
            matched_keywords=winning_matches,
            evidence={
                "method": "keyword_matching",
                "threshold": keyword_set.minimum_score_threshold
                if best_type != "unknown"
                else 0.0,
            },
            raw_scores=scores,
        )

    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for keyword matching.

        Args:
            text: Raw text to normalize

        Returns:
            Normalized text (lowercase, spaces normalized)
        """
        # Convert to lowercase
        text = text.lower()
        # Normalize whitespace
        text = " ".join(text.split())
        return text

    def _score_document_type(
        self, normalized_text: str, keyword_set: KeywordSet
    ) -> tuple[float, list[str], dict[str, int]]:
        """
        Calculate score for a specific document type.

        Scoring weights:
        - Primary keywords: 1.0 points each
        - Secondary keywords: 0.6 points each
        - Tertiary keywords: 0.3 points each
        - Negative keywords: -2.0 penalty each

        Args:
            normalized_text: Normalized OCR text
            keyword_set: Keyword configuration for this type

        Returns:
            (score, matched_keywords_list, weight_counts)
        """
        score = 0.0
        matched_keywords: list[str] = []
        weights = {"primary": 0, "secondary": 0, "tertiary": 0, "negative": 0}

        # Score primary keywords (weight 1.0)
        for keyword in keyword_set.primary_keywords:
            if self._find_keyword(keyword, normalized_text):
                score += 1.0
                matched_keywords.append(keyword)
                weights["primary"] += 1

        # Score secondary keywords (weight 0.6)
        for keyword in keyword_set.secondary_keywords:
            if self._find_keyword(keyword, normalized_text):
                score += 0.6
                matched_keywords.append(keyword)
                weights["secondary"] += 1

        # Score tertiary keywords (weight 0.3)
        for keyword in keyword_set.tertiary_keywords:
            if self._find_keyword(keyword, normalized_text):
                score += 0.3
                matched_keywords.append(keyword)
                weights["tertiary"] += 1

        # Apply negative keyword penalties
        for keyword in keyword_set.negative_keywords:
            if self._find_keyword(keyword, normalized_text):
                score -= 2.0
                weights["negative"] += 1

        # Ensure score doesn't go below 0
        score = max(0.0, score)

        return score, matched_keywords, weights

    def _find_keyword(self, keyword: str, text: str) -> bool:
        """
        Check if keyword exists in text with proper boundaries.

        Uses word boundary matching to avoid partial matches.

        Args:
            keyword: Keyword to search for
            text: Text to search in (should be normalized)

        Returns:
            True if keyword found with word boundaries
        """
        # Escape special regex characters
        escaped = re.escape(keyword)
        # Match with word boundaries
        pattern = rf"\b{escaped}\b"
        return bool(re.search(pattern, text))


class HybridClassifier:
    """
    Hybrid classifier combining keyword and ML approaches.

    Uses keyword classifier as primary method, with optional ML fallback
    for borderline cases (confidence between threshold_low and threshold_high).
    """

    def __init__(
        self,
        keyword_classifier: KeywordClassifier | None = None,
        ml_classifier: ClassifierStrategy | None = None,
        confidence_threshold_low: float = 0.4,
        confidence_threshold_high: float = 0.8,
    ):
        """
        Initialize hybrid classifier.

        Args:
            keyword_classifier: Keyword classifier instance (creates default if None)
            ml_classifier: Optional ML classifier for fallback
            confidence_threshold_low: Below this, use ML fallback
            confidence_threshold_high: Above this, accept keyword result
        """
        self.keyword_classifier = keyword_classifier or KeywordClassifier()
        self.ml_classifier = ml_classifier
        self.threshold_low = confidence_threshold_low
        self.threshold_high = confidence_threshold_high

    def classify(
        self, ocr_lines: list[str], header_text: str | None = None
    ) -> ClassificationResult:
        """
        Classify using hybrid approach.

        Algorithm:
        1. Use keyword classifier
        2. If confidence > threshold_high: return result
        3. If confidence < threshold_low and ML available: use ML fallback
        4. Else: adjust confidence based on certainty

        Args:
            ocr_lines: OCR extracted lines
            header_text: Optional header text

        Returns:
            ClassificationResult from keyword or ML classifier
        """
        # Primary: keyword-based classification
        keyword_result = self.keyword_classifier.classify(
            ocr_lines=ocr_lines, header_text=header_text
        )

        # If high confidence, accept it
        if keyword_result.confidence_score >= self.threshold_high:
            keyword_result.evidence["method"] = "keyword_high_confidence"
            return keyword_result

        # If low confidence and ML available, try ML classifier
        if (
            keyword_result.confidence_score < self.threshold_low
            and self.ml_classifier is not None
        ):
            ml_result = self.ml_classifier.classify(
                ocr_lines=ocr_lines, header_text=header_text
            )
            ml_result.evidence["keyword_backup_score"] = keyword_result.confidence_score
            return ml_result

        # Medium confidence from keyword classifier
        keyword_result.evidence["method"] = "keyword_medium_confidence"
        return keyword_result


class DummyMLClassifier:
    """
    Minimal ML classifier for demonstration.

    In production, replace with actual ML model (scikit-learn, transformers, etc.)
    This serves as a template for integration.
    """

    def __init__(self, model_weights: dict[str, dict[str, float]] | None = None):
        """
        Initialize ML classifier with optional pre-trained weights.

        Args:
            model_weights: Pre-trained model weights dict
        """
        self.model_weights = model_weights or {}

    def classify(
        self, ocr_lines: list[str], header_text: str | None = None, **kwargs
    ) -> ClassificationResult:
        """
        Dummy ML classification (returns result based on simple heuristics).

        In production, this would:
        - Vectorize input text (TF-IDF, word2vec, transformers)
        - Run through trained model
        - Return predictions with confidence

        Args:
            ocr_lines: OCR lines
            header_text: Optional header
            **kwargs: Additional arguments

        Returns:
            ClassificationResult from dummy model
        """
        # Combine text
        all_text = " ".join(ocr_lines)
        if header_text:
            all_text = f"{header_text} {all_text}"

        # Dummy logic: use text length and specific keywords
        text_length = len(all_text)
        keyword_count = sum(1 for word in all_text.lower().split() if len(word) > 3)

        # Return based on simple heuristics
        scores = {
            "invoice": 0.5,
            "receipt": 0.5,
            "purchase_order": 0.4,
            "tax_invoice": 0.45,
        }

        # Boost scores based on text characteristics
        if text_length > 1000:
            scores["invoice"] += 0.1
            scores["tax_invoice"] += 0.15
        if keyword_count > 100:
            scores["receipt"] += 0.1

        best_type = max(scores, key=scores.get)
        best_score = min(1.0, scores[best_type])

        return ClassificationResult(
            document_type=DocumentType(best_type),
            confidence_score=best_score,
            matched_keywords={},
            evidence={"method": "dummy_ml", "text_length": text_length},
            raw_scores=scores,
        )


# Factory function for easy classifier creation
def create_classifier(
    classifier_type: str = "hybrid",
    keyword_sets: dict[str, KeywordSet] | None = None,
    use_ml: bool = False,
) -> KeywordClassifier | HybridClassifier:
    """
    Factory function to create document classifiers.

    Args:
        classifier_type: "keyword", "hybrid", or "ml"
        keyword_sets: Custom keyword sets (uses defaults if None)
        use_ml: Whether to include ML classifier in hybrid mode

    Returns:
        Configured classifier instance

    Examples:
        # Keyword-only classifier
        classifier = create_classifier("keyword")

        # Hybrid with ML fallback
        classifier = create_classifier("hybrid", use_ml=True)

        # Hybrid with custom keywords
        custom_keywords = {
            "invoice": KeywordSet.for_invoice(),
            "custom_type": KeywordSet(
                name="custom_type",
                primary_keywords=["custom", "keyword"]
            )
        }
        classifier = create_classifier("hybrid", keyword_sets=custom_keywords)
    """
    keyword_classifier = KeywordClassifier(keyword_sets=keyword_sets)

    if classifier_type == "keyword":
        return keyword_classifier

    if classifier_type == "hybrid":
        ml_classifier = DummyMLClassifier() if use_ml else None
        return HybridClassifier(
            keyword_classifier=keyword_classifier, ml_classifier=ml_classifier
        )

    raise ValueError(f"Unknown classifier type: {classifier_type}")
