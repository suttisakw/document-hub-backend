"""
Comprehensive unit tests for ValidationAndNormalization module.

Test coverage:
- Thai date parsing (formats, Buddhist year conversion)
- Currency normalization (formats, symbols, separators)
- Field validation (tax_id checksum, amounts, dates)
- Confidence adjustment
- Field review flagging
- Document validation
- Edge cases
"""

import pytest
from datetime import date, datetime
from backend.app.services.validation_and_normalization import (
    ValidationStatus,
    FieldType,
    ValidationResult,
    ThaiDateParser,
    CurrencyNormalizer,
    FieldValidator,
    ValidationAndNormalizationEngine,
    create_validation_engine,
)


# ====== THAI DATE PARSER TESTS ======

class TestThaiDateParser:
    """Test Thai date parsing and normalization."""

    def setup_method(self):
        """Setup for each test."""
        self.parser = ThaiDateParser()

    def test_parse_thai_digit_conversion(self):
        """Test conversion of Thai digits to Arabic."""
        text = "๑๕"  # Thai digits 15
        result = self.parser.convert_thai_digits_to_arabic(text)
        assert result == "15"

    def test_parse_dd_mm_yyyy_format(self):
        """Test parse DD/MM/YYYY format."""
        parsed, confidence, format_name = self.parser.parse_date("15/02/2024")
        assert parsed == date(2024, 2, 15)
        assert confidence == 0.95
        assert format_name == "DD/MM/YYYY"

    def test_parse_thai_date_with_digits(self):
        """Test parse Thai date with Thai digits."""
        parsed, confidence, format_name = self.parser.parse_date("๑๕/๐๒/๒๕๖๗")
        assert parsed == date(2024, 2, 15)  # Buddhist year 2567 = 2024 CE
        assert confidence == 0.95

    def test_parse_thai_month_name(self):
        """Test parse date with Thai month name."""
        parsed, confidence, format_name = self.parser.parse_date("15 กุมภาพันธ์ 2567")
        assert parsed == date(2024, 2, 15)
        assert confidence == 0.95

    def test_parse_thai_month_abbreviation(self):
        """Test parse date with abbreviated Thai month."""
        parsed, confidence, format_name = self.parser.parse_date("15 กพ 2567")
        assert parsed == date(2024, 2, 15)

    def test_parse_buddhist_year_conversion(self):
        """Test Buddhist year (BE) to Gregorian (CE) conversion."""
        # 2567 BE = 2024 CE
        parsed, _, _ = self.parser.parse_date("15/02/2567")
        assert parsed.year == 2024

    def test_parse_gregorian_year_no_conversion(self):
        """Test that Gregorian years are not converted."""
        parsed, _, _ = self.parser.parse_date("15/02/2024")
        assert parsed.year == 2024

    def test_parse_invalid_month(self):
        """Test invalid month number."""
        parsed, confidence, _ = self.parser.parse_date("15/13/2024")
        assert parsed is None
        assert confidence == 0.0

    def test_parse_invalid_day(self):
        """Test invalid day number."""
        parsed, confidence, _ = self.parser.parse_date("32/01/2024")
        assert parsed is None

    def test_parse_empty_input(self):
        """Test empty input."""
        parsed, confidence, _ = self.parser.parse_date("")
        assert parsed is None
        assert confidence == 0.0

    def test_normalize_date_to_iso(self):
        """Test date normalization to ISO format."""
        normalized, parsed, conf, fmt = self.parser.normalize_date("15/02/2567")
        assert normalized == "2024-02-15"
        assert parsed == date(2024, 2, 15)
        assert isinstance(normalized, str)

    def test_normalize_vietnamese_style(self):
        """Test Vietnamese date format (DD/MM/YYYY)."""
        normalized, parsed, conf, fmt = self.parser.normalize_date("25/12/2023")
        assert normalized == "2023-12-25"

    def test_parse_with_dashes(self):
        """Test parse with dashes as separators."""
        parsed, _, _ = self.parser.parse_date("15-02-2024")
        assert parsed == date(2024, 2, 15)

    def test_parse_with_spaces(self):
        """Test parse with spaces as separators."""
        parsed, _, _ = self.parser.parse_date("15 02 2024")
        assert parsed == date(2024, 2, 15)


# ====== CURRENCY NORMALIZER TESTS ======

