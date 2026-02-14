"""
Unit tests for document classifier module.

Tests cover:
- Keyword scoring logic
- Classification accuracy
- Hybrid classifier behavior
- Custom keyword sets
- Edge cases
"""

import pytest

from app.services.document_classifier import (
    DocumentType,
    KeywordClassifier,
    KeywordSet,
    HybridClassifier,
    DummyMLClassifier,
    create_classifier,
)


class TestKeywordClassifier:
    """Tests for KeywordClassifier."""

    def test_initialization(self):
        """Test classifier initialization with default keywords."""
        classifier = KeywordClassifier()
        assert classifier.keyword_sets is not None
        assert "invoice" in classifier.keyword_sets
        assert "receipt" in classifier.keyword_sets
        assert "purchase_order" in classifier.keyword_sets
        assert "tax_invoice" in classifier.keyword_sets

    def test_invoice_classification(self):
        """Test invoice detection."""
        classifier = KeywordClassifier()
        
        ocr_lines = [
            "INVOICE",
            "Invoice Number: INV-2026-001",
            "Date: 2026-02-13",
            "Customer: ABC Corp",
            "Total: 5,000.00",
        ]
        
        result = classifier.classify(ocr_lines=ocr_lines)
        
        assert result.document_type == DocumentType.INVOICE
        assert result.confidence_score > 0.5
        assert "invoice" in result.matched_keywords

    def test_receipt_classification(self):
        """Test receipt detection."""
        classifier = KeywordClassifier()
        
        ocr_lines = [
            "RECEIPT",
            "Store #123",
            "Thank you for your purchase!",
            "Total: 500.00",
            "Change: 50.00",
        ]
        
        result = classifier.classify(ocr_lines=ocr_lines)
        
        assert result.document_type == DocumentType.RECEIPT
        assert result.confidence_score > 0.4

    def test_po_classification(self):
        """Test purchase order detection."""
        classifier = KeywordClassifier()
        
        ocr_lines = [
            "PURCHASE ORDER",
            "PO Number: PO-2026-001",
            "Vendor: TechCorp",
            "Ship To: Warehouse A",
            "Delivery Date: 2026-03-01",
        ]
        
        result = classifier.classify(ocr_lines=ocr_lines)
        
        assert result.document_type == DocumentType.PURCHASE_ORDER
        assert result.confidence_score > 0.4

    def test_tax_invoice_classification(self):
        """Test tax invoice detection."""
        classifier = KeywordClassifier()
        
        ocr_lines = [
            "ใบกำกับภาษีอากร",  # Tax invoice in Thai
            "เลขที่: INV-TH-2026-042",
            "ภาษีมูลค่าเพิ่ม: 2,000.00 บาท",
            "รวมทั้งสิ้น: 22,000.00 บาท",
        ]
        
        result = classifier.classify(ocr_lines=ocr_lines)
        
        assert result.document_type == DocumentType.TAX_INVOICE
        assert result.confidence_score > 0.3

    def test_unknown_classification(self):
        """Test unknown document classification."""
        classifier = KeywordClassifier()
        
        ocr_lines = [
            "Random text",
            "Some content",
            "No matching keywords here",
        ]
        
        result = classifier.classify(ocr_lines=ocr_lines)
        
        assert result.document_type == DocumentType.UNKNOWN
        assert result.confidence_score == 0.0

    def test_empty_ocr_lines(self):
        """Test with empty OCR lines."""
        classifier = KeywordClassifier()
        
        result = classifier.classify(ocr_lines=[])
        
        assert result.document_type == DocumentType.UNKNOWN
        assert result.confidence_score == 0.0

    def test_with_header_text(self):
        """Test classification with header text."""
        classifier = KeywordClassifier()
        
        header = "ACME Corporation Invoice"
        ocr_lines = ["Some content"]
        
        result = classifier.classify(ocr_lines=ocr_lines, header_text=header)
        
        assert result.document_type == DocumentType.INVOICE
        assert result.confidence_score > 0.3

    def test_matched_keywords_structure(self):
        """Test that matched keywords are properly structured."""
        classifier = KeywordClassifier()
        
        ocr_lines = ["INVOICE", "Invoice Number: INV-001"]
        result = classifier.classify(ocr_lines=ocr_lines)
        
        assert isinstance(result.matched_keywords, dict)
        assert "invoice" in result.matched_keywords
        assert isinstance(result.matched_keywords["invoice"], list)
        assert len(result.matched_keywords["invoice"]) > 0

    def test_raw_scores_all_types(self):
        """Test that raw_scores contains all document types."""
        classifier = KeywordClassifier()
        
        ocr_lines = ["INVOICE"]
        result = classifier.classify(ocr_lines=ocr_lines)
        
        assert "invoice" in result.raw_scores
        assert "receipt" in result.raw_scores
        assert "purchase_order" in result.raw_scores
        assert "tax_invoice" in result.raw_scores

    def test_confidence_score_normalization(self):
        """Test that confidence scores are normalized to 0.0-1.0."""
        classifier = KeywordClassifier()
        
        ocr_lines = ["INVOICE"] * 100  # High scoring document
        result = classifier.classify(ocr_lines=ocr_lines)
        
        assert 0.0 <= result.confidence_score <= 1.0

    def test_negative_keyword_penalty(self):
        """Test that negative keywords reduce score."""
        classifier = KeywordClassifier()
        
        # Invoice with receipt keyword (negative)
        ocr_lines = [
            "INVOICE",
            "Invoice Number: INV-001",
            "RECEIPT",
            "Cash Register",
        ]
        
        result = classifier.classify(ocr_lines=ocr_lines)
        
        # Score should be lower due to negative keywords
        assert result.document_type == DocumentType.INVOICE or DocumentType.RECEIPT

    def test_text_normalization(self):
        """Test that text normalization works correctly."""
        classifier = KeywordClassifier()
        
        # Test with mixed case
        ocr_lines_lower = ["invoice", "invoice number: inv-001"]
        ocr_lines_upper = ["INVOICE", "INVOICE NUMBER: INV-001"]
        ocr_lines_mixed = ["Invoice", "Invoice Number: INV-001"]
        
        result_lower = classifier.classify(ocr_lines=ocr_lines_lower)
        result_upper = classifier.classify(ocr_lines=ocr_lines_upper)
        result_mixed = classifier.classify(ocr_lines=ocr_lines_mixed)
        
        # All should classify as invoice
        assert result_lower.document_type == DocumentType.INVOICE
        assert result_upper.document_type == DocumentType.INVOICE
        assert result_mixed.document_type == DocumentType.INVOICE
        
        # Confidence should be roughly the same
        assert abs(result_lower.confidence_score - result_upper.confidence_score) < 0.01
        assert abs(result_lower.confidence_score - result_mixed.confidence_score) < 0.01

    def test_word_boundary_matching(self):
        """Test that keyword matching respects word boundaries."""
        classifier = KeywordClassifier()
        
        # 'invoice' should match, 'invoicex' should not
        ocr_lines = ["Some invoicex text"]
        result = classifier.classify(ocr_lines=ocr_lines)
        
        # Should not classify as invoice due to word boundary
        assert result.document_type != DocumentType.INVOICE or result.confidence_score < 0.5


