"""
Comprehensive test suite for TableExtractionEngine.
"""

import pytest
from app.services.table_extraction_engine import (
    BoundingBox,
    BboxClusterer,
    HeaderDetector,
    RowExtractor,
    NumericValidator,
    TableExtractionEngine,
    StandardColumnName,
    ColumnType,
    create_table_extraction_engine,
)


# ====== CLUSTERING TESTS ======

class TestBboxClusterer:
    """Test bounding box clustering."""

    def test_cluster_simple_grid(self):
        """Test clustering simple grid of boxes."""
        clusterer = BboxClusterer(distance_threshold=50.0)
        
        # Create 4 boxes in a grid
        bboxes = [
            ("A", BoundingBox(0, 0, 20, 20)),
            ("B", BoundingBox(30, 0, 50, 20)),
            ("C", BoundingBox(0, 30, 20, 50)),
            ("D", BoundingBox(30, 30, 50, 50)),
        ]
        
        clusters = clusterer.cluster_bboxes(bboxes)
        assert len(clusters) == 1  # All should be in one cluster
        assert len(clusters[0]) == 4

    def test_cluster_separated_groups(self):
        """Test clustering separated groups."""
        clusterer = BboxClusterer(distance_threshold=50.0)
        
        # Group 1: tight cluster
        # Group 2: separated by 100 pixels
        bboxes = [
            ("A", BoundingBox(0, 0, 20, 20)),
            ("B", BoundingBox(30, 0, 50, 20)),
            ("C", BoundingBox(200, 0, 220, 20)),
            ("D", BoundingBox(230, 0, 250, 20)),
        ]
        
        clusters = clusterer.cluster_bboxes(bboxes)
        assert len(clusters) == 2

    def test_detect_table_region_valid(self):
        """Test detecting valid table region."""
        clusterer = BboxClusterer()
        cluster = [
            ("Header1", BoundingBox(10, 10, 50, 30)),
            ("Header2", BoundingBox(60, 10, 100, 30)),
            ("Data1", BoundingBox(10, 40, 50, 60)),
            ("Data2", BoundingBox(60, 40, 100, 60)),
        ]
        
        region = clusterer.detect_table_region(cluster)
        assert region is not None
        assert region.x_min == 10
        assert region.y_min == 10
        assert region.x_max == 100
        assert region.y_max == 60

    def test_detect_table_region_too_small(self):
        """Test that very small clusters are rejected."""
        clusterer = BboxClusterer()
        cluster = [
            ("A", BoundingBox(0, 0, 10, 10)),
            ("B", BoundingBox(20, 0, 30, 10)),
        ]
        
        region = clusterer.detect_table_region(cluster)
        assert region is None  # Only 2 cells, minimum is 4


# ====== HEADER DETECTION TESTS ======

class TestHeaderDetector:
    """Test header row detection."""

    def test_detect_header_row_first_position(self):
        """Test detecting header in first row."""
        detector = HeaderDetector()
        
        cells = [
            ("Item", BoundingBox(10, 0, 50, 20), 0),
            ("Quantity", BoundingBox(60, 0, 100, 20), 0),
            ("Price", BoundingBox(110, 0, 150, 20), 0),
            ("Data1", BoundingBox(10, 30, 50, 50), 1),
        ]
        
        header_row, confidence = detector.detect_header_row(cells, num_rows=2)
        assert header_row == 0
        assert confidence > 0.7

    def test_detect_header_row_middle_position(self):
        """Test detecting header in middle row."""
        detector = HeaderDetector()
        
        cells = [
            ("Data1", BoundingBox(10, 0, 50, 20), 0),
            ("Item", BoundingBox(10, 30, 50, 50), 1),
            ("Quantity", BoundingBox(60, 30, 100, 50), 1),
            ("Data2", BoundingBox(10, 60, 50, 80), 2),
        ]
        
        header_row, confidence = detector.detect_header_row(cells, num_rows=3)
        assert header_row == 1

    def test_map_column_names_perfect_match(self):
        """Test mapping with perfect matches."""
        detector = HeaderDetector()
        
        headers = ["Item Name", "Quantity", "Unit Price", "Amount"]
        mappings = detector.map_column_names(headers)
        
        assert mappings[0][1] == StandardColumnName.ITEM_NAME
        assert mappings[1][1] == StandardColumnName.QUANTITY
        assert mappings[2][1] == StandardColumnName.UNIT_PRICE
        assert mappings[3][1] == StandardColumnName.AMOUNT

    def test_map_column_names_partial_match(self):
        """Test mapping with abbreviated/partial names."""
        detector = HeaderDetector()
        
        headers = ["Item", "Qty", "Price", "Total"]
        mappings = detector.map_column_names(headers)
        
        assert mappings[0][1] == StandardColumnName.ITEM_NAME
        assert mappings[1][1] == StandardColumnName.QUANTITY
        assert mappings[2][1] == StandardColumnName.UNIT_PRICE

    def test_map_column_names_vietnamese(self):
        """Test mapping Vietnamese headers."""
        detector = HeaderDetector()
        
        headers = ["Hàng", "Số lượng", "Đơn giá", "Thành tiền"]
        mappings = detector.map_column_names(headers)
        
        assert mappings[0][1] == StandardColumnName.ITEM_NAME
        assert mappings[1][1] == StandardColumnName.QUANTITY
        assert mappings[2][1] == StandardColumnName.UNIT_PRICE
        assert mappings[3][1] == StandardColumnName.AMOUNT


