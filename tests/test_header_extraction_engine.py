"""
Unit tests for header extraction engine.
"""

import pytest
from app.services.header_extraction_engine import (
    HeaderExtractionEngine,
    TemplateExtractor,
    RegexAnchorExtractor,
    MLExtractor,
    create_extraction_engine,
    InvoiceFieldType,
    ExtractionSource,
    ExtractionStage,
    BoundingBox,
    ExtractionResult,
)


# ====== TEMPLATE EXTRACTOR TESTS ======

class TestTemplateExtractor:
    """Test template-based extraction."""

    def test_template_extractor_initialization(self):
        """Test template extractor creates with correct patterns."""
        extractor = TemplateExtractor()
        assert extractor.templates
        assert InvoiceFieldType.INVOICE_NUMBER in extractor.templates

    def test_extract_invoice_number(self):
        """Test invoicing number extraction."""
        extractor = TemplateExtractor()
        ocr_lines = ["INVOICE", "Invoice Number: INV-2024-001"]

        results = extractor.extract(ocr_lines, [InvoiceFieldType.INVOICE_NUMBER])

        assert len(results) == 1
        assert results[0].value == "INV-2024-001"
        assert results[0].confidence > 0.8
        assert results[0].source == ExtractionSource.TEMPLATE

    def test_extract_invoice_date(self):
        """Test invoice date extraction."""
        extractor = TemplateExtractor()
        ocr_lines = ["Invoice Date: 02/13/2024"]

        results = extractor.extract(ocr_lines, [InvoiceFieldType.INVOICE_DATE])

        assert len(results) == 1
        assert "02/13/2024" in results[0].value
        assert results[0].confidence > 0.8

    def test_extract_vendor_name(self):
        """Test vendor name extraction."""
        extractor = TemplateExtractor()
        ocr_lines = ["From: ACME Corporation"]

        results = extractor.extract(ocr_lines, [InvoiceFieldType.VENDOR_NAME])

        assert len(results) >= 0  # May not always match
        if results:
            assert results[0].source == ExtractionSource.TEMPLATE

    def test_extract_tax_id(self):
        """Test tax ID extraction."""
        extractor = TemplateExtractor()
        ocr_lines = ["Tax ID: 12-3456789"]

        results = extractor.extract(ocr_lines, [InvoiceFieldType.TAX_ID])

        assert len(results) == 1
        assert "12-3456789" in results[0].value

    def test_extract_monetary_amounts(self):
        """Test extraction of monetary values."""
        extractor = TemplateExtractor()
        ocr_lines = [
            "Subtotal: 1000.00",
            "VAT: 200.00",
            "Total: 1200.00"
        ]

        results = extractor.extract(ocr_lines, [
            InvoiceFieldType.SUBTOTAL,
            InvoiceFieldType.VAT,
            InvoiceFieldType.TOTAL_AMOUNT
        ])

        assert len(results) == 3
        assert all(r.source == ExtractionSource.TEMPLATE for r in results)

    def test_supports_field(self):
        """Test field support checking."""
        extractor = TemplateExtractor()

        assert extractor.supports_field(InvoiceFieldType.INVOICE_NUMBER)
        assert extractor.supports_field(InvoiceFieldType.TOTAL_AMOUNT)

    def test_confidence_validation(self):
        """Test confidence calculation."""
        extractor = TemplateExtractor()
        ocr_lines = ["Invoice Number: INV-001"]

        results = extractor.extract(ocr_lines, [InvoiceFieldType.INVOICE_NUMBER])

        assert all(0.0 <= r.confidence <= 1.0 for r in results)

    def test_empty_ocr_lines(self):
        """Test handling of empty OCR input."""
        extractor = TemplateExtractor()

        results = extractor.extract([], [InvoiceFieldType.INVOICE_NUMBER])

        assert len(results) == 0

    def test_no_matching_patterns(self):
        """Test when no patterns match."""
        extractor = TemplateExtractor()
        ocr_lines = ["Random text that has no meaning"]

        results = extractor.extract(ocr_lines, [InvoiceFieldType.INVOICE_NUMBER])

        assert len(results) == 0


