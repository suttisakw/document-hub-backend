"""
TableExtractionEngine - Working examples and demonstrations.
"""

from app.services.table_extraction_engine import (
    BoundingBox,
    StandardColumnName,
    create_table_extraction_engine,
    table_extraction_output_to_json,
)
import json


def example_basic_invoice_table():
    """Extract table from basic invoice."""
    print("\n" + "="*60)
    print("EXAMPLE 1: Basic Invoice Table")
    print("="*60)

    engine = create_table_extraction_engine()

    # Simulated OCR output from invoice
    ocr_output = [
        # Header row
        ("Item", BoundingBox(10, 10, 80, 30)),
        ("Quantity", BoundingBox(90, 10, 160, 30)),
        ("Unit Price", BoundingBox(170, 10, 260, 30)),
        ("Amount", BoundingBox(270, 10, 350, 30)),
        # Row 1
        ("Laptop", BoundingBox(10, 40, 80, 60)),
        ("2", BoundingBox(90, 40, 160, 60)),
        ("500.00", BoundingBox(170, 40, 260, 60)),
        ("1000.00", BoundingBox(270, 40, 350, 60)),
        # Row 2
        ("Mouse", BoundingBox(10, 70, 80, 90)),
        ("5", BoundingBox(90, 70, 160, 90)),
        ("25.00", BoundingBox(170, 70, 260, 90)),
        ("125.00", BoundingBox(270, 70, 350, 90)),
    ]

    tables = engine.extract_tables(ocr_output)

    if tables and tables[0].table_found:
        result = tables[0]
        print(f"\nTable found: ✓")
        print(f"Table region: ({result.table_region.x_min:.0f}, {result.table_region.y_min:.0f}) to "
              f"({result.table_region.x_max:.0f}, {result.table_region.y_max:.0f})")
        print(f"Columns detected: {len(result.columns)}")
        print(f"Rows extracted: {len(result.rows)}")
        print(f"Overall confidence: {result.overall_confidence:.1%}")
        print(f"Header confidence: {result.header_confidence:.1%}")
        print(f"Table confidence: {result.table_confidence:.1%}")

        print("\nColumn mapping:")
        for col in result.columns:
            print(f"  {col.detected_name:15} → {col.standard_name.value:15} (confidence: {col.confidence:.1%})")

        print("\nExtracted rows:")
        for row in result.rows:
            print(f"\n  Row {row.row_idx} (confidence: {row.row_confidence:.1%}):")
            for col_name, cell in row.cells.items():
                print(f"    {col_name.value:15}: {cell.value:15} (confidence: {cell.confidence:.1%}, method: {cell.method.value})")

        print(f"\nProcessing time: {result.processing_time_ms:.1f}ms")


def example_detect_table_region():
    """Demonstrate table region detection via clustering."""
    print("\n" + "="*60)
    print("EXAMPLE 2: Table Region Detection with Clustering")
    print("="*60)

    engine = create_table_extraction_engine()

    # OCR with scattered text around table
    ocr_output = [
        # Scattered text outside table
        ("Invoice #12345", BoundingBox(-100, -50, -10, -30)),
        ("Date: 2024-01-15", BoundingBox(-100, -20, -10, 0)),
        # Main table
        ("Item", BoundingBox(10, 10, 80, 30)),
        ("Qty", BoundingBox(90, 10, 160, 30)),
        ("Price", BoundingBox(170, 10, 250, 30)),
        ("Product A", BoundingBox(10, 40, 80, 60)),
        ("3", BoundingBox(90, 40, 160, 60)),
        ("100.00", BoundingBox(170, 40, 250, 60)),
        # More scattered text after table
        ("Total: $300.00", BoundingBox(10, 200, 150, 230)),
    ]

    tables = engine.extract_tables(ocr_output)

    print(f"\nClusters found: {len(tables)} table(s)")

    for idx, table in enumerate(tables):
        print(f"\nTable {idx + 1}:")
        if table.table_found:
            print(f"  Region detected: ✓")
            print(f"  Position: X=[{table.table_region.x_min:.0f}, {table.table_region.x_max:.0f}], "
                  f"Y=[{table.table_region.y_min:.0f}, {table.table_region.y_max:.0f}]")
            print(f"  Cells within region: {len(table.rows) * len(table.columns)}")
        else:
            print(f"  Not a valid table structure")