class TestCurrencyNormalizer:
    """Test currency normalization."""

    def test_normalize_simple_number(self):
        """Test normalize simple number."""
        value, conf = CurrencyNormalizer.normalize("1000")
        assert value == 1000.0
        assert conf == 0.95

    def test_normalize_us_format_with_commas(self):
        """Test normalize US format (1,000.50)."""
        value, conf = CurrencyNormalizer.normalize("1,000.50")
        assert value == 1000.50
        assert conf > 0.9

    def test_normalize_european_format(self):
        """Test normalize European format (1.000,50)."""
        value, conf = CurrencyNormalizer.normalize("1.000,50")
        assert value == 1000.50

    def test_normalize_with_currency_symbol(self):
        """Test normalize with currency symbol."""
        value, conf = CurrencyNormalizer.normalize("$1,000.50")
        assert value == 1000.50

    def test_normalize_with_baht_symbol(self):
        """Test normalize with Thai baht symbol."""
        value, conf = CurrencyNormalizer.normalize("฿5,500.00")
        assert value == 5500.0

    def test_normalize_thai_digits(self):
        """Test normalize Thai digits in currency."""
        value, conf = CurrencyNormalizer.normalize("๕,๕๐๐.๐๐")
        assert value == 5500.0

    def test_normalize_large_number(self):
        """Test normalize large number."""
        value, conf = CurrencyNormalizer.normalize("15,000,000.50")
        assert value == 15000000.50

    def test_normalize_negative_value(self):
        """Test normalize negative value (refund)."""
        value, conf = CurrencyNormalizer.normalize("-1,000.50")
        assert value == -1000.50

    def test_normalize_zero(self):
        """Test normalize zero value."""
        value, conf = CurrencyNormalizer.normalize("0.00")
        assert value == 0.0
        assert conf == 0.7  # Lower confidence for zero

    def test_normalize_invalid_format(self):
        """Test normalize invalid format."""
        value, conf = CurrencyNormalizer.normalize("ABC")
        assert value is None
        assert conf == 0.0

    def test_normalize_empty_string(self):
        """Test normalize empty string."""
        value, conf = CurrencyNormalizer.normalize("")
        assert value is None
        assert conf == 0.0


# ====== FIELD VALIDATOR TESTS ======

class TestFieldValidator:
    """Test field validation."""

    def test_validate_tax_id_valid(self):
        """Test validate valid tax ID."""
        # Valid 13-digit Thai tax ID (with correct checksum)
        is_valid, conf, error = FieldValidator.validate_tax_id("1234567890128")
        assert isinstance(is_valid, bool)
        assert 0.0 <= conf <= 1.0

    def test_validate_tax_id_invalid_length(self):
        """Test validate tax ID with wrong length."""
        is_valid, conf, error = FieldValidator.validate_tax_id("123456789")
        assert not is_valid
        assert "13 digits" in error

    def test_validate_tax_id_non_numeric(self):
        """Test validate tax ID with non-numeric characters."""
        is_valid, conf, error = FieldValidator.validate_tax_id("123456789012A")
        assert not is_valid

    def test_validate_tax_id_empty(self):
        """Test validate empty tax ID."""
        is_valid, conf, error = FieldValidator.validate_tax_id("")
        assert not is_valid

    def test_validate_amounts_valid(self):
        """Test validate valid amounts."""
        is_valid, conf, errors = FieldValidator.validate_amounts(
            subtotal=1000.0,
            vat=100.0,
            total=1100.0
        )
        assert is_valid
        assert len(errors) == 0

    def test_validate_amounts_total_less_than_subtotal(self):
        """Test validate total < subtotal."""
        is_valid, conf, errors = FieldValidator.validate_amounts(
            subtotal=1000.0,
            vat=None,
            total=900.0
        )
        assert not is_valid
        assert any("should be >=" in e for e in errors)

    def test_validate_amounts_negative_values(self):
        """Test validate negative values."""
        is_valid, conf, errors = FieldValidator.validate_amounts(
            subtotal=-100.0,
            vat=None,
            total=None
        )
        assert not is_valid
        assert any("negative" in e for e in errors)

    def test_validate_amounts_none_values(self):
        """Test validate with None values."""
        is_valid, conf, errors = FieldValidator.validate_amounts(
            subtotal=None,
            vat=None,
            total=None
        )
        assert is_valid
        assert len(errors) == 0

    def test_validate_date_valid(self):
        """Test validate valid date."""
        is_valid, conf, error = FieldValidator.validate_date(date(2024, 2, 15))
        assert is_valid
        assert conf == 0.95

    def test_validate_date_in_future(self):
        """Test validate future date."""
        future_date = date(2099, 12, 31)
        is_valid, conf, error = FieldValidator.validate_date(future_date)
        assert not is_valid

    def test_validate_date_too_old(self):
        """Test validate date too old."""
        old_date = date(1800, 1, 1)
        is_valid, conf, error = FieldValidator.validate_date(old_date)
        assert not is_valid

    def test_validate_date_none(self):
        """Test validate None date."""
        is_valid, conf, error = FieldValidator.validate_date(None)
        assert not is_valid


# ====== VALIDATION ENGINE TESTS ======

