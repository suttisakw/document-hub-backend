"""
Document Classifier - Examples and Testing

This module provides usage examples and test utilities for the document classifier.
"""

from app.services.document_classifier import (
    KeywordClassifier,
    HybridClassifier,
    DummyMLClassifier,
    create_classifier,
    KeywordSet,
    DocumentType,
)


# ============================================================================
# Example 1: Basic Keyword Classification
# ============================================================================

def example_basic_keyword_classification():
    """Simple keyword-based classification example."""
    print("\n=== Example 1: Basic Keyword Classification ===")

    # Create classifier with default keyword sets
    classifier = KeywordClassifier()

    # Sample invoice OCR
    invoice_lines = [
        "ACME CORPORATION",
        "INVOICE",
        "Invoice Number: INV-2026-001",
        "Date: 2026-02-13",
        "Customer Name: ABC Industries",
        "Item 1: Professional Services",
        "Quantity: 40",
        "Unit Price: 250.00",
        "Amount Due: 15,750.00",
        "Payment Terms: Net 30",
    ]

    result = classifier.classify(ocr_lines=invoice_lines)

    print(f"Document Type: {result.document_type.value}")
    print(f"Confidence: {result.confidence_score:.2%}")
    print(f"Matched Keywords: {result.matched_keywords}")
    print(f"Raw Scores: {result.raw_scores}")
    print()
    return result


# ============================================================================
# Example 2: Receipt Classification
# ============================================================================

def example_receipt_classification():
    """Receipt classification example."""
    print("=== Example 2: Receipt Classification ===")

    classifier = KeywordClassifier()

    receipt_lines = [
        "7-ELEVEN",
        "Store #12345",
        "Receipt",
        "Thank you for your purchase!",
        "Coca Cola 1.5L                 60.00",
        "Sandwich                        45.00",
        "Subtotal:                      105.00",
        "Change:                        45.00",
        "Paid in cash",
        "Transaction #567890",
    ]

    result = classifier.classify(ocr_lines=receipt_lines)

    print(f"Document Type: {result.document_type.value}")
    print(f"Confidence: {result.confidence_score:.2%}")
    print(f"Matched Keywords: {result.matched_keywords}")
    print()
    return result


# ============================================================================
# Example 3: Purchase Order Classification
# ============================================================================

def example_po_classification():
    """Purchase order classification example."""
    print("=== Example 3: Purchase Order Classification ===")

    classifier = KeywordClassifier()

    po_lines = [
        "PURCHASE ORDER",
        "PO Number: PO-2026-00542",
        "Order Date: 2026-02-10",
        "Delivery Date: 2026-03-10",
        "Vendor: TechSupply Corp",
        "Ship To: Warehouse A",
        "Item 1 Description: Server Hardware",
        "Quantity: 5",
        "Item 2: Network Cables (Cat6a)",
        "Quantity: 100",
        "Terms: Net 60",
    ]

    result = classifier.classify(ocr_lines=po_lines)

    print(f"Document Type: {result.document_type.value}")
    print(f"Confidence: {result.confidence_score:.2%}")
    print(f"Matched Keywords: {result.matched_keywords}")
    print()
    return result


# ============================================================================
# Example 4: Tax Invoice (Thai) Classification
# ============================================================================

def example_tax_invoice_thai():
    """Tax invoice with Thai text example."""
    print("=== Example 4: Thai Tax Invoice Classification ===")

    classifier = KeywordClassifier()

    tax_invoice_lines = [
        "ใบกำกับภาษีอากร",  # Tax invoice
        "เลขที่: INV-TH-2026-042",
        "เลขประจำตัวผู้เสียภาษีอากร: 0123456789012",
        "ผู้ขาย: บริษัท ธุรกิจไทย จำกัด",
        "ผู้ซื้อ: บริษัท เอ็กซ์วายแซด จำกัด",
        "วันที่: 13 กุมภาพันธ์ 2566",
        "ภาษีมูลค่าเพิ่ม (VAT): 2,000.00 บาท",
        "รวมทั้งสิ้น: 22,000.00 บาท",
    ]

    result = classifier.classify(ocr_lines=tax_invoice_lines)

    print(f"Document Type: {result.document_type.value}")
    print(f"Confidence: {result.confidence_score:.2%}")
    print(f"Matched Keywords: {result.matched_keywords}")
    print()
    return result