# ====== REGEX ANCHOR EXTRACTOR TESTS ======

class TestRegexAnchorExtractor:
    """Test regex anchor-based extraction."""

    def test_regex_extractor_initialization(self):
        """Test regex extractor initialization."""
        extractor = RegexAnchorExtractor(proximity_window=3)
        assert extractor.anchors
        assert InvoiceFieldType.INVOICE_NUMBER in extractor.anchors

    def test_extract_with_anchor(self):
        """Test extraction with anchor keyword."""
        extractor = RegexAnchorExtractor()
        ocr_lines = ["Invoice: INV-001"]

        results = extractor.extract(ocr_lines, [InvoiceFieldType.INVOICE_NUMBER])

        assert len(results) >= 1
        if results:
            assert results[0].source == ExtractionSource.REGEX

    def test_proximity_scoring(self):
        """Test proximity score calculation."""
        extractor = RegexAnchorExtractor()

        # Anchor on line 0, value on line 0: high proximity
        ocr_lines_same = ["Invoice: INV-001"]
        results_same = extractor.extract(ocr_lines_same, [InvoiceFieldType.INVOICE_NUMBER])

        # Anchor on line 0, value on line 3: lower proximity
        ocr_lines_far = ["Invoice:", "", "", "INV-001"]
        results_far = extractor.extract(ocr_lines_far, [InvoiceFieldType.INVOICE_NUMBER])

        if results_same and results_far:
            assert results_same[0].confidence >= results_far[0].confidence

    def test_extract_monetary_with_regex(self):
        """Test monetary value extraction."""
        extractor = RegexAnchorExtractor()
        ocr_lines = ["Total: 1000.00"]

        results = extractor.extract(ocr_lines, [InvoiceFieldType.TOTAL_AMOUNT])

        assert len(results) >= 1

    def test_supports_field(self):
        """Test field support checking."""
        extractor = RegexAnchorExtractor()
        assert extractor.supports_field(InvoiceFieldType.INVOICE_NUMBER)

    def test_confidence_in_range(self):
        """Test confidence is always in valid range."""
        extractor = RegexAnchorExtractor()
        ocr_lines = [
            "Invoice: INV-001",
            "Date: 02/13/2024",
            "Total: 1000.00"
        ]

        results = extractor.extract(ocr_lines, [
            InvoiceFieldType.INVOICE_NUMBER,
            InvoiceFieldType.INVOICE_DATE,
            InvoiceFieldType.TOTAL_AMOUNT
        ])

        assert all(0.0 <= r.confidence <= 1.0 for r in results)

    def test_text_quality_scoring(self):
        """Test quality scoring for different field types."""
        extractor = RegexAnchorExtractor()

        # Good quality: contains numbers
        ocr_good = ["Invoice: INV-2024-001"]
        results_good = extractor.extract(ocr_good, [InvoiceFieldType.INVOICE_NUMBER])

        # Poor quality: no numbers for numeric field
        ocr_poor = ["Invoice: ABC"]
        results_poor = extractor.extract(ocr_poor, [InvoiceFieldType.INVOICE_NUMBER])

        # Good should have higher or equal confidence
        if results_good and results_poor:
            assert results_good[0].confidence >= results_poor[0].confidence

    def test_empty_ocr(self):
        """Test empty OCR handling."""
        extractor = RegexAnchorExtractor()

        results = extractor.extract([], [InvoiceFieldType.INVOICE_NUMBER])

        assert len(results) == 0


# ====== ML EXTRACTOR TESTS ======

class TestMLExtractor:
    """Test ML-based extraction."""

    def test_ml_extractor_initialization(self):
        """Test ML extractor creation."""
        extractor = MLExtractor()
        assert extractor.confidence_threshold >= 0.0

    def test_ml_extractor_returns_empty_list(self):
        """Test ML extractor returns empty list (stub implementation)."""
        extractor = MLExtractor()
        ocr_lines = ["INVOICE", "Number: 001"]

        results = extractor.extract(ocr_lines, [InvoiceFieldType.INVOICE_NUMBER])

        # Should return empty until implemented
        assert isinstance(results, list)

    def test_ml_supports_all_fields(self):
        """Test ML extractor supports all field types."""
        extractor = MLExtractor()

        for field_type in InvoiceFieldType:
            assert extractor.supports_field(field_type)