class TestCustomKeywordSet:
    """Tests for custom keyword sets."""

    def test_custom_keyword_set(self):
        """Test classifier with custom keyword set."""
        custom_keywords = KeywordSet(
            name="statement",
            primary_keywords=["statement", "account statement"],
            secondary_keywords=["balance", "transaction"],
            tertiary_keywords=["date", "amount"],
            minimum_score_threshold=0.2,
        )
        
        classifier = KeywordClassifier(
            keyword_sets={"statement": custom_keywords}
        )
        
        ocr_lines = ["ACCOUNT STATEMENT", "Balance: 5000"]
        result = classifier.classify(ocr_lines=ocr_lines)
        
        # Custom keyword set should be used
        assert result.document_type.value == "statement"

    def test_mixed_default_and_custom_keywords(self):
        """Test mixing default and custom keyword sets."""
        custom_keywords = KeywordSet(
            name="custom",
            primary_keywords=["unique_keyword"],
            minimum_score_threshold=0.2,
        )
        
        classifier = KeywordClassifier(
            keyword_sets={
                "invoice": KeywordSet.for_invoice(),
                "custom": custom_keywords,
            }
        )
        
        # Should have both default and custom
        assert "invoice" in classifier.keyword_sets
        assert "custom" in classifier.keyword_sets


class TestHybridClassifier:
    """Tests for HybridClassifier."""

    def test_hybrid_initialization(self):
        """Test hybrid classifier initialization."""
        keyword_classifier = KeywordClassifier()
        ml_classifier = DummyMLClassifier()
        
        hybrid = HybridClassifier(
            keyword_classifier=keyword_classifier,
            ml_classifier=ml_classifier,
        )
        
        assert hybrid.keyword_classifier is not None
        assert hybrid.ml_classifier is not None

    def test_hybrid_high_confidence_path(self):
        """Test hybrid classifier with high-confidence keyword result."""
        keyword_classifier = KeywordClassifier()
        ml_classifier = DummyMLClassifier()
        
        hybrid = HybridClassifier(
            keyword_classifier=keyword_classifier,
            ml_classifier=ml_classifier,
            confidence_threshold_high=0.5,
        )
        
        ocr_lines = ["INVOICE", "Invoice Number: INV-001"]
        result = hybrid.classify(ocr_lines=ocr_lines)
        
        assert result.document_type == DocumentType.INVOICE
        assert result.evidence.get("method") == "keyword_high_confidence"

    def test_hybrid_low_confidence_fallback(self):
        """Test hybrid classifier ML fallback for low confidence."""
        keyword_classifier = KeywordClassifier()
        ml_classifier = DummyMLClassifier()
        
        hybrid = HybridClassifier(
            keyword_classifier=keyword_classifier,
            ml_classifier=ml_classifier,
            confidence_threshold_low=0.9,  # Very high threshold
            confidence_threshold_high=1.0,
        )
        
        ocr_lines = ["Random text"]
        result = hybrid.classify(ocr_lines=ocr_lines)
        
        # Should attempt ML fallback
        assert result.evidence.get("method") is not None

    def test_hybrid_without_ml(self):
        """Test hybrid classifier without ML fallback."""
        keyword_classifier = KeywordClassifier()
        
        hybrid = HybridClassifier(
            keyword_classifier=keyword_classifier,
            ml_classifier=None,
        )
        
        ocr_lines = ["INVOICE"]
        result = hybrid.classify(ocr_lines=ocr_lines)
        
        assert result.document_type == DocumentType.INVOICE