# ============================================================================
# Example 5: Hybrid Classification with ML Fallback
# ============================================================================

def example_hybrid_classification():
    """Hybrid classifier with ML fallback."""
    print("=== Example 5: Hybrid Classification (Keyword + ML Fallback) ===")

    keyword_classifier = KeywordClassifier()
    ml_classifier = DummyMLClassifier()

    hybrid_classifier = HybridClassifier(
        keyword_classifier=keyword_classifier,
        ml_classifier=ml_classifier,
        confidence_threshold_low=0.4,
        confidence_threshold_high=0.8,
    )

    # Ambiguous document
    ambiguous_lines = [
        "Document",
        "Number: 2026-042",
        "Date: Feb 13",
        "Amount: 5,000",
        "Please process",
    ]

    result = hybrid_classifier.classify(ocr_lines=ambiguous_lines)

    print(f"Document Type: {result.document_type.value}")
    print(f"Confidence: {result.confidence_score:.2%}")
    print(f"Classification Method: {result.evidence.get('method', 'unknown')}")
    print()
    return result


# ============================================================================
# Example 6: Custom Keyword Set
# ============================================================================

def example_custom_keyword_set():
    """Custom keyword set for specialized document type."""
    print("=== Example 6: Custom Keyword Set ===")

    # Create custom keyword set for "Statement of Account"
    custom_keywords = KeywordSet(
        name="statement",
        primary_keywords=[
            "statement of account",
            "account statement",
            "monthly statement",
            "statement period",
        ],
        secondary_keywords=[
            "opening balance",
            "closing balance",
            "transaction",
            "debit",
            "credit",
        ],
        tertiary_keywords=["date", "amount", "balance", "account number"],
        negative_keywords=["invoice", "receipt", "purchase order"],
        minimum_score_threshold=0.3,
    )

    # Use custom classifier with default + custom sets
    classifier = KeywordClassifier(
        keyword_sets={
            "invoice": KeywordSet.for_invoice(),
            "receipt": KeywordSet.for_receipt(),
            "purchase_order": KeywordSet.for_purchase_order(),
            "tax_invoice": KeywordSet.for_tax_invoice(),
            "statement": custom_keywords,
        }
    )

    statement_lines = [
        "MONTHLY ACCOUNT STATEMENT",
        "Account #123456789",
        "Statement Period: Jan 1 - Jan 31, 2026",
        "Opening Balance: 50,000.00",
        "Debit: 12,500.00",
        "Credit: 8,750.00",
        "Closing Balance: 46,250.00",
    ]

    result = classifier.classify(ocr_lines=statement_lines)

    print(f"Document Type: {result.document_type.value}")
    print(f"Confidence: {result.confidence_score:.2%}")
    print()
    return result


# ============================================================================
# Example 7: Using Factory Function
# ============================================================================

def example_factory_function():
    """Using create_classifier factory function."""
    print("=== Example 7: Using Factory Function ===")

    # Create keyword-only classifier
    classifier1 = create_classifier(classifier_type="keyword")
    print(f"Created classifier type: {type(classifier1).__name__}")

    # Create hybrid classifier with ML fallback
    classifier2 = create_classifier(classifier_type="hybrid", use_ml=True)
    print(f"Created classifier type: {type(classifier2).__name__}")

    # Classify with both
    test_lines = ["INVOICE", "Invoice Number: INV-001", "Total: 1,000"]

    result1 = classifier1.classify(ocr_lines=test_lines)
    result2 = classifier2.classify(ocr_lines=test_lines)

    print(f"Keyword classifier: {result1.document_type.value} ({result1.confidence_score:.2%})")
    print(f"Hybrid classifier: {result2.document_type.value} ({result2.confidence_score:.2%})")
    print()


