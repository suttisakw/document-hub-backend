"""
TableExtractionEngine: Multi-stage pipeline for extracting structured tables from documents.

Pipeline stages:
1. Table region detection via bbox clustering
2. Header row detection and mapping
3. Column name mapping to standard schema
4. Row extraction based on vertical alignment
5. Numeric validation and confidence scoring
6. Return structured JSON

Vendor-independent design supports any document format.
"""

from dataclasses import dataclass, field
from typing import Protocol, Optional, Dict, List, Tuple, Any, Set
from enum import Enum
from pydantic import BaseModel, Field
import re
from abc import ABC, abstractmethod
from app.services.confidence_service import ConfidenceService
from collections import defaultdict
import statistics


# ====== ENUMS & CONSTANTS ======

class StandardColumnName(str, Enum):
    """Standard column names for table schema."""
    ITEM_NAME = "item_name"
    QUANTITY = "quantity"
    UNIT_PRICE = "unit_price"
    AMOUNT = "amount"
    DESCRIPTION = "description"


class ColumnType(str, Enum):
    """Data type of column."""
    TEXT = "text"
    NUMERIC = "numeric"
    FLOAT = "float"
    INTEGER = "integer"
    OPTIONAL = "optional"


class ExtractionMethod(str, Enum):
    """How cell was extracted."""
    REGEX = "regex"
    CLUSTERING = "clustering"
    ALIGNMENT = "alignment"
    INTERPOLATION = "interpolation"


# ====== DATA CLASSES ======

@dataclass
class BoundingBox:
    """Spatial coordinate information."""
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def width(self) -> float:
        return self.x_max - self.x_min

    def height(self) -> float:
        return self.y_max - self.y_min

    def center_x(self) -> float:
        return (self.x_min + self.x_max) / 2

    def center_y(self) -> float:
        return (self.y_min + self.y_max) / 2

    def overlaps_x(self, other: 'BoundingBox', threshold: float = 0.5) -> bool:
        """Check if boxes overlap in x-axis significantly."""
        overlap_start = max(self.x_min, other.x_min)
        overlap_end = min(self.x_max, other.x_max)
        overlap = max(0, overlap_end - overlap_start)
        min_width = min(self.width(), other.width())
        return overlap > min_width * threshold if min_width > 0 else False

    def overlaps_y(self, other: 'BoundingBox', threshold: float = 0.5) -> bool:
        """Check if boxes overlap in y-axis significantly."""
        overlap_start = max(self.y_min, other.y_min)
        overlap_end = min(self.y_max, other.y_max)
        overlap = max(0, overlap_end - overlap_start)
        min_height = min(self.height(), other.height())
        return overlap > min_height * threshold if min_height > 0 else False


@dataclass
class TableCell:
    """Single table cell."""
    row_idx: int
    col_idx: int
    value: str
    confidence: float
    bbox: Optional[BoundingBox] = None
    method: ExtractionMethod = ExtractionMethod.REGEX
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TableColumn:
    """Column metadata."""
    col_idx: int
    standard_name: StandardColumnName
    detected_name: str  # Name from header row
    column_type: ColumnType
    x_range: Tuple[float, float]  # x_min, x_max for alignment
    cells: List[TableCell] = field(default_factory=list)
    confidence: float = field(default=0.9)


@dataclass
class TableRow:
    """Complete row with cells and confidence."""
    row_idx: int
    cells: Dict[StandardColumnName, TableCell]
    row_confidence: float
    bbox: Optional[BoundingBox] = None
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TableExtractionOutput:
    """Complete table extraction result."""
    table_found: bool
    table_region: Optional[BoundingBox]
    columns: List[TableColumn]
    rows: List[TableRow]
    overall_confidence: float
    table_confidence: float
    header_confidence: float
    row_confidences: List[float] = field(default_factory=list)
    processing_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ====== BBOX CLUSTERING ======

