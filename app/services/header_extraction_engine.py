"""
HeaderExtractionEngine: Multi-stage pipeline for extracting invoice headers.

Pipeline stages:
1. Template-based extraction (fastest, most reliable)
2. Regex anchor extraction (flexible, rule-based)
3. ML-based extraction fallback (adaptive learning)
4. LLM-based extraction (highest confidence, fallback only)

Architecture is modular and pluggable - each stage can be replaced or skipped.
"""

from dataclasses import dataclass, field
from typing import Protocol, Optional, Dict, List, Tuple, Any, Callable
from enum import Enum
from pydantic import BaseModel, Field
import re
from abc import ABC, abstractmethod
import json
from app.schemas.confidence import ConfidenceScore, ExtractedSource, ExtractionStage
from app.services.confidence_service import ConfidenceService


# ====== ENUMS & CONSTANTS ======

from app.core.enums import InvoiceFieldType


# Aliased from confidence.py
ExtractionSource = ExtractedSource
ExtractionStage = ExtractionStage


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


@dataclass
class ExtractionResult:
    """Extraction result for a single field."""
    field_type: InvoiceFieldType
    value: Optional[str]
    confidence: float  # 0.0-1.0
    source: ExtractionSource
    stage: ExtractionStage
    bbox: Optional[BoundingBox] = None
    raw_text: Optional[str] = None  # Full context from OCR
    evidence: Dict[str, Any] = field(default_factory=dict)  # Scoring details
    confidence_details: Optional[ConfidenceScore] = None

    def __post_init__(self):
        """Validate confidence range and initialize details."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")
        
        if self.confidence_details is None:
            self.confidence_details = ConfidenceScore(
                value=self.confidence,
                source=self.source,
                stage=self.stage,
                evidence=self.evidence,
                history=[self.confidence]
            )


@dataclass
class HeaderExtractionOutput:
    """Complete extraction output for invoice header."""
    fields: Dict[InvoiceFieldType, ExtractionResult]
    overall_confidence: float
    extracted_at_stage: ExtractionStage
    processing_time_ms: float
    all_results: List[ExtractionResult] = field(default_factory=list)  # All stages

    def get_field(self, field_type: InvoiceFieldType) -> Optional[ExtractionResult]:
        """Get extraction result for specific field."""
        return self.fields.get(field_type)

    def get_high_confidence_fields(self, threshold: float = 0.7) -> Dict[InvoiceFieldType, ExtractionResult]:
        """Get fields above confidence threshold."""
        return {
            ft: result for ft, result in self.fields.items()
            if result.confidence >= threshold and result.value is not None
        }


# ====== PROTOCOLS (FOR PLUGGABILITY) ======

class ExtractorStrategy(Protocol):
    """Protocol for extraction strategy implementations."""

    def extract(self, ocr_lines: List[str], field_types: List[InvoiceFieldType]) -> List[ExtractionResult]:
        """Extract fields from OCR lines."""
        ...

    def supports_field(self, field_type: InvoiceFieldType) -> bool:
        """Check if this extractor supports field type."""
        ...


# ====== TEMPLATE EXTRACTION ======

class TemplateExtractor:
    """
    Stage 1: Template-based extraction.
    Uses predefined patterns that match specific template layouts.
    Fastest and most reliable for structured documents.
    """

    def __init__(self, confidence_base: float = 0.95):
        """
        Initialize template extractor.
        
        Args:
            confidence_base: Base confidence for template matches
        """
        self.confidence_base = confidence_base
        self.templates = self._build_templates()

    def _build_templates(self) -> Dict[InvoiceFieldType, List[Dict[str, Any]]]:
        """
        Build template patterns for invoice fields.
        Each template defines positions, labels, and extraction logic.
        """
        return {
            InvoiceFieldType.INVOICE_NUMBER: [
                {
                    "pattern": r"(?:invoice\s+(?:number|no\.?|#|number:))\s*[:\s]*([A-Z0-9\-/]+)",
                    "label_indicators": ["invoice", "inv", "number", "no", "#"],
                    "line_proximity": 3,
                    "normalized": True,
                },
            ],
            InvoiceFieldType.INVOICE_DATE: [
                {
                    "pattern": r"(?:invoice\s+date|date|dated|issued)\s*[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                    "label_indicators": ["date", "issued", "dated"],
                    "line_proximity": 3,
                    "normalized": False,
                },
            ],
            InvoiceFieldType.VENDOR_NAME: [
                {
                    "pattern": r"(?:from|vendor|supplier|company|by)\s*[:\s]*([A-Za-z0-9\s&.,'-]+?)(?:\n|$)",
                    "label_indicators": ["from", "vendor", "supplier"],
                    "line_proximity": 5,
                    "normalized": False,
                },
            ],
            InvoiceFieldType.TAX_ID: [
                {
                    "pattern": r"(?:tax\s+id|tax\s+no|vat\s+no|ein|itin|tnid|afm|siret)\s*[:\s]*([A-Z0-9\-/]+)",
                    "label_indicators": ["tax", "id", "vat", "ein", "tin"],
                    "line_proximity": 4,
                    "normalized": True,
                },
            ],
            InvoiceFieldType.SUBTOTAL: [
                {
                    "pattern": r"(?:subtotal|sub[\s-]?total|net|net\s+amount)\s*[:\s]*([0-9,.\s]+)",
                    "label_indicators": ["subtotal", "sub"],
                    "line_proximity": 2,
                    "normalized": True,
                },
            ],
            InvoiceFieldType.VAT: [
                {
                    "pattern": r"(?:vat|tax|sales\s+tax|gst|tva)\s*(?:\(.*?\)|[0-9]*%?)?\s*[:\s]*([0-9,.\s]+)",
                    "label_indicators": ["vat", "tax"],
                    "line_proximity": 2,
                    "normalized": True,
                },
            ],
            InvoiceFieldType.TOTAL_AMOUNT: [
                {
                    "pattern": r"(?:total|grand\s+total|total\s+amount|amount\s+due)\s*[:\s]*([0-9,.\s]+)",
                    "label_indicators": ["total", "grand"],
                    "line_proximity": 2,
                    "normalized": True,
                },
            ],
        }

    def extract(self, ocr_lines: List[str], field_types: List[InvoiceFieldType]) -> List[ExtractionResult]:
        """
        Extract fields using templates.
        
        Args:
            ocr_lines: List of OCR text lines
            field_types: Fields to extract
            
        Returns:
            List of ExtractionResult objects
        """
        results = []
        combined_text = "\n".join(ocr_lines)

        for field_type in field_types:
            if field_type not in self.templates:
                continue

            best_result = None
            best_confidence = 0.0

            for template in self.templates[field_type]:
                try:
                    # Try to match pattern
                    match = re.search(
                        template["pattern"],
                        combined_text,
                        re.IGNORECASE | re.MULTILINE
                    )

                    if match:
                        value = match.group(1).strip()
                        
                        # Normalize if required
                        if template.get("normalized"):
                            value = self._normalize_value(value, field_type)

                        # Calculate confidence
                        confidence = self._calculate_match_confidence(
                            value, field_type, template, len(ocr_lines)
                        )

                        if confidence > best_confidence:
                            best_confidence = confidence
                            best_result = ExtractionResult(
                                field_type=field_type,
                                value=value,
                                confidence=confidence,
                                source=ExtractionSource.TEMPLATE,
                                stage=ExtractionStage.TEMPLATE,
                                bbox=None,  # Templates don't provide bbox
                                raw_text=match.group(0),
                                evidence={
                                    "pattern": template["pattern"],
                                    "match_position": match.start(),
                                    "template_confidence": self.confidence_base
                                }
                            )
                except Exception:
                    continue

            if best_result:
                results.append(best_result)

        return results

    def _normalize_value(self, value: str, field_type: InvoiceFieldType) -> str:
        """Normalize extracted value based on field type."""
        value = value.strip()

        if field_type in [InvoiceFieldType.SUBTOTAL, InvoiceFieldType.VAT, InvoiceFieldType.TOTAL_AMOUNT]:
            # Remove currency symbols and extra spaces
            value = re.sub(r'[^\d.,\s]', '', value)
            value = value.replace(',', '.').split('.')[0] + '.' + (value.split('.')[-1] if '.' in value else '00')

        elif field_type == InvoiceFieldType.INVOICE_NUMBER:
            value = value.upper()

        return value

    def _calculate_match_confidence(
        self, value: str, field_type: InvoiceFieldType, template: Dict[str, Any], num_lines: int
    ) -> float:
        """Calculate confidence based on match quality using central service."""
        return ConfidenceService.calculate_header_score(
            base_value=self.confidence_base,
            value_text=value,
            completeness=1.0 # Standard template match is complete
        )

    def supports_field(self, field_type: InvoiceFieldType) -> bool:
        """Check if field is supported by template extractor."""
        return field_type in self.templates


# ====== REGEX ANCHOR EXTRACTION ======

class RegexAnchorExtractor:
    """
    Stage 2: Regex anchor-based extraction.
    Uses flexible regex patterns to find values near anchor keywords.
    More flexible than templates, handles variations in layout.
    """

    def __init__(self, proximity_window: int = 3):
        """
        Initialize regex anchor extractor.
        
        Args:
            proximity_window: Lines around anchor to search for value
        """
        self.proximity_window = proximity_window
        self.anchors = self._build_anchors()

    def _build_anchors(self) -> Dict[InvoiceFieldType, Dict[str, Any]]:
        """Build anchor patterns for field extraction."""
        return {
            InvoiceFieldType.INVOICE_NUMBER: {
                "anchors": ["invoice", "inv", "number", "no:", "no.", "#"],
                "value_pattern": r"([A-Z0-9\-/]+)",
                "order": "after",
            },
            InvoiceFieldType.INVOICE_DATE: {
                "anchors": ["date:", "dated:", "issued:", "date"],
                "value_pattern": r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                "order": "after",
            },
            InvoiceFieldType.VENDOR_NAME: {
                "anchors": ["from:", "vendor:", "supplier:", "company:"],
                "value_pattern": r"([A-Za-z0-9\s&.,'-]+)",
                "order": "after",
            },
            InvoiceFieldType.TAX_ID: {
                "anchors": ["tax id", "vat no", "tin", "ein"],
                "value_pattern": r"([A-Z0-9\-/.]+)",
                "order": "after",
            },
            InvoiceFieldType.SUBTOTAL: {
                "anchors": ["subtotal", "sub-total", "net"],
                "value_pattern": r"([0-9,.\s]+)",
                "order": "after",
            },
            InvoiceFieldType.VAT: {
                "anchors": ["vat", "tax", "gst"],
                "value_pattern": r"([0-9,.\s]+)",
                "order": "after",
            },
            InvoiceFieldType.TOTAL_AMOUNT: {
                "anchors": ["total", "grand total", "amount due"],
                "value_pattern": r"([0-9,.\s]+)",
                "order": "after",
            },
        }

    def extract(self, ocr_lines: List[str], field_types: List[InvoiceFieldType]) -> List[ExtractionResult]:
        """
        Extract fields using regex anchors.
        
        Args:
            ocr_lines: List of OCR text lines
            field_types: Fields to extract
            
        Returns:
            List of ExtractionResult objects
        """
        results = []

        for field_type in field_types:
            if field_type not in self.anchors:
                continue

            anchor_config = self.anchors[field_type]
            best_result = None
            best_confidence = 0.0

            # Search through OCR lines
            for line_idx, line in enumerate(ocr_lines):
                lower_line = line.lower()

                # Check if anchor appears in this line
                for anchor in anchor_config["anchors"]:
                    if anchor.lower() in lower_line:
                        # Extract value from current and nearby lines
                        extraction = self._extract_value_at_anchor(
                            ocr_lines, line_idx, anchor, anchor_config, field_type
                        )

                        if extraction and extraction.confidence > best_confidence:
                            best_confidence = extraction.confidence
                            best_result = extraction

            if best_result:
                results.append(best_result)

        return results

    def _extract_value_at_anchor(
        self,
        ocr_lines: List[str],
        anchor_line_idx: int,
        anchor: str,
        config: Dict[str, Any],
        field_type: InvoiceFieldType
    ) -> Optional[ExtractionResult]:
        """Extract value near an anchor keyword."""
        value = None
        match_pos = None
        regex_score = 0.0

        # Try to find value in anchor line first
        anchor_line = ocr_lines[anchor_line_idx]
        anchor_pos = anchor_line.lower().find(anchor.lower())

        if anchor_pos >= 0:
            # Search after anchor
            search_text = anchor_line[anchor_pos + len(anchor):]
            match = re.search(config["value_pattern"], search_text)

            if match:
                value = match.group(1).strip()
                regex_score = 0.8
                match_pos = anchor_line_idx

        # If not found in anchor line, search nearby lines
        if not value:
            for offset in range(1, self.proximity_window + 1):
                if anchor_line_idx + offset < len(ocr_lines):
                    search_text = ocr_lines[anchor_line_idx + offset]
                    match = re.search(config["value_pattern"], search_text)

                    if match:
                        value = match.group(1).strip()
                        regex_score = 0.7 - (offset * 0.1)  # Decay with distance
                        match_pos = anchor_line_idx + offset
                        break

        if not value:
            return None

        # Calculate final confidence
        confidence = self._calculate_regex_confidence(
            value, field_type, regex_score, anchor_line_idx, match_pos
        )

        return ExtractionResult(
            field_type=field_type,
            value=value,
            confidence=confidence,
            source=ExtractionSource.REGEX,
            stage=ExtractionStage.REGEX,
            bbox=None,
            raw_text=ocr_lines[match_pos] if match_pos is not None else None,
            evidence={
                "anchor": anchor,
                "regex_score": regex_score,
                "proximity_score": self._calculate_proximity_score(match_pos, anchor_line_idx),
                "value_pattern": config["value_pattern"]
            }
        )

    def _calculate_regex_confidence(
        self, value: str, field_type: InvoiceFieldType, regex_score: float, anchor_idx: int, match_idx: Optional[int]
    ) -> float:
        """Calculate confidence using central service."""
        if match_idx is None:
            return 0.0

        proximity_score = self._calculate_proximity_score(match_idx, anchor_idx)
        
        return ConfidenceService.calculate_header_score(
            base_value=regex_score,
            value_text=value,
            proximity=proximity_score
        )

    def _calculate_proximity_score(self, match_idx: int, anchor_idx: int) -> float:
        """Score based on proximity to anchor (closer = higher score)."""
        distance = abs(match_idx - anchor_idx)
        if distance == 0:
            return 1.0
        return max(0.1, 1.0 - (distance * 0.15))

    def _calculate_text_quality(self, value: str, field_type: InvoiceFieldType) -> float:
        """Score text quality based on expected patterns."""
        if not value:
            return 0.1

        # Numeric fields: should contain numbers
        if field_type in [InvoiceFieldType.SUBTOTAL, InvoiceFieldType.VAT, InvoiceFieldType.TOTAL_AMOUNT, InvoiceFieldType.INVOICE_NUMBER]:
            if any(c.isdigit() for c in value):
                return 0.9
            return 0.3

        # Text fields: should be reasonable length
        if field_type in [InvoiceFieldType.VENDOR_NAME]:
            if len(value) >= 3:
                return 0.85
            return 0.4

        # Date: should contain numbers and separators
        if field_type == InvoiceFieldType.INVOICE_DATE:
            if re.search(r'\d+[/-]\d+[/-]\d+', value):
                return 0.9
            return 0.3

        return 0.7

    def supports_field(self, field_type: InvoiceFieldType) -> bool:
        """Check if field is supported by regex extractor."""
        return field_type in self.anchors


# ====== ML EXTRACTION (PLACEHOLDER) ======

class MLExtractor:
    """
    Stage 3: ML-based extraction.
    Placeholder for named entity recognition or custom ML models.
    Provides fallback when template/regex fail.
    """

    def __init__(self, confidence_threshold: float = 0.6):
        """
        Initialize ML extractor.
        
        Args:
            confidence_threshold: Minimum confidence for ML predictions
        """
        self.confidence_threshold = confidence_threshold

    def extract(self, ocr_lines: List[str], field_types: List[InvoiceFieldType]) -> List[ExtractionResult]:
        """
        Extract fields using ML model.
        This is a stub - implement with your chosen ML library.
        """
        results = []
        # TODO: Implement with:
        # - spaCy NER for named entity recognition
        # - Transformers for token classification
        # - Custom fine-tuned models
        return results

    def supports_field(self, field_type: InvoiceFieldType) -> bool:
        """Check if field is supported by ML extractor."""
        return True


# ====== LLM EXTRACTION (OPTIONAL) ======

class LLMExtractor:
    """
    Stage 4: LLM-based extraction (optional fallback).
    Uses language model for complex field extraction.
    Only invoked when confidence < threshold.
    """

    def __init__(self, confidence_threshold: float = 0.5, api_key: Optional[str] = None):
        """
        Initialize LLM extractor.
        
        Args:
            confidence_threshold: Invoke LLM if confidence < threshold
            api_key: API key for LLM service (OpenAI, Azure, etc.)
        """
        self.confidence_threshold = confidence_threshold
        self.api_key = api_key

    def extract(self, ocr_lines: List[str], field_types: List[InvoiceFieldType]) -> List[ExtractionResult]:
        """
        Extract fields using LLM.
        This is a stub - implement with your LLM API.
        """
        results = []
        # TODO: Implement with:
        # - OpenAI API
        # - Azure OpenAI
        # - Anthropic Claude
        # - Local LLM (Ollama, etc.)
        return results

    def supports_field(self, field_type: InvoiceFieldType) -> bool:
        """Check if field is supported by LLM extractor."""
        return True


# ====== MAIN EXTRACTION ENGINE ======

class HeaderExtractionEngine:
    """
    Main orchestrator for invoice header extraction.
    
    Pipeline order:
    1. Template extraction (fastest, most reliable)
    2. Regex anchor extraction (flexible, rule-based)
    3. ML extraction (adaptive, handles variations)
    4. LLM extraction (highest quality, fallback only)
    
    Each stage attempts extraction for missing fields.
    """

    def __init__(
        self,
        template_extractor: Optional[TemplateExtractor] = None,
        regex_extractor: Optional[RegexAnchorExtractor] = None,
        ml_extractor: Optional[MLExtractor] = None,
        llm_extractor: Optional[LLMExtractor] = None,
        confidence_threshold_for_llm: float = 0.5,
        enable_llm: bool = False,
    ):
        """
        Initialize extraction engine.
        
        Args:
            template_extractor: Template-based extractor (stage 1)
            regex_extractor: Regex anchor extractor (stage 2)
            ml_extractor: ML-based extractor (stage 3)
            llm_extractor: LLM-based extractor (stage 4, optional)
            confidence_threshold_for_llm: Invoke LLM if confidence < this
            enable_llm: Enable LLM fallback stage
        """
        self.template_extractor = template_extractor or TemplateExtractor()
        self.regex_extractor = regex_extractor or RegexAnchorExtractor()
        self.ml_extractor = ml_extractor or MLExtractor()
        self.llm_extractor = llm_extractor
        self.confidence_threshold_for_llm = confidence_threshold_for_llm
        self.enable_llm = enable_llm

    def extract_invoice_header(
        self,
        ocr_lines: List[str],
        field_types: Optional[List[InvoiceFieldType]] = None,
        ocr_confidence_scores: Optional[Dict[int, float]] = None,
    ) -> HeaderExtractionOutput:
        """
        Extract invoice header fields using multi-stage pipeline.
        
        Args:
            ocr_lines: List of OCR text lines
            field_types: Fields to extract (default: all)
            ocr_confidence_scores: Optional OCR confidence per line
            
        Returns:
            HeaderExtractionOutput with all extracted fields
        """
        import time
        start_time = time.time()

        # Default to all invoice fields
        if field_types is None:
            field_types = list(InvoiceFieldType)

        # Track all results and extracted fields
        all_results: List[ExtractionResult] = []
        extracted_fields: Dict[InvoiceFieldType, ExtractionResult] = {}
        remaining_fields = set(field_types)

        # Store OCR confidence scores
        self.ocr_confidence_by_line = ocr_confidence_scores or {}

        # ===== STAGE 1: TEMPLATE EXTRACTION =====
        if remaining_fields:
            template_results = self.template_extractor.extract(
                ocr_lines, list(remaining_fields)
            )
            for result in template_results:
                if result.confidence > 0.5:  # Only accept high-confidence matches
                    extracted_fields[result.field_type] = result
                    remaining_fields.discard(result.field_type)
                all_results.append(result)

        # ===== STAGE 2: REGEX ANCHOR EXTRACTION =====
        if remaining_fields:
            regex_results = self.regex_extractor.extract(ocr_lines, list(remaining_fields))
            for result in regex_results:
                if result.confidence > 0.4:  # Lower threshold for regex
                    extracted_fields[result.field_type] = result
                    remaining_fields.discard(result.field_type)
                all_results.append(result)

        # ===== STAGE 3: ML EXTRACTION =====
        if remaining_fields:
            ml_results = self.ml_extractor.extract(ocr_lines, list(remaining_fields))
            for result in ml_results:
                if result.confidence > 0.5:
                    extracted_fields[result.field_type] = result
                    remaining_fields.discard(result.field_type)
                all_results.append(result)

        # ===== STAGE 4: LLM EXTRACTION (OPTIONAL) =====
        if self.enable_llm and remaining_fields and self.llm_extractor:
            # Find fields with low confidence that could benefit from LLM
            low_confidence_fields = [
                ft for ft in remaining_fields
                if ft not in extracted_fields or extracted_fields[ft].confidence < self.confidence_threshold_for_llm
            ]

            if low_confidence_fields:
                llm_results = self.llm_extractor.extract(ocr_lines, low_confidence_fields)
                for result in llm_results:
                    if result.confidence > 0.6:
                        extracted_fields[result.field_type] = result
                        remaining_fields.discard(result.field_type)
                    all_results.append(result)

        # ===== CALCULATE OVERALL CONFIDENCE =====
        overall_confidence = self._calculate_overall_confidence(extracted_fields)

        # Determine final stage
        final_stage = self._determine_final_stage(all_results)

        processing_time = (time.time() - start_time) * 1000  # Convert to ms

        return HeaderExtractionOutput(
            fields=extracted_fields,
            overall_confidence=overall_confidence,
            extracted_at_stage=final_stage,
            processing_time_ms=processing_time,
            all_results=all_results,
        )

    def _calculate_overall_confidence(self, fields: Dict[InvoiceFieldType, ExtractionResult]) -> float:
        """Calculate overall extraction confidence."""
        if not fields:
            return 0.0

        total_confidence = sum(result.confidence for result in fields.values())
        return total_confidence / len(fields)

    def _determine_final_stage(self, results: List[ExtractionResult]) -> ExtractionStage:
        """Determine which stage completed the extraction."""
        if not results:
            return ExtractionStage.TEMPLATE

        # Return the latest stage that had a successful extraction
        stage_order = [
            ExtractionStage.TEMPLATE,
            ExtractionStage.REGEX,
            ExtractionStage.ML,
            ExtractionStage.LLM,
        ]

        for stage in reversed(stage_order):
            if any(r.stage == stage for r in results):
                return stage

        return ExtractionStage.TEMPLATE


# ====== FACTORY FUNCTION ======

def create_extraction_engine(
    enable_template: bool = True,
    enable_regex: bool = True,
    enable_ml: bool = False,
    enable_llm: bool = False,
    llm_api_key: Optional[str] = None,
    confidence_threshold_for_llm: float = 0.5,
) -> HeaderExtractionEngine:
    """
    Factory function to create configured HeaderExtractionEngine.
    
    Args:
        enable_template: Enable template extractor (stage 1)
        enable_regex: Enable regex extractor (stage 2)
        enable_ml: Enable ML extractor (stage 3)
        enable_llm: Enable LLM extractor (stage 4)
        llm_api_key: API key for LLM service
        confidence_threshold_for_llm: Invoke LLM if confidence < threshold
        
    Returns:
        Configured HeaderExtractionEngine
    """
    template_extractor = TemplateExtractor() if enable_template else None
    regex_extractor = RegexAnchorExtractor() if enable_regex else None
    ml_extractor = MLExtractor() if enable_ml else None
    llm_extractor = LLMExtractor(api_key=llm_api_key) if enable_llm else None

    return HeaderExtractionEngine(
        template_extractor=template_extractor,
        regex_extractor=regex_extractor,
        ml_extractor=ml_extractor,
        llm_extractor=llm_extractor,
        confidence_threshold_for_llm=confidence_threshold_for_llm,
        enable_llm=enable_llm,
    )