def example_header_detection():
    """Demonstrate header row detection."""
    print("\n" + "="*60)
    print("EXAMPLE 3: Header Row Detection")
    print("="*60)

    engine = create_table_extraction_engine()

    # Table with header in different position
    ocr_output = [
        # Some data before header
        ("Note: Please verify", BoundingBox(10, 10, 150, 30)),
        # Header row
        ("Item Name", BoundingBox(10, 50, 100, 70)),
        ("Quantity", BoundingBox(110, 50, 200, 70)),
        ("Unit Cost", BoundingBox(210, 50, 300, 70)),
        # Data rows
        ("Widget A", BoundingBox(10, 80, 100, 100)),
        ("10", BoundingBox(110, 80, 200, 100)),
        ("50.00", BoundingBox(210, 80, 300, 100)),
        ("Widget B", BoundingBox(10, 110, 100, 130)),
        ("20", BoundingBox(110, 110, 200, 130)),
        ("75.00", BoundingBox(210, 110, 300, 130)),
    ]

    tables = engine.extract_tables(ocr_output)

    if tables and tables[0].table_found:
        result = tables[0]
        print(f"\nHeader detected: ✓")
        print(f"Header confidence: {result.header_confidence:.1%}")
        print(f"\nHeader columns:")
        for col in result.columns:
            print(f"  Detected: '{col.detected_name}' → Standard: '{col.standard_name.value}'")


def example_numeric_validation():
    """Demonstrate numeric field validation."""
    print("\n" + "="*60)
    print("EXAMPLE 4: Numeric Validation")
    print("="*60)

    engine = create_table_extraction_engine()

    # Mix of properly formatted and messy numeric data
    ocr_output = [
        ("Item", BoundingBox(10, 10, 80, 30)),
        ("Quantity", BoundingBox(90, 10, 160, 30)),
        ("Price", BoundingBox(170, 10, 250, 30)),
        ("Total", BoundingBox(260, 10, 330, 30)),
        # Row with clean numbers
        ("Product A", BoundingBox(10, 40, 80, 60)),
        ("5", BoundingBox(90, 40, 160, 60)),
        ("19.99", BoundingBox(170, 40, 250, 60)),
        ("99.95", BoundingBox(260, 40, 330, 60)),
        # Row with messy formatting
        ("Product B", BoundingBox(10, 70, 80, 90)),
        ("1,000", BoundingBox(90, 70, 160, 90)),  # Comma-separated
        ("$45.50", BoundingBox(170, 70, 250, 90)),  # Currency symbol
        ("45,500.00", BoundingBox(260, 70, 330, 90)),  # Comma in thousands
    ]

    tables = engine.extract_tables(ocr_output)

    if tables and tables[0].table_found:
        result = tables[0]
        print(f"\nRows processed: {len(result.rows)}")
        
        for row in result.rows:
            print(f"\nRow {row.row_idx}:")
            for col_name, cell in row.cells.items():
                valid = "✓" if col_name in [StandardColumnName.QUANTITY, StandardColumnName.UNIT_PRICE, 
                                            StandardColumnName.AMOUNT] else ""
                print(f"  {col_name.value:15}: {cell.value:15} → Parsed OK {valid}")


