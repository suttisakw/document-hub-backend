import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from app.extraction.stages.base import ExtractionStage, ExtractionStageResult
from app.schemas.confidence import ConfidenceScore, ExtractedSource, ExtractionStage as StageEnum
from app.services.confidence_service import ConfidenceService
from app.core.enums import InvoiceFieldType

logger = logging.getLogger(__name__)

class MlExtractionStage(ExtractionStage):
    """
    Stage 3: ML-based extraction.
    Uses spatial-textual heuristics (contextual proximity) to identify fields.
    Mimics LayoutLM behavior by considering bounding box proximity.
    """

    def __init__(self):
        self.field_labels = {
            InvoiceFieldType.INVOICE_NUMBER: ["invoice no", "inv no", "no.", "เลขที่ใบแจ้งหนี้"],
            InvoiceFieldType.INVOICE_DATE: ["date", "dated", "issued at", "วันที่"],
            InvoiceFieldType.TOTAL_AMOUNT: ["total", "grand total", "net amount", "จำนวนเงินรวม"],
            InvoiceFieldType.TAX_ID: ["tax id", "เลขประจำตัวผู้เสียภาษี"],
            InvoiceFieldType.VENDOR_NAME: ["from", "vendor", "supplier", "ผู้ขาย"]
        }

    async def execute(
        self, 
        text: str, 
        field_types: List[str], 
        context: Optional[Dict[str, Any]] = None,
        previous_best: Optional[ExtractionStageResult] = None
    ) -> ExtractionStageResult:
        fields = previous_best.fields.copy() if previous_best else {}
        confidences = previous_best.confidence_scores.copy() if previous_best else {}

        if not context or "ocr_result" not in context:
            logger.warning("ML Extraction Stage missing OCR context, skipping spatial analysis")
            return previous_best or ExtractionStageResult(
                fields={}, confidence_scores={}, stage_name=self.get_name()
            )

        raw_ocr = context["ocr_result"].get("raw_data")
        if not raw_ocr:
            return previous_best or ExtractionStageResult(
                fields={}, confidence_scores={}, stage_name=self.get_name()
            )

        # Flatten raw_ocr to list of (text, bbox)
        # Paddle format: [[ [ [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], ('text', conf) ], ... ]]
        blocks = []
        for page in raw_ocr:
            if not page: continue
            for entry in page:
                if len(entry) < 2: continue
                bbox = entry[0] # List of 4 points
                text_val = entry[1][0]
                # Center point of bbox
                cx = sum(p[0] for p in bbox) / 4
                cy = sum(p[1] for p in bbox) / 4
                blocks.append({"text": text_val.lower(), "bbox": bbox, "center": (cx, cy)})

        for field_type in field_types:
            # Skip if already high confidence
            if field_type in confidences and confidences[field_type].value > 0.8:
                continue

            labels = self.field_labels.get(field_type, [])
            for label in labels:
                for idx, block in enumerate(blocks):
                    if label in block["text"]:
                        # Found a likely label! Look for a value nearby
                        value_match = self._find_value_near(block, blocks, field_type)
                        if value_match:
                            val, dist_score = value_match
                            conf = ConfidenceService.calculate_header_score(0.85, val) * dist_score
                            
                            if field_type not in confidences or conf > confidences[field_type].value:
                                fields[field_type] = val
                                confidences[field_type] = ConfidenceScore(
                                    value=conf,
                                    source=ExtractedSource.ML,
                                    stage=StageEnum.ML,
                                    evidence={"label_found": label, "spatial_dist": dist_score},
                                    history=[conf]
                                )

        return ExtractionStageResult(
            fields=fields,
            confidence_scores=confidences,
            stage_name=self.get_name(),
            is_sufficient=all(f in fields and confidences[f].value > 0.8 for f in field_types)
        )

    def _find_value_near(self, label_block: dict, all_blocks: list, field_type: str) -> Optional[Tuple[str, float]]:
        """Find the most likely value block near a label block."""
        lb_cx, lb_cy = label_block["center"]
        
        best_match = None
        min_dist = 500 # Max pixel distance to consider
        
        for block in all_blocks:
            if block == label_block: continue
            
            b_cx, b_cy = block["center"]
            dx = b_cx - lb_cx
            dy = b_cy - lb_cy
            
            # Simple spatial rules:
            # 1. Same line (to the right)
            if abs(dy) < 20 and dx > 0 and dx < 300:
                dist = dx
                weight = 1.0
            # 2. Directly below
            elif abs(dx) < 50 and dy > 0 and dy < 100:
                dist = dy
                weight = 0.8
            else:
                continue
                
            if dist < min_dist:
                # Basic validation: does the block look like a value for this field?
                if self._is_valid_type(block["text"], field_type):
                    min_dist = dist
                    score = weight * (1.0 - (dist / 500))
                    best_match = (block["text"], score)
        
        return best_match

    def _is_valid_type(self, text: str, field_type: str) -> bool:
        if field_type == InvoiceFieldType.TOTAL_AMOUNT:
            return bool(re.search(r'\d', text))
        if field_type == InvoiceFieldType.INVOICE_NUMBER:
            return len(text) > 2
        return True

    def get_name(self) -> str:
        return "ml_extraction"
