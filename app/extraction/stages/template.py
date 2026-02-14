import re
from typing import List, Dict, Any, Optional
from app.extraction.stages.base import ExtractionStage, ExtractionStageResult
from app.schemas.confidence import ConfidenceScore, ExtractedSource, ExtractionStage as StageEnum
from app.services.confidence_service import ConfidenceService
from app.core.enums import InvoiceFieldType

class TemplateExtractionStage(ExtractionStage):
    """Stage 1: Template-based extraction."""

    def __init__(self, confidence_base: float = 0.95):
        self.confidence_base = confidence_base
        self.templates = self._build_templates()

    def _build_templates(self) -> Dict[str, List[Dict[str, Any]]]:
        # Borrowed from original header_extraction_engine.py
        return {
            InvoiceFieldType.INVOICE_NUMBER: [
                {"pattern": r"(?:invoice\s+(?:number|no\.?|#|number:))\s*[:\s]*([A-Z0-9\-/]+)", "normalized": True},
            ],
            InvoiceFieldType.INVOICE_DATE: [
                {"pattern": r"(?:invoice\s+date|date|dated|issued)\s*[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", "normalized": False},
            ],
            InvoiceFieldType.VENDOR_NAME: [
                {"pattern": r"(?:from|vendor|supplier|company|by)\s*[:\s]*([A-Za-z0-9\s&.,'-]+?)(?:\n|$)", "normalized": False},
            ],
            InvoiceFieldType.TOTAL_AMOUNT: [
                {"pattern": r"(?:total|grand\s+total|total\s+amount|amount\s+due)\s*[:\s]*([0-9,.\s]+)", "normalized": True},
            ]
        }

    async def execute(
        self, 
        text: str, 
        field_types: List[str], 
        context: Optional[Dict[str, Any]] = None,
        previous_best: Optional[ExtractionStageResult] = None
    ) -> ExtractionStageResult:
        fields = {}
        confidences = {}
        sufficient_count = 0

        for field_type in field_types:
            if field_type not in self.templates: continue
            
            best_val = None
            best_conf = 0.0
            
            for template in self.templates[field_type]:
                match = re.search(template["pattern"], text, re.IGNORECASE | re.MULTILINE)
                if match:
                    val = match.group(1).strip()
                    conf = ConfidenceService.calculate_header_score(self.confidence_base, val)
                    if conf > best_conf:
                        best_conf = conf
                        best_val = val
            
            if best_val:
                fields[field_type] = best_val
                confidences[field_type] = ConfidenceScore(
                    value=best_conf,
                    source=ExtractedSource.TEMPLATE,
                    stage=StageEnum.TEMPLATE,
                    evidence={"pattern_match": True},
                    history=[best_conf]
                )
                if best_conf > 0.8: sufficient_count += 1

        return ExtractionStageResult(
            fields=fields,
            confidence_scores=confidences,
            stage_name=self.get_name(),
            is_sufficient=sufficient_count >= len(field_types) * 0.7
        )

    def get_name(self) -> str:
        return "template_extraction"