# ====== ROW EXTRACTION TESTS ======

class TestRowExtractor:
    """Test row extraction."""

    def test_extract_rows_simple_grid(self):
        """Test extracting rows from simple grid."""
        extractor = RowExtractor(vertical_alignment_threshold=20.0)
        
        ocr_output = [
            ("A1", BoundingBox(10, 10, 30, 30)),
            ("A2", BoundingBox(40, 10, 60, 30)),
            ("B1", BoundingBox(10, 40, 30, 60)),
            ("B2", BoundingBox(40, 40, 60, 60)),
        ]
        columns = [(10, 40), (40, 70)]
        
        rows = extractor.extract_rows(ocr_output, columns)
        
        assert len(rows) == 2  # Two rows
        assert len(rows[0]) == 2  # Two columns in first row

    def test_extract_rows_misaligned(self):
        """Test extracting rows with slight misalignment."""
        extractor = RowExtractor(vertical_alignment_threshold=15.0)
        
        ocr_output = [
            ("A1", BoundingBox(10, 10, 30, 25)),
            ("A2", BoundingBox(40, 12, 60, 28)),  # Slightly misaligned
            ("B1", BoundingBox(10, 40, 30, 55)),
            ("B2", BoundingBox(40, 42, 60, 57)),  # Slightly misaligned
        ]
        columns = [(10, 40), (40, 70)]
        
        rows = extractor.extract_rows(ocr_output, columns)
        assert len(rows) == 2

    def test_extract_rows_no_output(self):
        """Test with empty OCR output."""
        extractor = RowExtractor()
        
        rows = extractor.extract_rows([], [])
        assert len(rows) == 0


# ====== NUMERIC VALIDATION TESTS ======

