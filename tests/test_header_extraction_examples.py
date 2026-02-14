"""
Working examples for header extraction engine.

Demonstrates all extraction scenarios and features.
"""

from app.services.header_extraction_engine import (
    HeaderExtractionEngine,
    create_extraction_engine,
    TemplateExtractor,
    RegexAnchorExtractor,
    InvoiceFieldType,
)


# ======= EXAMPLE 1: BASIC TEMPLATE EXTRACTION =======

def example_basic_template_extraction():
    """Example 1: Basic extraction with template extractor."""
    print("\n" + "="*70)
    print("EXAMPLE 1: Basic Template Extraction")
    print("="*70)

    # Create extractor with template only
    extractor = TemplateExtractor(confidence_base=0.95)

    ocr_lines = [
        "ACME Corporation",
        "INVOICE",
        "Invoice Number: INV-2024-001",
        "Date: 02/13/2024",
        "Tax ID: 12-3456789",
        "---",
        "Subtotal: 1000.00",
        "VAT (20%): 200.00",
        "Total: 1200.00"
    ]

    field_types = [
        InvoiceFieldType.INVOICE_NUMBER,
        InvoiceFieldType.INVOICE_DATE,
        InvoiceFieldType.TAX_ID,
        InvoiceFieldType.SUBTOTAL,
        InvoiceFieldType.VAT,
        InvoiceFieldType.TOTAL_AMOUNT,
    ]

    results = extractor.extract(ocr_lines, field_types)

    print(f"\nExtracted {len(results)} fields:\n")
    for result in results:
        print(f"✓ {result.field_type.value}")
        print(f"  Value: {result.value}")
        print(f"  Confidence: {result.confidence:.2%}")
        print(f"  Source: {result.source.value}")
        print()


# ======= EXAMPLE 2: REGEX ANCHOR EXTRACTION =======

def example_regex_anchor_extraction():
    """Example 2: Flexible extraction with regex anchors."""
    print("\n" + "="*70)
    print("EXAMPLE 2: Regex Anchor Extraction")
    print("="*70)

    extractor = RegexAnchorExtractor(proximity_window=3)

    # More realistic OCR with variations
    ocr_lines = [
        "INVOICE",
        "",
        "Invoice: INV-2024-001",  # Variation: "Invoice:" instead of "Invoice Number:"
        "Dated: 02/13/2024",
        "",
        "From: TechCorp Solutions",
        "Tax: 12-3456789",  # Variation: "Tax:" instead of "Tax ID:"
        "",
        "Subtotal $1000.00",
        "Tax $200.00",
        "",
        "TOTAL: $1200.00"
    ]

    field_types = [
        InvoiceFieldType.INVOICE_NUMBER,
        InvoiceFieldType.INVOICE_DATE,
        InvoiceFieldType.VENDOR_NAME,
        InvoiceFieldType.TAX_ID,
        InvoiceFieldType.SUBTOTAL,
        InvoiceFieldType.VAT,
        InvoiceFieldType.TOTAL_AMOUNT,
    ]

    results = extractor.extract(ocr_lines, field_types)

    print(f"\nExtracted {len(results)} fields:\n")
    for result in results:
        print(f"✓ {result.field_type.value}")
        print(f"  Value: {result.value}")
        print(f"  Confidence: {result.confidence:.2%}")
        print(f"  Evidence:")
        print(f"    - Proximity Score: {result.evidence.get('proximity_score', 'N/A'):.2%}")
        print(f"    - Text Quality: {result.evidence.get('regex_score', 'N/A'):.2%}")
        print()


# ======= EXAMPLE 3: MULTI-STAGE PIPELINE =======

def example_multi_stage_pipeline():
    """Example 3: Full multi-stage extraction pipeline."""
    print("\n" + "="*70)
    print("EXAMPLE 3: Multi-Stage Pipeline Extraction")
    print("="*70)

    # Create full engine
    engine = create_extraction_engine(
        enable_template=True,
        enable_regex=True,
        enable_ml=False,
        enable_llm=False
    )

    ocr_lines = [
        "ABC Company Invoice",
        "",
        "Invoice #INV-2024-001",
        "Date: 02/13/2024",
        "",
        "From: ABC Company Ltd",
        "Tax ID: 98-7654321",
        "",
        "Items:",
        "Widget A                   100 x 10.00 = 1000.00",
        "",
        "Subtotal:                           1000.00",
        "VAT 20%:                             200.00",
        "Total Amount:                      1200.00"
    ]

    output = engine.extract_invoice_header(ocr_lines)

    print(f"\nOverall Confidence: {output.overall_confidence:.2%}")
    print(f"Extracted at Stage: {output.extracted_at_stage.value}")
    print(f"Processing Time: {output.processing_time_ms:.2f}ms")
    print(f"\nExtracted {len(output.fields)} fields:\n")

    for field_type, result in output.fields.items():
        stage = result.stage.value.replace("stage_", "").replace("_", " ").title()
        print(f"✓ {field_type.value}")
        print(f"  Value: {result.value}")
        print(f"  Confidence: {result.confidence:.2%}")
        print(f"  Stage: {stage}")
        print()