class BboxClusterer:
    """Detect table regions using bbox clustering."""

    def __init__(self, distance_threshold: float = 50.0):
        """
        Initialize bbox clusterer.
        
        Args:
            distance_threshold: Maximum distance between boxes to be in same cluster
        """
        self.distance_threshold = distance_threshold

    def cluster_bboxes(self, bboxes: List[Tuple[str, BoundingBox]]) -> List[List[Tuple[str, BoundingBox]]]:
        """
        Cluster bboxes into groups (potential tables).
        
        Args:
            bboxes: List of (text, bbox) tuples from OCR
            
        Returns:
            List of clusters, each containing grouped boxes
        """
        if not bboxes:
            return []

        clusters = []
        used = set()

        for i, (text_i, bbox_i) in enumerate(bboxes):
            if i in used:
                continue

            current_cluster = [(text_i, bbox_i)]
            used.add(i)

            # Find boxes close to this one
            for j in range(i + 1, len(bboxes)):
                if j in used:
                    continue

                text_j, bbox_j = bboxes[j]
                
                # Check if close to any box in cluster
                for text_k, bbox_k in current_cluster:
                    if self._boxes_nearby(bbox_j, bbox_k):
                        current_cluster.append((text_j, bbox_j))
                        used.add(j)
                        break

            clusters.append(current_cluster)

        return clusters

    def _boxes_nearby(self, bbox1: BoundingBox, bbox2: BoundingBox) -> bool:
        """Check if two boxes are nearby."""
        # Horizontal distance
        h_dist = min(
            abs(bbox1.x_min - bbox2.x_max),
            abs(bbox2.x_min - bbox1.x_max),
            abs(bbox1.center_x() - bbox2.center_x())
        )

        # Vertical distance
        v_dist = min(
            abs(bbox1.y_min - bbox2.y_max),
            abs(bbox2.y_min - bbox1.y_max),
            abs(bbox1.center_y() - bbox2.center_y())
        )

        # Both should be close
        return h_dist < self.distance_threshold and v_dist < self.distance_threshold

    def detect_table_region(self, cluster: List[Tuple[str, BoundingBox]]) -> Optional[BoundingBox]:
        """
        Detect table region from cluster of boxes.
        
        Args:
            cluster: List of (text, bbox) tuples
            
        Returns:
            BoundingBox encompassing table, or None if not a table
        """
        if not cluster or len(cluster) < 4:  # Tables need min 4 cells
            return None

        # Find bounds of cluster
        x_coords = []
        y_coords = []

        for text, bbox in cluster:
            x_coords.extend([bbox.x_min, bbox.x_max])
            y_coords.extend([bbox.y_min, bbox.y_max])

        if not x_coords or not y_coords:
            return None

        region = BoundingBox(
            x_min=min(x_coords),
            y_min=min(y_coords),
            x_max=max(x_coords),
            y_max=max(y_coords)
        )

        return region


# ====== HEADER DETECTION ======

class HeaderDetector:
    """Detect header row using heuristics."""

    def __init__(self):
        """Initialize header detector."""
        self.header_indicators = [
            "item", "description", "qty", "quantity", "price", "unit",
            "amount", "total", "name", "product", "code", "sku",
            "qty", "qta", "số lượng", "đơn giá", "thành tiền"  # Include Vietnamese
        ]

    def detect_header_row(
        self,
        sorted_cells: List[Tuple[str, BoundingBox, int]],  # (text, bbox, row_idx)
        num_rows: int
    ) -> Tuple[int, float]:
        """
        Detect header row index.
        
        Args:
            sorted_cells: Cells sorted by position
            num_rows: Total number of rows
            
        Returns:
            (header_row_index, confidence)
        """
        if not sorted_cells or num_rows < 2:
            return 0, 0.5

        # Group cells by row (y-coordinate)
        row_groups = defaultdict(list)
        for text, bbox, row_idx in sorted_cells:
            row_groups[row_idx].append((text.lower(), bbox))

        best_header_row = 0
        best_score = 0.0

        # Check each row as potential header
        for row_idx in sorted(row_groups.keys())[:3]:  # Check top 3 rows
            row_cells = row_groups[row_idx]
            
            # Score based on header indicators
            indicator_count = sum(
                1 for text, _ in row_cells
                if any(indicator in text for indicator in self.header_indicators)
            )

            # Position score (headers usually at top)
            position_score = 1.0 - (row_idx / (num_rows + 1))

            # Text length consistency (headers are usually short)
            lengths = [len(text) for text, _ in row_cells]
            if lengths:
                avg_length = sum(lengths) / len(lengths)
                length_score = 1.0 if 5 <= avg_length <= 30 else 0.6
            else:
                length_score = 0.5

            # Combined score
            score = (
                (indicator_count / len(row_cells) if row_cells else 0) * 0.5 +
                position_score * 0.3 +
                length_score * 0.2
            )

            if score > best_score:
                best_score = score
                best_header_row = row_idx

        return best_header_row, min(1.0, best_score * 1.2)

    def map_column_names(self, header_texts: List[str]) -> List[Tuple[str, StandardColumnName, float]]:
        """
        Map detected header names to standard schema.
        
        Args:
            header_texts: Header text from each column
            
        Returns:
            List of (detected_name, standard_name, confidence)
        """
        mappings = []

        for text in header_texts:
            lower_text = text.lower().strip()
            confidence = 0.0
            standard_name = StandardColumnName.DESCRIPTION

            # Match against patterns
            if any(w in lower_text for w in ["item", "name", "product", "product name", "hàng", "sản phẩm"]):
                standard_name = StandardColumnName.ITEM_NAME
                confidence = 0.95
            elif any(w in lower_text for w in ["quantity", "qty", "qta", "số lượng", "sl"]):
                standard_name = StandardColumnName.QUANTITY
                confidence = 0.95
            elif any(w in lower_text for w in ["price", "unit price", "unit cost", "đơn giá", "giá"]):
                standard_name = StandardColumnName.UNIT_PRICE
                confidence = 0.95
            elif any(w in lower_text for w in ["amount", "total", "sum", "thành tiền", "cộng"]):
                standard_name = StandardColumnName.AMOUNT
                confidence = 0.95
            elif any(w in lower_text for w in ["description", "desc", "notes", "ghi chú"]):
                standard_name = StandardColumnName.DESCRIPTION
                confidence = 0.90
            else:
                # Default to description for unknown
                confidence = 0.6

            mappings.append((text, standard_name, confidence))

        return mappings