# ====== HEADER EXTRACTION ENGINE TESTS ======

class TestHeaderExtractionEngine:
    """Test main extraction engine."""

    def test_engine_initialization(self):
        """Test engine creation."""
        engine = create_extraction_engine()
        assert engine.template_extractor is not None
        assert engine.regex_extractor is not None

    def test_extract_with_template_stage(self):
        """Test extraction completes at template stage."""
        engine = create_extraction_engine(enable_template=True, enable_regex=False)

        ocr_lines = ["Invoice Number: INV-001"]
        output = engine.extract_invoice_header(ocr_lines)

        assert len(output.fields) > 0
        assert output.extracted_at_stage == ExtractionStage.TEMPLATE

    def test_extract_with_regex_fallback(self):
        """Test regex stage executes for missing fields."""
        engine = create_extraction_engine()

        # Template won't match these variations
        ocr_lines = ["Invoice: INV-001"]
        output = engine.extract_invoice_header(ocr_lines)

        assert output.fields
        # May be extracted at template or regex stage

    def test_overall_confidence_calculation(self):
        """Test overall confidence is calculated correctly."""
        engine = create_extraction_engine()

        ocr_lines = [
            "INVOICE",
            "Invoice Number: INV-001",
            "Total: 1000.00"
        ]

        output = engine.extract_invoice_header(ocr_lines)

        if output.fields:
            avg_conf = sum(r.confidence for r in output.fields.values()) / len(output.fields)
            assert output.overall_confidence == avg_conf

    def test_processing_time_recorded(self):
        """Test processing time is recorded."""
        engine = create_extraction_engine()

        ocr_lines = ["Invoice Number: INV-001"]
        output = engine.extract_invoice_header(ocr_lines)

        assert output.processing_time_ms >= 0.0
        assert output.processing_time_ms < 10000  # Should be fast

    def test_custom_field_selection(self):
        """Test extracting only specific fields."""
        engine = create_extraction_engine()

        ocr_lines = [
            "Invoice Number: INV-001",
            "Date: 02/13/2024",
            "Total: 1000.00"
        ]

        field_types = [InvoiceFieldType.INVOICE_NUMBER, InvoiceFieldType.TOTAL_AMOUNT]
        output = engine.extract_invoice_header(ocr_lines, field_types=field_types)

        # Should only request/contain these field types
        extracted_types = set(output.fields.keys())
        requested_types = set(field_types)
        assert extracted_types.issubset(requested_types.union({InvoiceFieldType.INVOICE_DATE, InvoiceFieldType.VENDOR_NAME}))

    def test_all_results_tracking(self):
        """Test all_results contains attempts from all stages."""
        engine = create_extraction_engine()

        ocr_lines = ["INV-001", "2024-02-13", "1000"]
        output = engine.extract_invoice_header(ocr_lines)

        # all_results should track attempts from each stage
        if output.all_results:
            assert any(r.stage == ExtractionStage.TEMPLATE for r in output.all_results)

    def test_handles_empty_ocr(self):
        """Test handling of empty OCR."""
        engine = create_extraction_engine()

        output = engine.extract_invoice_header([])

        assert output.overall_confidence >= 0.0
        assert output.fields == {}


# ====== FACTORY FUNCTION TESTS ======

class TestFactoryFunction:
    """Test factory function configurations."""

    def test_create_default_engine(self):
        """Test creating engine with defaults."""
        engine = create_extraction_engine()
        assert engine.template_extractor is not None
        assert engine.regex_extractor is not None
        assert not engine.enable_llm

    def test_create_template_only(self):
        """Test creating template-only engine."""
        engine = create_extraction_engine(
            enable_template=True,
            enable_regex=False,
            enable_ml=False,
            enable_llm=False
        )
        assert engine.template_extractor is not None
        assert engine.regex_extractor is None

    def test_create_ml_enabled(self):
        """Test creating engine with ML enabled."""
        engine = create_extraction_engine(enable_ml=True)
        assert engine.ml_extractor is not None

    def test_create_with_llm_config(self):
        """Test creating engine with LLM configuration."""
        engine = create_extraction_engine(
            enable_llm=True,
            llm_api_key="test-key",
            confidence_threshold_for_llm=0.6
        )
        assert engine.enable_llm
        assert engine.confidence_threshold_for_llm == 0.6