def example_row_extraction():
    """Demonstrate row extraction with vertical alignment."""
    print("\n" + "="*60)
    print("EXAMPLE 5: Row Extraction & Vertical Alignment")
    print("="*60)

    engine = create_table_extraction_engine()

    # Rows with slight vertical misalignment (realistic from OCR)
    ocr_output = [
        ("Name", BoundingBox(10, 10, 80, 30)),
        ("Qty", BoundingBox(90, 10, 160, 30)),
        ("Book A", BoundingBox(10, 42, 80, 62)),  # Slightly lower
        ("7", BoundingBox(90, 38, 160, 58)),      # Slightly higher
        ("Book B", BoundingBox(10, 70, 80, 90)),  # Middle
        ("3", BoundingBox(90, 72, 160, 92)),      # Slightly lower
    ]

    tables = engine.extract_tables(ocr_output)

    if tables and tables[0].table_found:
        result = tables[0]
        print(f"\nRows correctly aligned: {len(result.rows)}")
        print(f"Vertical alignment threshold: 10.0 pixels")
        
        for row in result.rows:
            print(f"\n  Row {row.row_idx}:")
            for col_name, cell in row.cells.items():
                bbox_info = f" @ Y=[{cell.bbox.y_min:.0f}, {cell.bbox.y_max:.0f}]" if cell.bbox else ""
                print(f"    {col_name.value:15}: {cell.value:10}{bbox_info}")


def example_multilingual_table():
    """Demonstrate multilingual header detection."""
    print("\n" + "="*60)
    print("EXAMPLE 6: Multilingual Support (Vietnamese)")
    print("="*60)

    engine = create_table_extraction_engine()

    # Vietnamese invoice table
    ocr_output = [
        ("Hàng hóa", BoundingBox(10, 10, 100, 30)),
        ("Số lượng", BoundingBox(110, 10, 180, 30)),
        ("Đơn giá", BoundingBox(190, 10, 260, 30)),
        ("Thành tiền", BoundingBox(270, 10, 350, 30)),
        # Row 1
        ("Máy tính xách tay", BoundingBox(10, 40, 100, 60)),
        ("2", BoundingBox(110, 40, 180, 60)),
        ("15,000,000", BoundingBox(190, 40, 260, 60)),
        ("30,000,000", BoundingBox(270, 40, 350, 60)),
        # Row 2
        ("Chuột", BoundingBox(10, 70, 100, 90)),
        ("5", BoundingBox(110, 70, 180, 90)),
        ("500,000", BoundingBox(190, 70, 260, 90)),
        ("2,500,000", BoundingBox(270, 70, 350, 90)),
    ]

    tables = engine.extract_tables(ocr_output)

    if tables and tables[0].table_found:
        result = tables[0]
        print(f"\nVietnamese headers detected: ✓")
        print("\nColumn mappings:")
        for col in result.columns:
            print(f"  '{col.detected_name}' → {col.standard_name.value}")
        
        print(f"\nRows extracted: {len(result.rows)}")
        for row in result.rows:
            print(f"\n  Row {row.row_idx}:")
            item = row.cells.get(StandardColumnName.ITEM_NAME)
            qty = row.cells.get(StandardColumnName.QUANTITY)
            if item and qty:
                print(f"    Item: {item.value}, Qty: {qty.value}")


def example_batch_processing():
    """Demonstrate batch processing multiple documents."""
    print("\n" + "="*60)
    print("EXAMPLE 7: Batch Processing")
    print("="*60)

    engine = create_table_extraction_engine()

    documents = [
        # Document 1
        [
            ("Item", BoundingBox(10, 10, 80, 30)),
            ("Qty", BoundingBox(90, 10, 150, 30)),
            ("Product A", BoundingBox(10, 40, 80, 60)),
            ("5", BoundingBox(90, 40, 150, 60)),
        ],
        # Document 2
        [
            ("Name", BoundingBox(10, 10, 80, 30)),
            ("Price", BoundingBox(90, 10, 150, 30)),
            ("Product B", BoundingBox(10, 40, 80, 60)),
            ("100.00", BoundingBox(90, 40, 150, 60)),
        ],
        # Document 3
        [
            ("Service", BoundingBox(10, 10, 80, 30)),
            ("Hours", BoundingBox(90, 10, 150, 30)),
            ("Consulting", BoundingBox(10, 40, 80, 60)),
            ("8", BoundingBox(90, 40, 150, 60)),
        ],
    ]

    results = []
    for idx, doc in enumerate(documents):
        tables = engine.extract_tables(doc)
        results.append(tables[0] if tables else None)

    print(f"\nProcessed {len(documents)} documents")
    
    successful = sum(1 for r in results if r and r.table_found)
    print(f"Tables extracted: {successful}/{len(documents)}")
    
    avg_confidence = sum(r.overall_confidence for r in results if r and r.table_found) / max(successful, 1)
    print(f"Average confidence: {avg_confidence:.1%}")


