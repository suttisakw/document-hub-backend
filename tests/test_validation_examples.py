"""
Working examples of ValidationAndNormalization module.

Demonstrates:
1. Thai date parsing and normalization
2. Currency normalization
3. Field validation
4. Document validation
5. Confidence adjustment
6. Field review flagging
7. Batch processing
"""

import json
from datetime import date
from backend.app.services.validation_and_normalization import (
    create_validation_engine,
    FieldType,
    ValidationAndNormalizationEngine,
)


def example_thai_date_parsing():
    """Example: Parse various Thai date formats."""
    print("=" * 70)
    print("EXAMPLE 1: Thai Date Parsing")
    print("=" * 70)

    engine = create_validation_engine()

    date_formats = [
        "15/02/2567",  # Thai year (BE) with slash
        "15 กุมภาพันธ์ 2567",  # Thai month name
        "15 กพ 2567",  # Abbreviated Thai month
        "๑๕/๐๒/๒๕๖๗",  # Thai digits
        "15-02-2024",  # Gregorian with dash
    ]

    for date_str in date_formats:
        result = engine.validate_and_normalize_field(
            "invoice_date",
            date_str,
            FieldType.DATE,
            0.95
        )

        print(f"\n  Input:      {date_str}")
        print(f"  Normalized: {result.normalized_value}")
        print(f"  Valid:      {result.is_valid}")
        print(f"  Status:     {result.status}")
        if result.evidence:
            print(f"  Format:     {result.evidence.get('format_detected', 'N/A')}")
            print(f"  Confidence: {result.evidence.get('parse_confidence', 0.0):.2f}")

    print()


def example_currency_normalization():
    """Example: Normalize various currency formats."""
    print("=" * 70)
    print("EXAMPLE 2: Currency Normalization")
    print("=" * 70)

    engine = create_validation_engine()

    currency_formats = [
        "5,500.00",  # US format
        "5.500,00",  # European format
        "฿5,500.00",  # With baht symbol
        "$5,500.00",  # With dollar symbol
        "๕,๕๐๐.๐๐",  # Thai digits
        "5500",  # No separators
    ]

    for currency_str in currency_formats:
        result = engine.validate_and_normalize_field(
            "total_amount",
            currency_str,
            FieldType.CURRENCY,
            0.95
        )

        print(f"\n  Input:      {currency_str}")
        print(f"  Normalized: {result.normalized_value}")
        print(f"  Valid:      {result.is_valid}")
        if result.normalized_value:
            print(f"  Parsed:     {float(result.normalized_value):,.2f}")

    print()


def example_tax_id_validation():
    """Example: Validate Thai tax IDs."""
    print("=" * 70)
    print("EXAMPLE 3: Thai Tax ID Validation")
    print("=" * 70)

    engine = create_validation_engine()

    tax_ids = [
        "1234567890128",  # Valid 13-digit format
        "123456789",  # Too short
        "123456789012A",  # Contains letter
        "12 34 56 78 90 12 8",  # With spaces (should be cleaned)
    ]

    for tax_id in tax_ids:
        result = engine.validate_and_normalize_field(
            "vendor_tax_id",
            tax_id,
            FieldType.TAX_ID,
            0.95
        )

        print(f"\n  Input:      {tax_id}")
        print(f"  Normalized: {result.normalized_value}")
        print(f"  Valid:      {result.is_valid}")
        if result.error_message:
            print(f"  Error:      {result.error_message}")
        if result.needs_review:
            print(f"  Review:     YES - requires manual check")

    print()


def example_field_validation():
    """Example: Validate individual fields with confidence adjustment."""
    print("=" * 70)
    print("EXAMPLE 4: Field Validation with Confidence Adjustment")
    print("=" * 70)

    engine = create_validation_engine()

    # Valid date field
    result_valid = engine.validate_and_normalize_field(
        "invoice_date",
        "15/02/2567",
        FieldType.DATE,
        original_confidence=0.95
    )

    print(f"\n  VALID FIELD:")
    print(f"    Original Value:        15/02/2567")
    print(f"    Normalized Value:      {result_valid.normalized_value}")
    print(f"    Is Valid:              {result_valid.is_valid}")
    print(f"    Original Confidence:   0.95")
    print(f"    Confidence Adjustment: {result_valid.confidence_adjustment:.2f}")
    print(f"    New Confidence:        {(0.95 - result_valid.confidence_adjustment):.2f}")

    # Invalid date field
    result_invalid = engine.validate_and_normalize_field(
        "invoice_date",
        "invalid_date",
        FieldType.DATE,
        original_confidence=0.95
    )

    print(f"\n  INVALID FIELD:")
    print(f"    Original Value:        invalid_date")
    print(f"    Normalized Value:      {result_invalid.normalized_value}")
    print(f"    Is Valid:              {result_invalid.is_valid}")
    print(f"    Original Confidence:   0.95")
    print(f"    Confidence Adjustment: {result_invalid.confidence_adjustment:.2f}")
    print(f"    New Confidence:        {(0.95 - result_invalid.confidence_adjustment):.2f}")
    print(f"    Needs Review:          {result_invalid.needs_review}")
    print(f"    Error:                 {result_invalid.error_message}")

    print()