# ============================================================================
# Example 8: Scoring Details
# ============================================================================

def example_scoring_details():
    """Show detailed scoring breakdown."""
    print("=== Example 8: Scoring Details ===")

    classifier = KeywordClassifier()

    # Document with mixed signals
    mixed_lines = [
        "ACME CORPORATION",
        "INVOICE/RECEIPT",
        "Thank you for your purchase",
        "Invoice: INV-001",
        "Amount: 5,000.00",
        "Payment received",
    ]

    result = classifier.classify(ocr_lines=mixed_lines)

    print(f"Winning Type: {result.document_type.value}")
    print(f"Winning Score: {result.confidence_score:.4f}")
    print("\nAll Scores (sorted):")
    for doc_type, score in sorted(result.raw_scores.items(), key=lambda x: x[1], reverse=True):
        print(f"  {doc_type:20s}: {score:6.4f}")
    print()


# ============================================================================
# Example 9: Batch Classification
# ============================================================================

def example_batch_classification():
    """Batch classification of multiple documents."""
    print("=== Example 9: Batch Classification ===")

    classifier = KeywordClassifier()

    documents = [
        {
            "name": "doc1",
            "lines": ["INVOICE", "INV-001", "Total: 500"],
        },
        {
            "name": "doc2",
            "lines": ["RECEIPT", "Store #123", "Change: 50"],
        },
        {
            "name": "doc3",
            "lines": ["PURCHASE ORDER", "PO-001", "Vendor: ABC"],
        },
    ]

    print("Batch Classification Results:")
    print(f"{'Document':<10} {'Type':<20} {'Confidence':<12}")
    print("-" * 42)

    for doc in documents:
        result = classifier.classify(ocr_lines=doc["lines"])
        print(f"{doc['name']:<10} {result.document_type.value:<20} {result.confidence_score:>6.2%}")

    print()


# ============================================================================
# Test Helper Functions
# ============================================================================

def test_classifier_accuracy():
    """Test classifier accuracy on known examples."""
    print("\n=== Classifier Accuracy Test ===\n")

    test_cases = [
        {
            "name": "Invoice",
            "lines": [
                "INVOICE",
                "Invoice Number: INV-2026-001",
                "Subtotal: 1000",
                "Tax: 100",
                "Total: 1100",
            ],
            "expected": "invoice",
        },
        {
            "name": "Receipt",
            "lines": [
                "RECEIPT",
                "Store #456",
                "Thank you",
                "Total: 500",
                "Change: 50",
            ],
            "expected": "receipt",
        },
        {
            "name": "PO",
            "lines": [
                "PURCHASE ORDER",
                "PO: PO-2026-001",
                "Vendor: Supplier Inc",
                "Delivery: 2026-03-01",
            ],
            "expected": "purchase_order",
        },
    ]

    classifier = KeywordClassifier()
    passed = 0
    failed = 0

    for test in test_cases:
        result = classifier.classify(ocr_lines=test["lines"])
        is_correct = result.document_type.value == test["expected"]

        status = "✓ PASS" if is_correct else "✗ FAIL"
        print(f"{status} | {test['name']:<15} | Expected: {test['expected']:<15} | Got: {result.document_type.value:<15} | Confidence: {result.confidence_score:.2%}")

        if is_correct:
            passed += 1
        else:
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    print()


if __name__ == "__main__":
    # Run all examples
    example_basic_keyword_classification()
    example_receipt_classification()
    example_po_classification()
    example_tax_invoice_thai()
    example_hybrid_classification()
    example_custom_keyword_set()
    example_factory_function()
    example_scoring_details()
    example_batch_classification()
    test_classifier_accuracy()

    print("\n=== All Examples Complete ===\n")