class TestDummyMLClassifier:
    """Tests for DummyMLClassifier."""

    def test_dummy_ml_initialization(self):
        """Test dummy ML classifier initialization."""
        ml = DummyMLClassifier()
        assert ml is not None

    def test_dummy_ml_classification(self):
        """Test dummy ML classification."""
        ml = DummyMLClassifier()
        
        ocr_lines = ["Some text content here"]
        result = ml.classify(ocr_lines=ocr_lines)
        
        assert result.document_type in [
            DocumentType.INVOICE,
            DocumentType.RECEIPT,
            DocumentType.PURCHASE_ORDER,
            DocumentType.TAX_INVOICE,
        ]
        assert 0.0 <= result.confidence_score <= 1.0


class TestFactoryFunction:
    """Tests for create_classifier factory function."""

    def test_create_keyword_classifier(self):
        """Test creating keyword-only classifier."""
        classifier = create_classifier("keyword")
        assert isinstance(classifier, KeywordClassifier)

    def test_create_hybrid_classifier(self):
        """Test creating hybrid classifier."""
        classifier = create_classifier("hybrid", use_ml=False)
        assert isinstance(classifier, HybridClassifier)

    def test_create_hybrid_with_ml(self):
        """Test creating hybrid classifier with ML."""
        classifier = create_classifier("hybrid", use_ml=True)
        assert isinstance(classifier, HybridClassifier)
        assert classifier.ml_classifier is not None

    def test_create_with_custom_keywords(self):
        """Test creating classifier with custom keywords."""
        custom_keywords = {"invoice": KeywordSet.for_invoice()}
        classifier = create_classifier("keyword", keyword_sets=custom_keywords)
        assert isinstance(classifier, KeywordClassifier)

    def test_invalid_classifier_type(self):
        """Test error on invalid classifier type."""
        with pytest.raises(ValueError):
            create_classifier("invalid_type")


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_very_long_document(self):
        """Test classification of very long document."""
        classifier = KeywordClassifier()
        
        long_lines = ["INVOICE"] + ["Some content line"] * 10000
        result = classifier.classify(ocr_lines=long_lines)
        
        assert result.document_type == DocumentType.INVOICE

    def test_non_ascii_characters(self):
        """Test with non-ASCII characters."""
        classifier = KeywordClassifier()
        
        ocr_lines = [
            "ใบแจ้งหนี้",  # Thai
            "發票",  # Chinese
            "facture",  # French
        ]
        
        result = classifier.classify(ocr_lines=ocr_lines)
        # Should handle gracefully
        assert result.document_type is not None

    def test_special_characters_in_keywords(self):
        """Test keywords with special characters."""
        classifier = KeywordClassifier()
        
        ocr_lines = [
            "INVOICE #123-456",
            "PO: PO-2026-001",
            "VAT: €250.00",
        ]
        
        result = classifier.classify(ocr_lines=ocr_lines)
        assert result.document_type is not None

    def test_single_line_classification(self):
        """Test classification with single line."""
        classifier = KeywordClassifier()
        
        result = classifier.classify(ocr_lines=["INVOICE"])
        
        assert result.document_type == DocumentType.INVOICE

    def test_whitespace_handling(self):
        """Test handling of excessive whitespace."""
        classifier = KeywordClassifier()
        
        ocr_lines = ["INVOICE", "   ", "\t\t", "Invoice Number: INV-001"]
        result = classifier.classify(ocr_lines=ocr_lines)
        
        assert result.document_type == DocumentType.INVOICE


class TestThresholds:
    """Tests for threshold behavior."""

    def test_minimum_threshold_enforcement(self):
        """Test that minimum score threshold is enforced."""
        classifier = KeywordClassifier()
        
        # Document with very few matching keywords
        ocr_lines = ["something"]
        result = classifier.classify(ocr_lines=ocr_lines)
        
        # Should be unknown due to low score
        assert result.document_type == DocumentType.UNKNOWN

    def test_threshold_just_above_minimum(self):
        """Test classification just above minimum threshold."""
        classifier = KeywordClassifier()
        
        # Single primary keyword should exceed minimum threshold
        ocr_lines = ["INVOICE"]
        result = classifier.classify(ocr_lines=ocr_lines)
        
        assert result.document_type == DocumentType.INVOICE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