class TestNumericValidator:
    """Test numeric validation."""

    def test_validate_item_name_text(self):
        """Test validating item name (text field)."""
        is_valid, value, conf = NumericValidator.is_numeric("Product A", StandardColumnName.ITEM_NAME)
        assert is_valid
        assert value is None
        assert conf > 0.8

    def test_validate_quantity_integer(self):
        """Test validating quantity."""
        is_valid, value, conf = NumericValidator.is_numeric("10", StandardColumnName.QUANTITY)
        assert is_valid
        assert value == 10.0
        assert conf > 0.9

    def test_validate_quantity_comma_separated(self):
        """Test validating quantity with comma."""
        is_valid, value, conf = NumericValidator.is_numeric("1,000", StandardColumnName.QUANTITY)
        assert is_valid
        assert value == 1000.0

    def test_validate_unit_price_float(self):
        """Test validating unit price."""
        is_valid, value, conf = NumericValidator.is_numeric("19.99", StandardColumnName.UNIT_PRICE)
        assert is_valid
        assert value == 19.99
        assert conf > 0.9

    def test_validate_unit_price_currency_format(self):
        """Test validating currency with symbol."""
        is_valid, value, conf = NumericValidator.is_numeric("$19.99", StandardColumnName.UNIT_PRICE)
        assert is_valid
        assert value == 19.99

    def test_validate_invalid_numeric(self):
        """Test validation fails for non-numeric."""
        is_valid, value, conf = NumericValidator.is_numeric("ABC", StandardColumnName.QUANTITY)
        assert not is_valid
        assert value is None

    def test_validate_row_valid(self):
        """Test validating complete row."""
        row = {
            StandardColumnName.ITEM_NAME: "Product A",
            StandardColumnName.QUANTITY: "10",
            StandardColumnName.UNIT_PRICE: "19.99",
            StandardColumnName.AMOUNT: "199.90"
        }
        
        schema = {
            StandardColumnName.ITEM_NAME: ColumnType.TEXT,
            StandardColumnName.QUANTITY: ColumnType.NUMERIC,
            StandardColumnName.UNIT_PRICE: ColumnType.FLOAT,
            StandardColumnName.AMOUNT: ColumnType.FLOAT,
        }
        
        is_valid, details = NumericValidator.validate_row(row, schema)
        assert is_valid

    def test_validate_row_invalid(self):
        """Test validating row with invalid values."""
        row = {
            StandardColumnName.ITEM_NAME: "Product A",
            StandardColumnName.QUANTITY: "ABC",  # Invalid
            StandardColumnName.UNIT_PRICE: "19.99",
            StandardColumnName.AMOUNT: "199.90"
        }
        
        schema = {
            StandardColumnName.ITEM_NAME: ColumnType.TEXT,
            StandardColumnName.QUANTITY: ColumnType.NUMERIC,
            StandardColumnName.UNIT_PRICE: ColumnType.FLOAT,
            StandardColumnName.AMOUNT: ColumnType.FLOAT,
        }
        
        is_valid, details = NumericValidator.validate_row(row, schema)
        assert not is_valid
        assert details["invalid_fields"] > 0


# ====== FULL PIPELINE TESTS ======