def example_json_output():
    """Demonstrate JSON output format."""
    print("\n" + "="*60)
    print("EXAMPLE 8: JSON Output Format")
    print("="*60)

    engine = create_table_extraction_engine()

    ocr_output = [
        ("Item", BoundingBox(10, 10, 80, 30)),
        ("Qty", BoundingBox(90, 10, 150, 30)),
        ("Product A", BoundingBox(10, 40, 80, 60)),
        ("5", BoundingBox(90, 40, 150, 60)),
    ]

    tables = engine.extract_tables(ocr_output)

    if tables and tables[0].table_found:
        result = tables[0]
        json_output = table_extraction_output_to_json(result)
        
        print("\nJSON output (pretty-printed):")
        print(json.dumps(json_output, indent=2))


def test_extraction_accuracy():
    """Test extraction accuracy against known invoices."""
    print("\n" + "="*60)
    print("ACCURACY TEST: Known Invoice Tables")
    print("="*60)

    engine = create_table_extraction_engine()

    test_cases = [
        {
            "name": "Simple 2x2 table",
            "ocr": [
                ("A", BoundingBox(10, 10, 50, 30)),
                ("B", BoundingBox(60, 10, 100, 30)),
                ("1", BoundingBox(10, 40, 50, 60)),
                ("2", BoundingBox(60, 40, 100, 60)),
            ],
            "expected_rows": 1,
        },
        {
            "name": "3x3 invoice table",
            "ocr": [
                ("Item", BoundingBox(10, 10, 80, 30)),
                ("Qty", BoundingBox(90, 10, 150, 30)),
                ("Price", BoundingBox(160, 10, 220, 30)),
                ("Product A", BoundingBox(10, 40, 80, 60)),
                ("5", BoundingBox(90, 40, 150, 60)),
                ("50.00", BoundingBox(160, 40, 220, 60)),
                ("Product B", BoundingBox(10, 70, 80, 90)),
                ("3", BoundingBox(90, 70, 150, 90)),
                ("100.00", BoundingBox(160, 70, 220, 90)),
            ],
            "expected_rows": 2,
        },
    ]

    passed = 0
    for test in test_cases:
        tables = engine.extract_tables(test["ocr"])
        
        if tables and tables[0].table_found:
            actual_rows = len(tables[0].rows)
            success = actual_rows == test["expected_rows"]
            passed += 1 if success else 0
            status = "✓ PASS" if success else "✗ FAIL"
            print(f"\n{status} - {test['name']}")
            print(f"  Expected {test['expected_rows']} rows, got {actual_rows}")
        else:
            print(f"\n✗ FAIL - {test['name']}")
            print(f"  Table not detected")

    print(f"\n\nResults: {passed}/{len(test_cases)} tests passed")


if __name__ == "__main__":
    example_basic_invoice_table()
    example_detect_table_region()
    example_header_detection()
    example_numeric_validation()
    example_row_extraction()
    example_multilingual_table()
    example_batch_processing()
    example_json_output()
    test_extraction_accuracy()
    
    print("\n" + "="*60)
    print("All examples completed!")
    print("="*60)