# ====== ROW EXTRACTION ======

class RowExtractor:
    """Extract rows based on vertical alignment."""

    def __init__(self, vertical_alignment_threshold: float = 10.0):
        """
        Initialize row extractor.
        
        Args:
            vertical_alignment_threshold: Max difference in y-center for same row
        """
        self.vertical_threshold = vertical_alignment_threshold

    def extract_rows(
        self,
        ocr_output: List[Tuple[str, BoundingBox]],
        columns: List[Tuple[float, float]]  # List of (x_min, x_max) for each column
    ) -> Dict[int, Dict[int, Tuple[str, BoundingBox]]]:
        """
        Extract rows by grouping cells vertically.
        
        Args:
            ocr_output: List of (text, bbox) from OCR
            columns: List of column x-ranges
            
        Returns:
            Dict[row_idx][col_idx] = (text, bbox)
        """
        if not ocr_output:
            return {}

        # Group cells by vertical position
        rows = defaultdict(lambda: defaultdict(list))

        for text, bbox in ocr_output:
            # Find which row based on y-center
            row_group = self._find_row_group(bbox, rows)
            
            # Find which column based on x-range
            col_idx = self._find_column(bbox, columns)
            
            rows[row_group][col_idx].append((text, bbox))

        # Consolidate multiple cells in same row/col
        consolidated = defaultdict(dict)
        for row_idx, cols in rows.items():
            for col_idx, cells in cols.items():
                # Take longest text (most likely correct)
                best_cell = max(cells, key=lambda x: len(x[0]))
                consolidated[row_idx][col_idx] = best_cell

        return consolidated

    def _find_row_group(self, bbox: BoundingBox, existing_rows: Dict) -> int:
        """Find which row group this bbox belongs to."""
        y_center = bbox.center_y()

        for row_idx in existing_rows.keys():
            # Get average y_center of row
            cells = [bb for col_cells in existing_rows[row_idx].values() for _, bb in col_cells]
            if cells:
                avg_y = sum(bb.center_y() for bb in cells) / len(cells)
                if abs(y_center - avg_y) < self.vertical_threshold:
                    return row_idx

        # New row
        return max(existing_rows.keys()) + 1 if existing_rows else 0

    def _find_column(self, bbox: BoundingBox, columns: List[Tuple[float, float]]) -> int:
        """Find which column this bbox belongs to."""
        x_center = bbox.center_x()

        for col_idx, (x_min, x_max) in enumerate(columns):
            if x_min <= x_center <= x_max:
                return col_idx

        # Closest column
        min_distance = float('inf')
        closest_col = 0
        for col_idx, (x_min, x_max) in enumerate(columns):
            col_center = (x_min + x_max) / 2
            distance = abs(x_center - col_center)
            if distance < min_distance:
                min_distance = distance
                closest_col = col_idx

        return closest_col


# ====== NUMERIC VALIDATION ======