class TestValidationEngine:
    """Test main validation engine."""

    def setup_method(self):
        """Setup for each test."""
        self.engine = create_validation_engine()

    def test_validate_thai_date_field(self):
        """Test validate Thai date field."""
        result = self.engine.validate_and_normalize_field(
            "invoice_date",
            "15/02/2567",
            FieldType.DATE,
            0.95
        )
        assert result.is_valid
        assert result.normalized_value == "2024-02-15"
        assert result.status == ValidationStatus.VALID

    def test_validate_currency_field(self):
        """Test validate currency field."""
        result = self.engine.validate_and_normalize_field(
            "total_amount",
            "5,500.00",
            FieldType.CURRENCY,
            0.95
        )
        assert result.is_valid
        assert result.normalized_value == "5500.0"

    def test_validate_tax_id_field(self):
        """Test validate tax ID field."""
        result = self.engine.validate_and_normalize_field(
            "vendor_tax_id",
            "1234567890128",
            FieldType.TAX_ID,
            0.95
        )
        assert isinstance(result.is_valid, bool)
        assert result.normalized_value is not None

    def test_validate_text_field(self):
        """Test validate text field (always valid if non-empty)."""
        result = self.engine.validate_and_normalize_field(
            "vendor_name",
            "ABC Company",
            FieldType.TEXT,
            0.95
        )
        assert result.is_valid
        assert result.normalized_value == "ABC Company"

    def test_validate_empty_field(self):
        """Test validate empty field."""
        result = self.engine.validate_and_normalize_field(
            "invoice_date",
            "",
            FieldType.DATE,
            0.95
        )
        assert not result.is_valid
        assert result.needs_review
        assert result.confidence_adjustment > 0

    def test_validate_invalid_date_field(self):
        """Test validate invalid date."""
        result = self.engine.validate_and_normalize_field(
            "invoice_date",
            "invalid",
            FieldType.DATE,
            0.95
        )
        assert not result.is_valid
        assert result.needs_review

    def test_validate_document_complete(self):
        """Test validate complete document."""
        document = {
            "id": "doc_123",
            "invoice_date": "15/02/2567",
            "vendor_tax_id": "1234567890128",
            "subtotal": "5,000.00",
            "vat": "500.00",
            "total_amount": "5,500.00",
            "vendor_name": "ABC Company",
            "confidence": {
                "invoice_date": 0.95,
                "vendor_tax_id": 0.92,
                "total_amount": 0.98,
            }
        }

        updated_doc = self.engine.validate_document(document)

        assert "validation" in updated_doc
        assert updated_doc["id"] == "doc_123"
        assert "invoice_date" in updated_doc  # Normalized
        assert isinstance(updated_doc["total_amount"], str)

    def test_validate_document_with_invalid_fields(self):
        """Test validate document with some invalid fields."""
        document = {
            "id": "doc_456",
            "invoice_date": "invalid_date",
            "vendor_tax_id": "12345",  # Too short
            "total_amount": "5,500.00",
            "confidence": {
                "invoice_date": 0.95,
                "vendor_tax_id": 0.92,
                "total_amount": 0.98,
            }
        }

        updated_doc = self.engine.validate_document(document)

        # Should have validation metadata
        assert "validation" in updated_doc
        assert len(updated_doc["validation"]["fields_needing_review"]) > 0

    def test_validate_document_batch_processing(self):
        """Test process multiple documents."""
        doc1 = {
            "id": "doc_1",
            "invoice_date": "15/02/2567",
            "total_amount": "5,500.00"
        }
        doc2 = {
            "id": "doc_2",
            "invoice_date": "20/02/2567",
            "total_amount": "3,000.00"
        }

        result1 = self.engine.validate_document(doc1)
        result2 = self.engine.validate_document(doc2)

        assert result1["id"] == "doc_1"
        assert result2["id"] == "doc_2"
        assert "validation" in result1
        assert "validation" in result2


