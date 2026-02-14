from typing import List, Dict, Any, Optional
from app.extraction.stages.base import ExtractionStage, ExtractionStageResult
from app.schemas.confidence import ConfidenceScore, ExtractedSource, ExtractionStage as StageEnum
from app.services.llm_service import get_llm_provider
from app.services.confidence_service import ConfidenceService

class LlmExtractionStage(ExtractionStage):
    """Stage 4: LLM-based extraction."""

    async def execute(
        self, 
        text: str, 
        field_types: List[str], 
        context: Optional[Dict[str, Any]] = None,
        previous_best: Optional[ExtractionStageResult] = None
    ) -> ExtractionStageResult:
        fields = previous_best.fields.copy() if previous_best else {}
        confidences = previous_best.confidence_scores.copy() if previous_best else {}
        
        # Determine missing or low-confidence fields
        missing = [f for f in field_types if f not in fields or confidences[f].value < 0.6]
        if not missing:
            return previous_best or ExtractionStageResult(fields={}, confidence_scores={}, stage_name=self.get_name())

        schema_desc = "\n".join([f"* {f}" for f in missing])
        provider = get_llm_provider()
        result = await provider.extract_fields(text, schema_desc)
        
        for f, val in result.data.items():
            if f in field_types:
                conf_val = ConfidenceService.calculate_header_score(0.75, str(val))
                fields[f] = val
                confidences[f] = ConfidenceScore(
                    value=conf_val,
                    source=ExtractedSource.LLM,
                    stage=StageEnum.LLM,
                    evidence={"model": result.model_name},
                    history=[conf_val]
                )
        
        return ExtractionStageResult(
            fields=fields,
            confidence_scores=confidences,
            stage_name=self.get_name(),
            is_sufficient=True,
            metadata={"model": result.model_name}
        )

    def get_name(self) -> str:
        return "llm_extraction"