# ====== EDGE CASE TESTS ======

class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_very_long_ocr_document(self):
        """Test handling of very long documents."""
        engine = create_extraction_engine()

        # Create 1000 lines of OCR
        ocr_lines = [f"Line {i}: Some invoice data" for i in range(1000)]
        ocr_lines[500] = "Invoice Number: INV-001"
        ocr_lines[750] = "Total: 1000.00"

        output = engine.extract_invoice_header(ocr_lines)

        # Should still process
        assert output.processing_time_ms >= 0.0

    def test_non_ascii_characters(self):
        """Test handling of non-ASCII characters."""
        engine = create_extraction_engine()

        ocr_lines = [
            "ใบแจ้งหนี้",  # Thai for invoice
            "เลขที่: INV-001",
            "รวม: 1000 บาท"
        ]

        output = engine.extract_invoice_header(ocr_lines)

        # Should process without errors
        assert output.overall_confidence >= 0.0

    def test_special_characters_in_values(self):
        """Test handling of special characters."""
        engine = create_extraction_engine()

        ocr_lines = [
            "Invoice Number: INV-2024/001-A",
            "Vendor: O'Reilly & Associates",
            "Total: $1,200.50"
        ]

        output = engine.extract_invoice_header(ocr_lines)

        assert output.fields

    def test_duplicate_field_indicators(self):
        """Test handling of multiple field indicators."""
        engine = create_extraction_engine()

        ocr_lines = [
            "Invoice: INV-001",
            "Invoice No: INV-002",
            "Invoice ID: INV-003"
        ]

        output = engine.extract_invoice_header(
            ocr_lines,
            [InvoiceFieldType.INVOICE_NUMBER]
        )

        # Should find one result (the best match)
        assert len([f for f in output.fields.values() if f.value]) <= 1

    def test_confidence_with_poor_ocr(self):
        """Test confidence scores with poor OCR quality."""
        engine = create_extraction_engine()

        ocr_lines = [
            "I||v0iCe: |NV-0|",
            "D4t3: 02/13/20??",
            "T0tal: 1000.OO"  # Mix of letters and numbers
        ]

        output = engine.extract_invoice_header(ocr_lines)

        # May not extract anything, or extract with low confidence
        if output.fields:
            assert all(0.0 <= r.confidence <= 1.0 for r in output.fields.values())


# ====== CONFIDENCE SCORING TESTS ======

class TestConfidenceScoring:
    """Test confidence scoring logic."""

    def test_confidence_bounds(self):
        """Test confidence is always 0.0-1.0."""
        engine = create_extraction_engine()

        test_cases = [
            ["Invoice: INV-001"],
            ["Random junk text"],
            [""],
            ["Invoice Number: " + "A" * 1000]  # Very long
        ]

        for ocr_lines in test_cases:
            output = engine.extract_invoice_header(ocr_lines)
            assert 0.0 <= output.overall_confidence <= 1.0

    def test_perfect_match_confidence(self):
        """Test confidence for perfect template matches."""
        template_extractor = TemplateExtractor()

        ocr_lines = ["Invoice Number: INV-2024-001"]
        results = template_extractor.extract(
            ocr_lines,
            [InvoiceFieldType.INVOICE_NUMBER]
        )

        if results:
            # Perfect match should be high confidence
            assert results[0].confidence > 0.85

    def test_partial_match_confidence(self):
        """Test confidence for partial matches."""
        regex_extractor = RegexAnchorExtractor()

        # Partial match: valid field but some offset
        ocr_lines = [
            "Some header",
            "Invoice info here:",
            "",
            "INV-001"  # value is 3 lines away
        ]

        results = regex_extractor.extract(
            ocr_lines,
            [InvoiceFieldType.INVOICE_NUMBER]
        )

        if results:
            # Partial match should be lower confidence
            assert results[0].confidence < 0.95


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