# ======= EXAMPLE 4: SCORING BREAKDOWN =======

def example_scoring_breakdown():
    """Example 4: Detailed scoring breakdown."""
    print("\n" + "="*70)
    print("EXAMPLE 4: Confidence Scoring Breakdown")
    print("="*70)

    regex_extractor = RegexAnchorExtractor()

    ocr_lines = [
        "Invoice Number: INV-2024-001",
        "Date: 02/13/2024",
        "Total: 1000.00"
    ]

    results = regex_extractor.extract(
        ocr_lines,
        [InvoiceFieldType.TOTAL_AMOUNT]
    )

    print("\nSCORING FORMULA:")
    print("Confidence = regex_score × proximity_score × text_quality")
    print()

    for result in results:
        print(f"Field: {result.field_type.value}")
        print(f"Evidence: {result.evidence}")
        print()
        regex_score = result.evidence.get('regex_score', 0.8)
        proximity_score = result.evidence.get('proximity_score', 1.0)
        print(f"Calculation: {regex_score:.2f} × {proximity_score:.2f} = {result.confidence:.4f}")
        print(f"Final Confidence: {result.confidence:.2%}")
        print()


# ======= EXAMPLE 5: BATCH PROCESSING =======

def example_batch_processing():
    """Example 5: Batch processing multiple invoices."""
    print("\n" + "="*70)
    print("EXAMPLE 5: Batch Processing")
    print("="*70)

    engine = create_extraction_engine(enable_template=True, enable_regex=True)

    documents = [
        {
            "name": "Invoice 1",
            "ocr_lines": [
                "INVOICE",
                "Invoice Number: INV-001",
                "Total: 500.00"
            ]
        },
        {
            "name": "Invoice 2",
            "ocr_lines": [
                "RECEIPT",
                "Transaction #: RCP-001",
                "Amount: 250.00"
            ]
        },
        {
            "name": "Invoice 3",
            "ocr_lines": [
                "Purchase Order",
                "PO Number: PO-2024-001",
                "Total Value: 5000.00"
            ]
        }
    ]

    print(f"\nProcessing {len(documents)} documents...\n")

    total_time = 0.0
    for doc in documents:
        output = engine.extract_invoice_header(doc["ocr_lines"])
        total_time += output.processing_time_ms
        extracted_count = len([f for f in output.fields.values() if f.value])

        print(f"{doc['name']}: Extracted {extracted_count} fields in {output.processing_time_ms:.1f}ms")

    print(f"\nTotal Processing Time: {total_time:.1f}ms")
    print(f"Average per Document: {total_time / len(documents):.1f}ms")


# ======= EXAMPLE 6: CUSTOM FIELD EXTRACTION =======

def example_custom_field_selection():
    """Example 6: Extract only specific fields."""
    print("\n" + "="*70)
    print("EXAMPLE 6: Custom Field Selection")
    print("="*70)

    engine = create_extraction_engine()

    ocr_lines = [
        "INVOICE",
        "Invoice No: INV-2024-001",
        "Date: 02/13/2024",
        "Vendor: ABC Corp",
        "Tax ID: 12-345-6789",
        "Subtotal: 1000.00",
        "VAT: 200.00",
        "Total: 1200.00"
    ]

    # Extract only specific fields
    field_types = [
        InvoiceFieldType.INVOICE_NUMBER,
        InvoiceFieldType.TOTAL_AMOUNT,
        InvoiceFieldType.TAX_ID
    ]

    output = engine.extract_invoice_header(
        ocr_lines=ocr_lines,
        field_types=field_types
    )

    print(f"\nRequested {len(field_types)} fields:")
    for ft in field_types:
        print(f"  - {ft.value}")

    print(f"\nExtracted {len(output.fields)} fields:\n")
    for field_type, result in output.fields.items():
        status = "✓" if result.value else "✗"
        print(f"{status} {field_type.value}: {result.value} ({result.confidence:.2%})")


# ======= EXAMPLE 7: CONFIDENCE THRESHOLDS =======

