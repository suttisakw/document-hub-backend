import re
from typing import List, Dict, Any, Optional
from app.extraction.stages.base import ExtractionStage, ExtractionStageResult
from app.schemas.confidence import ConfidenceScore, ExtractedSource, ExtractionStage as StageEnum
from app.services.confidence_service import ConfidenceService
from app.core.enums import InvoiceFieldType

class RegexExtractionStage(ExtractionStage):
    """Stage 2: Regex anchor-based extraction."""

    def __init__(self, proximity_window: int = 3):
        self.proximity_window = proximity_window
        self.anchors = self._build_anchors()

    def _build_anchors(self) -> Dict[str, Dict[str, Any]]:
        return {
            InvoiceFieldType.INVOICE_NUMBER: {
                "anchors": ["invoice", "inv", "number", "no:", "no.", "#"],
                "value_pattern": r"([A-Z0-9\-/]+)",
            },
            InvoiceFieldType.TOTAL_AMOUNT: {
                "anchors": ["total", "grand total", "amount due"],
                "value_pattern": r"([0-9,.\s]+)",
            },
        }

    async def execute(
        self, 
        text: str, 
        field_types: List[str], 
        context: Optional[Dict[str, Any]] = None,
        previous_best: Optional[ExtractionStageResult] = None
    ) -> ExtractionStageResult:
        ocr_lines = text.split("\n")
        fields = previous_best.fields.copy() if previous_best else {}
        confidences = previous_best.confidence_scores.copy() if previous_best else {}
        
        for field_type in field_types:
            if field_type in fields and confidences[field_type].value > 0.8: continue
            if field_type not in self.anchors: continue
            
            config = self.anchors[field_type]
            for idx, line in enumerate(ocr_lines):
                for anchor in config["anchors"]:
                    if anchor.lower() in line.lower():
                        # Simple look-ahead in same line
                        match = re.search(config["value_pattern"], line[line.lower().find(anchor.lower()) + len(anchor):])
                        if match:
                            val = match.group(1).strip()
                            conf = ConfidenceService.calculate_header_score(0.8, val)
                            if field_type not in confidences or conf > confidences[field_type].value:
                                fields[field_type] = val
                                confidences[field_type] = ConfidenceScore(
                                    value=conf,
                                    source=ExtractedSource.REGEX,
                                    stage=StageEnum.REGEX,
                                    evidence={"anchor_match": anchor},
                                    history=[conf]
                                )
                                break
        
        return ExtractionStageResult(
            fields=fields,
            confidence_scores=confidences,
            stage_name=self.get_name(),
            is_sufficient=all(f in fields for f in field_types)
        )

    def get_name(self) -> str:
        return "regex_extraction"