def example_document_validation():
    """Example: Validate complete document with multiple fields."""
    print("=" * 70)
    print("EXAMPLE 5: Complete Document Validation")
    print("=" * 70)

    engine = create_validation_engine()

    invoice_document = {
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

    result = engine.validate_document(invoice_document)

    print(f"\n  Document ID:              {result['id']}")
    print(f"  Overall Valid:            {result['validation']['status']}")
    print(f"  Fields Needing Review:    {result['validation']['fields_needing_review']}")
    print(f"  Confidence Adjustment:    {result['validation']['confidence_adjustment']:.4f}")

    print(f"\n  NORMALIZED FIELDS:")
    print(f"    vendor_name:     {result.get('vendor_name', 'N/A')}")
    print(f"    vendor_tax_id:   {result.get('vendor_tax_id', 'N/A')}")
    print(f"    invoice_date:    {result.get('invoice_date', 'N/A')}")
    print(f"    subtotal:        {result.get('subtotal', 'N/A')}")
    print(f"    total_amount:    {result.get('total_amount', 'N/A')}")

    if "confidence" in result:
        print(f"\n  UPDATED CONFIDENCE:")
        for field, conf in result["confidence"].items():
            print(f"    {field:20s}: {conf:.2f}")

    print()


def example_document_with_errors():
    """Example: Document with validation errors."""
    print("=" * 70)
    print("EXAMPLE 6: Document with Validation Errors")
    print("=" * 70)

    engine = create_validation_engine()

    problematic_document = {
        "id": "INV-2024-ERROR",
        "vendor_name": "Company XYZ",
        "vendor_tax_id": "12345",  # Too short - will fail
        "invoice_date": "invalid-date",  # Invalid format - will fail
        "subtotal": "5,000.00",
        "total_amount": "3,000.00",  # Less than subtotal - warning
        "confidence": {
            "vendor_tax_id": 0.85,
            "invoice_date": 0.90,
            "subtotal": 0.95,
            "total_amount": 0.95,
        }
    }

    result = engine.validate_document(problematic_document)

    print(f"\n  Document ID:              {result['id']}")
    print(f"  Overall Valid:            {result['validation']['status']}")
    print(f"  Issues Found:             {result['validation']['issues_count']}")

    print(f"\n  FIELDS NEEDING REVIEW:")
    if result['validation']['fields_needing_review']:
        for field in result['validation']['fields_needing_review']:
            print(f"    - {field}")
    else:
        print(f"    (None)")

    print(f"\n  CONFIDENCE ADJUSTMENTS:")
    if "confidence" in result:
        for field, conf in result["confidence"].items():
            if conf < 1.0:  # Only show adjusted ones
                original = problematic_document["confidence"].get(field, 0.0)
                adjustment = original - conf
                print(f"    {field:20s}: {original:.2f} → {conf:.2f} (Δ -{adjustment:.2f})")

    print()


def example_batch_processing():
    """Example: Process multiple documents in batch."""
    print("=" * 70)
    print("EXAMPLE 7: Batch Document Processing")
    print("=" * 70)

    engine = create_validation_engine()

    documents = [
        {
            "id": "INV-2024-001",
            "vendor_name": "ABC Co.",
            "invoice_date": "15/02/2567",
            "total_amount": "5,500.00",
        },
        {
            "id": "INV-2024-002",
            "vendor_name": "XYZ Ltd.",
            "invoice_date": "20/02/2567",
            "total_amount": "3,000.00",
        },
        {
            "id": "INV-2024-003",
            "vendor_name": "PQR Corp.",
            "invoice_date": "invalid",  # This will cause an error
            "total_amount": "2,500.00",
        },
    ]

    print(f"\n  Processing {len(documents)} documents...\n")

    results = []
    for doc in documents:
        result = engine.validate_document(doc)
        results.append(result)

        status = result['validation']['status']
        needs_review = len(result['validation']['fields_needing_review'])
        print(f"  {result['id']:20s} | Status: {status:7s} | Issues: {needs_review}")

    # Summary
    valid_count = sum(1 for r in results if r['validation']['status'] == 'valid')
    total_count = len(results)

    print(f"\n  SUMMARY:")
    print(f"    Total Processed:  {total_count}")
    print(f"    Valid:            {valid_count}")
    print(f"    Needs Review:     {total_count - valid_count}")
    print(f"    Success Rate:     {(valid_count/total_count)*100:.1f}%")

    print()


def example_json_output():
    """Example: Full JSON output structure."""
    print("=" * 70)
    print("EXAMPLE 8: JSON Output Structure")
    print("=" * 70)

    engine = create_validation_engine()

    document = {
        "id": "INV-2024-JSON",
        "vendor_tax_id": "1234567890128",
        "invoice_date": "15/02/2567",
        "total_amount": "5,500.00",
        "confidence": {
            "vendor_tax_id": 0.92,
            "invoice_date": 0.95,
            "total_amount": 0.98,
        }
    }

    result = engine.validate_document(document)

    # Extract validation result
    validation_meta = result.get('validation', {})

    output = {
        "document_id": result['id'],
        "validation_status": validation_meta.get('status', 'unknown'),
        "fields_needing_review": validation_meta.get('fields_needing_review', []),
        "overall_confidence_adjustment": validation_meta.get('confidence_adjustment', 0.0),
        "normalized_fields": {
            "vendor_tax_id": result.get('vendor_tax_id'),
            "invoice_date": result.get('invoice_date'),
            "total_amount": result.get('total_amount'),
        },
        "updated_confidences": result.get('confidence', {}),
    }

    print("\n  JSON OUTPUT:")
    print(json.dumps(output, indent=2, ensure_ascii=False))

    print()


def test_accuracy():
    """Accuracy test on known cases."""
    print("=" * 70)
    print("TEST: Validation Accuracy")
    print("=" * 70)

    engine = create_validation_engine()

    test_cases = [
        {
            "name": "Thai date with Buddhist year",
            "field": "invoice_date",
            "value": "15/02/2567",
            "type": FieldType.DATE,
            "expected_normalized": "2024-02-15",
            "expected_valid": True,
        },
        {
            "name": "US format currency",
            "field": "total_amount",
            "value": "5,500.00",
            "type": FieldType.CURRENCY,
            "expected_normalized": "5500.0",
            "expected_valid": True,
        },
        {
            "name": "European format currency",
            "field": "total_amount",
            "value": "5.500,00",
            "type": FieldType.CURRENCY,
            "expected_normalized": "5500.0",
            "expected_valid": True,
        },
        {
            "name": "Invalid date",
            "field": "invoice_date",
            "value": "invalid",
            "type": FieldType.DATE,
            "expected_valid": False,
        },
    ]

    passed = 0
    failed = 0

    for test in test_cases:
        result = engine.validate_and_normalize_field(
            test["field"],
            test["value"],
            test["type"],
            0.95
        )

        # Check validity
        valid_ok = result.is_valid == test["expected_valid"]

        # Check normalized value if expected
        normalized_ok = True
        if "expected_normalized" in test:
            normalized_ok = result.normalized_value == test["expected_normalized"]

        passed_test = valid_ok and normalized_ok

        status = "✓ PASS" if passed_test else "✗ FAIL"
        print(f"\n  {status} | {test['name']}")
        print(f"         Input:     {test['value']}")
        print(f"         Expected:  valid={test['expected_valid']}", end="")
        if "expected_normalized" in test:
            print(f", normalized={test['expected_normalized']}", end="")
        print()
        print(f"         Got:       valid={result.is_valid}, normalized={result.normalized_value}")

        if passed_test:
            passed += 1
        else:
            failed += 1

    print(f"\n  RESULTS: {passed} passed, {failed} failed")
    print()


if __name__ == "__main__":
    # Run all examples
    example_thai_date_parsing()
    example_currency_normalization()
    example_tax_id_validation()
    example_field_validation()
    example_document_validation()
    example_document_with_errors()
    example_batch_processing()
    example_json_output()
    test_accuracy()

    print("=" * 70)
    print("All examples completed successfully!")
    print("=" * 70)