def example_confidence_thresholds():
    """Example 7: Filtering by confidence threshold."""
    print("\n" + "="*70)
    print("EXAMPLE 7: Confidence Thresholds")
    print("="*70)

    engine = create_extraction_engine()

    ocr_lines = [
        "INVOICE",
        "Invoice: INV-001",
        "Date: 02/13/2024",
        "Amount: 1000.00"
    ]

    output = engine.extract_invoice_header(ocr_lines)

    print(f"\nAll extracted fields ({len(output.fields)}):")
    for field_type, result in output.fields.items():
        print(f"  {field_type.value}: {result.confidence:.2%}")

    # Filter by threshold
    thresholds = [0.5, 0.7, 0.9]
    for threshold in thresholds:
        high_conf = {
            ft: result for ft, result in output.fields.items()
            if result.confidence >= threshold
        }
        print(f"\nFields with confidence >= {threshold:.0%}: {len(high_conf)}")


# ======= EXAMPLE 8: FAILED EXTRACTION HANDLING =======

def example_failed_extraction():
    """Example 8: Handling documents with missing/poor OCR."""
    print("\n" + "="*70)
    print("EXAMPLE 8: Failed Extraction Handling")
    print("="*70)

    engine = create_extraction_engine()

    # Poor quality OCR
    ocr_lines = [
        "xxxxx",
        "!!!!!",
        "12345",
        "=====",
    ]

    output = engine.extract_invoice_header(ocr_lines)

    print(f"\nOverall Confidence: {output.overall_confidence:.2%}")
    print(f"Fields Extracted: {len([f for f in output.fields.values() if f.value])}")
    print(f"\nDocument Quality: {'Poor' if output.overall_confidence < 0.5 else 'Acceptable'}")


# ======= EXAMPLE 9: THAI LANGUAGE SUPPORT =======

def example_thai_language():
    """Example 9: Thai language invoice extraction."""
    print("\n" + "="*70)
    print("EXAMPLE 9: Thai Language Support")
    print("="*70)

    template_extractor = TemplateExtractor()

    # Thai invoice
    ocr_lines = [
        "บริษัท ACME",
        "ใบแจ้งหนี้",  # Invoice
        "เลขที่: INV-2024-001",  # Number
        "วันที่: 13/02/2024",  # Date
        "รหัสประจำตัวผู้เสียภาษี: 12-3456789",  # Tax ID
        "รวม: 1000.00 บาท"  # Total
    ]

    print("\nThai Invoice OCR:")
    for line in ocr_lines[:3]:
        print(f"  {line}")

    results = template_extractor.extract(
        ocr_lines,
        [InvoiceFieldType.INVOICE_NUMBER, InvoiceFieldType.TOTAL_AMOUNT]
    )

    print(f"\nExtracted {len(results)} fields")


# ======= ACCURACY TEST =======

def test_extraction_accuracy():
    """Test extraction accuracy with known documents."""
    print("\n" + "="*70)
    print("ACCURACY TEST: DocumentClassification")
    print("="*70)

    test_cases = [
        {
            "name": "Standard Invoice",
            "ocr_lines": [
                "INVOICE",
                "Invoice Number: INV-2024-001",
                "Date: 02/13/2024",
                "Vendor: ABC Corp",
                "Tax ID: 12-345-6789",
                "Subtotal: 1000.00",
                "VAT: 200.00",
                "Total: 1200.00"
            ],
            "expected_fields": 7,
            "expected_high_confidence": 5,
        },
        {
            "name": "Minimal Invoice",
            "ocr_lines": [
                "Invoice #001",
                "Total: 500.00"
            ],
            "expected_fields": 2,
            "expected_high_confidence": 1,
        },
    ]

    engine = create_extraction_engine()
    passed = 0
    total = len(test_cases)

    for test case in test_cases:
        output = engine.extract_invoice_header(test_case["ocr_lines"])
        extracted = len([f for f in output.fields.values() if f.value])
        high_conf = len([f for f in output.fields.values() if f.confidence >= 0.7])

        success = (
            extracted >= test_case.get("expected_fields", 0) and
            high_conf >= test_case.get("expected_high_confidence", 0)
        )

        status = "✓ PASS" if success else "✗ FAIL"
        print(f"\n{status}: {test_case['name']}")
        print(f"  Extracted: {extracted} (expected >= {test_case.get('expected_fields')})")
        print(f"  High Confidence: {high_conf} (expected >= {test_case.get('expected_high_confidence')})")

        if success:
            passed += 1

    print(f"\n\nAccuracy: {passed}/{total} ({passed/total*100:.0f}%)")


# ======= MAIN =======

if __name__ == "__main__":
    example_basic_template_extraction()
    example_regex_anchor_extraction()
    example_multi_stage_pipeline()
    example_scoring_breakdown()
    example_batch_processing()
    example_custom_field_selection()
    example_confidence_thresholds()
    example_failed_extraction()
    example_thai_language()
    test_extraction_accuracy()

    print("\n" + "="*70)
    print("All examples completed!")
    print("="*70 + "\n")