class TestTableExtractionEngine:
    """Test complete extraction pipeline."""

    def test_extract_simple_invoice_table(self):
        """Test extracting simple invoice table."""
        engine = create_table_extraction_engine()
        
        ocr_output = [
            # Header
            ("Item", BoundingBox(10, 10, 50, 30)),
            ("Qty", BoundingBox(60, 10, 100, 30)),
            ("Price", BoundingBox(110, 10, 150, 30)),
            # Row 1
            ("Product A", BoundingBox(10, 40, 50, 60)),
            ("10", BoundingBox(60, 40, 100, 60)),
            ("50.00", BoundingBox(110, 40, 150, 60)),
            # Row 2
            ("Product B", BoundingBox(10, 70, 50, 90)),
            ("5", BoundingBox(60, 70, 100, 90)),
            ("100.00", BoundingBox(110, 70, 150, 90)),
        ]
        
        tables = engine.extract_tables(ocr_output)
        
        assert len(tables) > 0
        assert tables[0].table_found
        assert len(tables[0].rows) >= 2
        assert tables[0].overall_confidence > 0.7

    def test_extract_no_table(self):
        """Test with data that doesn't form a table."""
        engine = create_table_extraction_engine()
        
        ocr_output = [
            ("Scattered", BoundingBox(10, 10, 50, 30)),
            ("Text", BoundingBox(200, 200, 250, 220)),
        ]
        
        tables = engine.extract_tables(ocr_output)
        
        assert len(tables) == 0 or tables[0].table_found == False

    def test_extract_multiple_tables(self):
        """Test extracting multiple tables from same document."""
        engine = create_table_extraction_engine()
        
        # Table 1: top of page
        table1_rows = [
            ("Item", BoundingBox(10, 10, 50, 30)),
            ("Qty", BoundingBox(60, 10, 100, 30)),
            ("Product A", BoundingBox(10, 40, 50, 60)),
            ("10", BoundingBox(60, 40, 100, 60)),
        ]
        
        # Table 2: bottom of page (separated by 200+ pixels)
        table2_rows = [
            ("Item", BoundingBox(10, 300, 50, 320)),
            ("Qty", BoundingBox(60, 300, 100, 320)),
            ("Product B", BoundingBox(10, 330, 50, 350)),
            ("5", BoundingBox(60, 330, 100, 350)),
        ]
        
        ocr_output = table1_rows + table2_rows
        tables = engine.extract_tables(ocr_output)
        
        # Should detect multiple tables or at least one
        assert len(tables) >= 1

    def test_extraction_confidence_bounds(self):
        """Test that confidence is always 0-1."""
        engine = create_table_extraction_engine()
        
        ocr_output = [
            ("Item", BoundingBox(10, 10, 50, 30)),
            ("Qty", BoundingBox(60, 10, 100, 30)),
            ("Product A", BoundingBox(10, 40, 50, 60)),
            ("10", BoundingBox(60, 40, 100, 60)),
        ]
        
        tables = engine.extract_tables(ocr_output)
        
        if tables and tables[0].table_found:
            assert 0.0 <= tables[0].overall_confidence <= 1.0
            assert 0.0 <= tables[0].table_confidence <= 1.0
            assert 0.0 <= tables[0].header_confidence <= 1.0
            
            for row in tables[0].rows:
                assert 0.0 <= row.row_confidence <= 1.0

    def test_column_mapping_accuracy(self):
        """Test that columns are correctly mapped."""
        engine = create_table_extraction_engine()
        
        ocr_output = [
            ("Item Name", BoundingBox(10, 10, 100, 30)),
            ("Quantity", BoundingBox(110, 10, 160, 30)),
            ("Unit Price", BoundingBox(170, 10, 240, 30)),
            ("Total Amount", BoundingBox(250, 10, 330, 30)),
            ("Product A", BoundingBox(10, 40, 100, 60)),
            ("5", BoundingBox(110, 40, 160, 60)),
            ("20.00", BoundingBox(170, 40, 240, 60)),
            ("100.00", BoundingBox(250, 40, 330, 60)),
        ]
        
        tables = engine.extract_tables(ocr_output)
        
        if tables and tables[0].table_found:
            # Check column mapping
            standard_names = [col.standard_name for col in tables[0].columns]
            assert StandardColumnName.ITEM_NAME in standard_names
            assert StandardColumnName.QUANTITY in standard_names


# ====== EDGE CASE TESTS ======

class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_very_small_font(self):
        """Test with very small bounding boxes."""
        engine = create_table_extraction_engine()
        
        ocr_output = [
            ("I", BoundingBox(10, 10, 12, 12)),
            ("Q", BoundingBox(13, 10, 15, 12)),
            ("P", BoundingBox(10, 13, 12, 15)),
            ("A", BoundingBox(13, 13, 15, 15)),
        ]
        
        tables = engine.extract_tables(ocr_output)
        # Should handle gracefully, not crash
        assert isinstance(tables, list)

    def test_single_column(self):
        """Test with single-column data."""
        engine = create_table_extraction_engine()
        
        ocr_output = [
            ("Items", BoundingBox(10, 10, 50, 30)),
            ("Item 1", BoundingBox(10, 40, 50, 60)),
            ("Item 2", BoundingBox(10, 70, 50, 90)),
        ]
        
        tables = engine.extract_tables(ocr_output)
        # Single column tables might not extract (expected)
        assert isinstance(tables, list)

    def test_heavily_misaligned_rows(self):
        """Test with rows that have significant vertical misalignment."""
        engine = create_table_extraction_engine()
        
        ocr_output = [
            ("Item", BoundingBox(10, 10, 50, 30)),
            ("Qty", BoundingBox(60, 5, 100, 35)),  # Very misaligned
            ("Price", BoundingBox(110, 15, 150, 25)),
            ("Product A", BoundingBox(10, 40, 50, 60)),
            ("10", BoundingBox(60, 35, 100, 65)),
            ("50.00", BoundingBox(110, 45, 150, 55)),
        ]
        
        tables = engine.extract_tables(ocr_output)
        # Should attempt to extract despite misalignment
        assert isinstance(tables, list)

    def test_negative_coordinates(self):
        """Test with negative bounding box coordinates."""
        engine = create_table_extraction_engine()
        
        ocr_output = [
            ("Item", BoundingBox(-50, -50, 0, 0)),
            ("Qty", BoundingBox(10, -50, 60, 0)),
            ("Product", BoundingBox(-50, 10, 0, 60)),
            ("5", BoundingBox(10, 10, 60, 60)),
        ]
        
        tables = engine.extract_tables(ocr_output)
        # Should handle negative coords
        assert isinstance(tables, list)

    def test_overlapping_cells(self):
        """Test with overlapping bounding boxes."""
        engine = create_table_extraction_engine()
        
        ocr_output = [
            ("Item", BoundingBox(10, 10, 60, 30)),
            ("Qty", BoundingBox(40, 10, 100, 30)),  # Overlaps with Item
            ("Product A", BoundingBox(10, 40, 60, 60)),
            ("10", BoundingBox(40, 40, 100, 60)),
        ]
        
        tables = engine.extract_tables(ocr_output)
        # Should handle overlaps
        assert isinstance(tables, list)