class NumericValidator:
    """Validate and extract numeric values."""

    @staticmethod
    def is_numeric(text: str, field_type: StandardColumnName) -> Tuple[bool, Optional[float], float]:
        """
        Check if text is numeric for field type.
        
        Args:
            text: Text to validate
            field_type: Expected field type
            
        Returns:
            (is_valid, numeric_value, confidence)
        """
        text = text.strip()

        if field_type == StandardColumnName.ITEM_NAME:
            return True, None, 0.9  # Always valid for text

        if field_type == StandardColumnName.DESCRIPTION:
            return True, None, 0.9  # Always valid for text

        # For numeric fields
        if field_type in [StandardColumnName.QUANTITY, StandardColumnName.UNIT_PRICE, StandardColumnName.AMOUNT]:
            # Try to extract number
            match = re.search(r'[\d.,]+', text)
            if match:
                num_str = match.group(0).replace(',', '.')
                try:
                    value = float(num_str)
                    return True, value, 0.95
                except ValueError:
                    return False, None, 0.1

            return False, None, 0.1

        return True, None, 0.9

    @staticmethod
    def validate_row(
        row_cells: Dict[StandardColumnName, str],
        schema: Dict[StandardColumnName, ColumnType]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate entire row.
        
        Args:
            row_cells: Dict of standard_name -> text
            schema: Column types
            
        Returns:
            (is_valid, validation_details)
        """
        details = {"valid_fields": 0, "invalid_fields": 0, "errors": []}

        for col_name, cell_text in row_cells.items():
            col_type = schema.get(col_name, ColumnType.TEXT)
            is_valid, _, conf = NumericValidator.is_numeric(cell_text, col_name)

            if is_valid:
                details["valid_fields"] += 1
            else:
                details["invalid_fields"] += 1
                details["errors"].append(f"{col_name}: '{cell_text}' is not numeric")

        return details["invalid_fields"] == 0, details


# ====== MAIN TABLE EXTRACTION ENGINE ======

class TableExtractionEngine:
    """
    Main orchestrator for table extraction.
    
    Pipeline:
    1. Detect table region via bbox clustering
    2. Detect header row with column mapping
    3. Extract rows based on vertical alignment
    4. Validate numeric columns
    5. Compute confidence scores
    6. Return structured JSON
    """

    def __init__(
        self,
        clusterer: Optional[BboxClusterer] = None,
        header_detector: Optional[HeaderDetector] = None,
        row_extractor: Optional[RowExtractor] = None,
        validator: Optional[NumericValidator] = None,
        min_table_cells: int = 4,
        min_rows: int = 2,
    ):
        """
        Initialize table extraction engine.
        
        Args:
            clusterer: BoundingBox clusterer
            header_detector: Header row detector
            row_extractor: Row extraction engine
            validator: Numeric validator
            min_table_cells: Minimum cells for valid table
            min_rows: Minimum rows (including header)
        """
        self.clusterer = clusterer or BboxClusterer()
        self.header_detector = header_detector or HeaderDetector()
        self.row_extractor = row_extractor or RowExtractor()
        self.validator = validator or NumericValidator()
        self.min_table_cells = min_table_cells
        self.min_rows = min_rows

        # Standard schema
        self.standard_schema = {
            StandardColumnName.ITEM_NAME: ColumnType.TEXT,
            StandardColumnName.QUANTITY: ColumnType.NUMERIC,
            StandardColumnName.UNIT_PRICE: ColumnType.FLOAT,
            StandardColumnName.AMOUNT: ColumnType.FLOAT,
            StandardColumnName.DESCRIPTION: ColumnType.OPTIONAL,
        }

    def extract_tables(
        self,
        ocr_output: List[Tuple[str, BoundingBox]],
        page_height: float = 1000.0,
        page_width: float = 1000.0,
    ) -> List[TableExtractionOutput]:
        """
        Extract all tables from OCR output.
        
        Args:
            ocr_output: List of (text, bbox) tuples from OCR
            page_height: Page height for context
            page_width: Page width for context
            
        Returns:
            List of extracted tables
        """
        import time
        start_time = time.time()

        # Step 1: Cluster bboxes to find table regions
        clusters = self.clusterer.cluster_bboxes(ocr_output)

        tables = []
        for cluster in clusters:
            # Try to extract table from this cluster
            table_output = self._extract_single_table(cluster)
            if table_output.table_found:
                tables.append(table_output)

        # Set processing time
        processing_time = (time.time() - start_time) * 1000
        for table in tables:
            table.processing_time_ms = processing_time

        return tables

    def _extract_single_table(self, cluster: List[Tuple[str, BoundingBox]]) -> TableExtractionOutput:
        """
        Extract single table from cluster with robust error recovery.
        
        Args:
            cluster: List of (text, bbox) tuples
            
        Returns:
            TableExtractionOutput
        """
        # Initialize default response
        default_output = TableExtractionOutput(
            table_found=False,
            table_region=None,
            columns=[],
            rows=[],
            overall_confidence=0.0,
            table_confidence=0.0,
            header_confidence=0.0,
            metadata={"errors": []}
        )

        try:
            # Step 1: Detect table region
            table_region = self.clusterer.detect_table_region(cluster)
            if table_region is None:
                return default_output
            
            default_output.table_region = table_region
        except Exception as e:
            default_output.metadata["errors"].append(f"Region detection failed: {str(e)}")
            return default_output

        try:
            # Filter cluster to table region
            filtered_cluster = [
                (text, bbox) for text, bbox in cluster
                if self._bbox_in_region(bbox, table_region)
            ]

            if len(filtered_cluster) < self.min_table_cells:
                default_output.metadata["errors"].append("Cluster filtered to too few cells")
                return default_output
        except Exception as e:
            default_output.metadata["errors"].append(f"Cluster filtering failed: {str(e)}")
            return default_output

        try:
            # Step 2: Detect header row
            sorted_cells = self._sort_cells(filtered_cluster)
            num_rows = len(set(int(bbox.center_y() / 20) for _, bbox in filtered_cluster))  # Approximate rows

            header_row_idx, header_confidence = self.header_detector.detect_header_row(
                [(text, bbox, int(bbox.center_y() / 20)) for text, bbox in sorted_cells],
                num_rows
            )

            # Extract header texts
            header_cells = [
                (text, bbox) for text, bbox in filtered_cluster
                if int(bbox.center_y() / 20) == header_row_idx
            ]
            header_texts = [text for text, _ in sorted(header_cells, key=lambda x: x[1].center_x())]

            if not header_texts:
                default_output.metadata["errors"].append("No header texts detected")
                return default_output
        except Exception as e:
            default_output.metadata["errors"].append(f"Header detection failed: {str(e)}")
            return default_output

        try:
            # Step 3: Map column names
            column_mappings = self.header_detector.map_column_names(header_texts)
        except Exception as e:
            default_output.metadata["errors"].append(f"Column mapping failed: {str(e)}")
            return default_output

        try:
            # Step 4: Extract rows
            # Get column x-ranges from header
            header_x_ranges = [bbox.x_min for _, bbox in sorted(header_cells, key=lambda x: x[1].center_x())]
            if len(header_x_ranges) > 0:
                x_ranges = [(header_x_ranges[i], header_x_ranges[i+1] if i+1 < len(header_x_ranges) else table_region.x_max)
                            for i in range(len(header_x_ranges))]
            else:
                x_ranges = [(table_region.x_min, table_region.x_max)]

            extracted_rows_dict = self.row_extractor.extract_rows(filtered_cluster, x_ranges)
        except Exception as e:
            default_output.metadata["errors"].append(f"Row extraction failed: {str(e)}")
            return default_output

        try:
            # Step 5: Build output structure
            columns = []
            for col_idx, (detected_name, standard_name, name_confidence) in enumerate(column_mappings):
                if col_idx < len(x_ranges):
                    col = TableColumn(
                        col_idx=col_idx,
                        standard_name=standard_name,
                        detected_name=detected_name,
                        column_type=self.standard_schema.get(standard_name, ColumnType.TEXT),
                        x_range=x_ranges[col_idx],
                        confidence=name_confidence
                    )
                    columns.append(col)

            # Build rows
            rows = []
            row_confidences = []

            for row_idx in sorted(extracted_rows_dict.keys()):
                if row_idx == header_row_idx:
                    continue  # Skip header row in output

                row_cells_dict = extracted_rows_dict[row_idx]
                row_cells = {}
                cell_confidences = []

                for col_idx, col in enumerate(columns):
                    if col_idx in row_cells_dict:
                        text, bbox = row_cells_dict[col_idx]
                        try:
                            is_valid, num_value, confidence = self.validator.is_numeric(text, col.standard_name)
                        except Exception:
                            # Default if validator fails
                            is_valid, num_value, confidence = True, None, 0.5
                            
                        cell = TableCell(
                            row_idx=row_idx,
                            col_idx=col_idx,
                            value=text,
                            confidence=confidence,
                            bbox=bbox,
                            method=ExtractionMethod.ALIGNMENT
                        )
                        row_cells[col.standard_name] = cell
                        cell_confidences.append(confidence)

                if not row_cells:
                    continue

                # Calculate row confidence
                row_confidence = ConfidenceService.calculate_table_score(cell_confidences)

                # Validate row
                try:
                    is_valid, validation_details = self.validator.validate_row(
                        {col_name: cell.value for col_name, cell in row_cells.items()},
                        self.standard_schema
                    )
                except Exception as e:
                    validation_details = {"errors": [f"Row validation failed: {str(e)}"]}

                row = TableRow(
                    row_idx=row_idx,
                    cells=row_cells,
                    row_confidence=row_confidence,
                    bbox=self._compute_row_bbox(row_cells_dict),
                    evidence=validation_details
                )
                rows.append(row)
                row_confidences.append(row_confidence)

            # Compute overall confidence
            overall_confidence = ConfidenceService.aggregate_document_confidence(row_confidences)

            return TableExtractionOutput(
                table_found=True,
                table_region=table_region,
                columns=columns,
                rows=rows,
                overall_confidence=overall_confidence,
                table_confidence=min(1.0, len(rows) / 10),  # Confidence based on row count
                header_confidence=header_confidence,
                row_confidences=row_confidences,
                metadata={
                    "num_rows": len(rows),
                    "num_columns": len(columns),
                    "num_cells": len(rows) * len(columns),
                    "errors": default_output.metadata.get("errors", [])
                }
            )
        except Exception as e:
            default_output.metadata["errors"].append(f"Result building failed: {str(e)}")
            return default_output

    def _bbox_in_region(self, bbox: BoundingBox, region: BoundingBox) -> bool:
        """Check if bbox is within region."""
        return (
            bbox.x_min >= region.x_min and bbox.x_max <= region.x_max and
            bbox.y_min >= region.y_min and bbox.y_max <= region.y_max
        )

    def _sort_cells(self, cluster: List[Tuple[str, BoundingBox]]) -> List[Tuple[str, BoundingBox]]:
        """Sort cells by position (top-left to bottom-right)."""
        return sorted(cluster, key=lambda x: (x[1].center_y(), x[1].center_x()))

    def _compute_row_bbox(self, row_cells: Dict) -> Optional[BoundingBox]:
        """Compute bounding box for row."""
        if not row_cells:
            return None

        bboxes = [bbox for _, bbox in row_cells.values()]
        if not bboxes:
            return None

        return BoundingBox(
            x_min=min(bb.x_min for bb in bboxes),
            y_min=min(bb.y_min for bb in bboxes),
            x_max=max(bb.x_max for bb in bboxes),
            y_max=max(bb.y_max for bb in bboxes)
        )


# ====== FACTORY FUNCTION ======

def create_table_extraction_engine() -> TableExtractionEngine:
    """Factory function to create configured TableExtractionEngine."""
    return TableExtractionEngine(
        clusterer=BboxClusterer(distance_threshold=50.0),
        header_detector=HeaderDetector(),
        row_extractor=RowExtractor(vertical_alignment_threshold=10.0),
        validator=NumericValidator(),
        min_table_cells=4,
        min_rows=2,
    )


# ====== SERIALIZATION ======

def table_extraction_output_to_json(output: TableExtractionOutput) -> Dict[str, Any]:
    """Convert extraction output to JSON-serializable dict."""
    if not output.table_found:
        return {
            "table_found": False,
            "error": "No table detected"
        }

    rows_json = []
    for row in output.rows:
        row_data = {
            "row_index": row.row_idx,
            "confidence": row.row_confidence,
            "cells": {}
        }

        for col_name, cell in row.cells.items():
            row_data["cells"][col_name.value] = {
                "value": cell.value,
                "confidence": cell.confidence,
                "method": cell.method.value
            }

        rows_json.append(row_data)

    return {
        "table_found": True,
        "table_region": {
            "x_min": output.table_region.x_min,
            "y_min": output.table_region.y_min,
            "x_max": output.table_region.x_max,
            "y_max": output.table_region.y_max,
        } if output.table_region else None,
        "columns": [
            {
                "index": col.col_idx,
                "detected_name": col.detected_name,
                "standard_name": col.standard_name.value,
                "type": col.column_type.value,
                "confidence": col.confidence
            }
            for col in output.columns
        ],
        "rows": rows_json,
        "overall_confidence": output.overall_confidence,
        "table_confidence": output.table_confidence,
        "header_confidence": output.header_confidence,
        "metadata": output.metadata,
        "processing_time_ms": output.processing_time_ms
    }