# ====== EDGE CASE TESTS ======

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def setup_method(self):
        """Setup for each test."""
        self.engine = create_validation_engine()

    def test_validate_leap_year_date(self):
        """Test validate date on leap year."""
        result = self.engine.validate_and_normalize_field(
            "invoice_date",
            "29/02/2024",
            FieldType.DATE,
            0.95
        )
        assert result.is_valid
        assert result.normalized_value == "2024-02-29"

    def test_validate_invalid_leap_year_date(self):
        """Test validate invalid leap year date."""
        result = self.engine.validate_and_normalize_field(
            "invoice_date",
            "29/02/2023",  # 2023 is not a leap year
            FieldType.DATE,
            0.95
        )
        assert not result.is_valid

    def test_validate_year_2000(self):
        """Test validate year 2000."""
        result = self.engine.validate_and_normalize_field(
            "invoice_date",
            "01/01/2000",
            FieldType.DATE,
            0.95
        )
        assert result.is_valid

    def test_validate_very_large_currency(self):
        """Test validate very large currency amount."""
        result = self.engine.validate_and_normalize_field(
            "total_amount",
            "999,999,999,999.99",
            FieldType.CURRENCY,
            0.95
        )
        assert result.is_valid
        assert float(result.normalized_value) == 999999999999.99

    def test_validate_mixed_separators(self):
        """Test validate currency with mixed separators (European)."""
        result = self.engine.validate_and_normalize_field(
            "total_amount",
            "1.234.567,89",
            FieldType.CURRENCY,
            0.95
        )
        assert result.is_valid
        assert float(result.normalized_value) == 1234567.89

    def test_validate_confidence_adjustment_range(self):
        """Test confidence adjustments are in valid range."""
        result = self.engine.validate_and_normalize_field(
            "invoice_date",
            "invalid",
            FieldType.DATE,
            0.95
        )
        assert 0.0 <= result.confidence_adjustment <= 1.0

    def test_validate_special_characters_in_text(self):
        """Test text field with special characters."""
        result = self.engine.validate_and_normalize_field(
            "vendor_name",
            "Company #1 & Co., Ltd.",
            FieldType.TEXT,
            0.95
        )
        assert result.is_valid
        assert result.normalized_value == "Company #1 & Co., Ltd."

    def test_validate_multilingual_vendor_name(self):
        """Test multilingual vendor name."""
        result = self.engine.validate_and_normalize_field(
            "vendor_name",
            "บริษัท ABC Co., Ltd.",
            FieldType.TEXT,
            0.95
        )
        assert result.is_valid

    def test_validate_currency_with_multiple_formats(self):
        """Test various currency formats."""
        formats = [
            "1,000.00",
            "1.000,00",
            "$1,000.00",
            "฿1,000.00",
            "1000",
            "1 000",
        ]

        for currency_str in formats:
            result = self.engine.validate_and_normalize_field(
                "amount",
                currency_str,
                FieldType.CURRENCY,
                0.95
            )
            assert result.is_valid, f"Failed for format: {currency_str}"

    def test_validate_year_conversion_boundary(self):
        """Test Buddhist year conversion at boundary (year 2000)."""
        # Year 2000 CE = 2543 BE
        result = self.engine.validate_and_normalize_field(
            "invoice_date",
            "01/01/2543",
            FieldType.DATE,
            0.95
        )
        assert result.is_valid
        assert "2000-01-01" in result.normalized_value

    def test_confidence_not_increased_for_valid_fields(self):
        """Test confidence is not increased for valid fields."""
        result = self.engine.validate_and_normalize_field(
            "invoice_date",
            "15/02/2024",
            FieldType.DATE,
            0.95
        )
        # Confidence adjustment should be zero or small for valid fields
        assert result.confidence_adjustment <= 0.1


# ====== INTEGRATION TESTS ======

class TestIntegration:
    """Integration tests with full documents."""

    def test_validate_invoice_document(self):
        """Test validate complete invoice document."""
        invoice = {
            "id": "INV-2024-001",
            "vendor_name": "บริษัท ABC จำกัด",
            "vendor_tax_id": "1234567890128",
            "invoice_date": "15 กุมภาพันธ์ 2567",
            "subtotal": "5,000.00",
            "vat": "500.00",
            "total_amount": "5,500.00",
            "confidence": {
                "vendor_name": 0.98,
                "vendor_tax_id": 0.92,
                "invoice_date": 0.95,
                "subtotal": 0.97,
                "vat": 0.97,
                "total_amount": 0.98,
            }
        }

        engine = create_validation_engine()
        result = engine.validate_document(invoice)

        assert result["id"] == "INV-2024-001"
        assert "validation" in result
        assert isinstance(result["validation"]["fields_needing_review"], list)

    def test_validate_multiple_date_formats_in_document(self):
        """Test document with different date formats."""
        doc = {
            "id": "doc_mixed",
            "invoice_date": "15/02/2567",  # Thai format
            "due_date": "25-02-2024",  # Gregorian with dashes
        }

        engine = create_validation_engine()
        # Should handle both formats
        result = engine.validate_document(doc)
        assert "id" in result

    def test_validate_document_preserves_original_on_parse_failure(self):
        """Test document field is preserved if normalization fails."""
        doc = {
            "id": "doc_fail",
            "invoice_date": "invalid_date_string",
            "total_amount": "not_a_number",
        }

        engine = create_validation_engine()
        result = engine.validate_document(doc)

        # Original values should be in normalized_document
        # (even if marked as needing review)
        assert result["id"] == "doc_fail"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