# ====== FACTORY FUNCTION TESTS ======

class TestFactoryFunction:
    """Test factory function."""

    def test_create_default_engine(self):
        """Test creating default engine."""
        engine = create_table_extraction_engine()
        assert isinstance(engine, TableExtractionEngine)

    def test_engine_is_reusable(self):
        """Test that engine can process multiple documents."""
        engine = create_table_extraction_engine()
        
        ocr_output_1 = [
            ("Item", BoundingBox(10, 10, 50, 30)),
            ("Q", BoundingBox(60, 10, 100, 30)),
            ("A", BoundingBox(10, 40, 50, 60)),
            ("5", BoundingBox(60, 40, 100, 60)),
        ]
        
        tables_1 = engine.extract_tables(ocr_output_1)
        
        ocr_output_2 = [
            ("Product", BoundingBox(10, 10, 80, 30)),
            ("Price", BoundingBox(90, 10, 150, 30)),
            ("Item B", BoundingBox(10, 40, 80, 60)),
            ("100.00", BoundingBox(90, 40, 150, 60)),
        ]
        
        tables_2 = engine.extract_tables(ocr_output_2)
        
        # Both should work
        assert isinstance(tables_1, list)
        assert isinstance(tables_2, list)


# ====== MULTILINGUAL TESTS ======

class TestMultilingual:
    """Test multilingual support."""

    def test_vietnamese_table(self):
        """Test Vietnamese invoice table."""
        engine = create_table_extraction_engine()
        
        ocr_output = [
            ("Hàng hóa", BoundingBox(10, 10, 80, 30)),
            ("Số lượng", BoundingBox(90, 10, 160, 30)),
            ("Đơn giá", BoundingBox(170, 10, 240, 30)),
            ("Thành tiền", BoundingBox(250, 10, 330, 30)),
            ("Product A", BoundingBox(10, 40, 80, 60)),
            ("5", BoundingBox(90, 40, 160, 60)),
            ("100.000", BoundingBox(170, 40, 240, 60)),
            ("500.000", BoundingBox(250, 40, 330, 60)),
        ]
        
        tables = engine.extract_tables(ocr_output)
        
        if tables and tables[0].table_found:
            # Should detect Vietnamese columns
            standard_names = [col.standard_name for col in tables[0].columns]
            assert StandardColumnName.ITEM_NAME in standard_names

    def test_mixed_language_table(self):
        """Test table with mixed languages."""
        engine = create_table_extraction_engine()
        
        ocr_output = [
            ("Item", BoundingBox(10, 10, 80, 30)),
            ("số lượng", BoundingBox(90, 10, 160, 30)),
            ("Unit Price", BoundingBox(170, 10, 240, 30)),
            ("Thành tiền", BoundingBox(250, 10, 330, 30)),
            ("Product A", BoundingBox(10, 40, 80, 60)),
            ("5", BoundingBox(90, 40, 160, 60)),
            ("100.00", BoundingBox(170, 40, 240, 60)),
            ("500.00", BoundingBox(250, 40, 330, 60)),
        ]
        
        tables = engine.extract_tables(ocr_output)
        assert isinstance(tables, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
