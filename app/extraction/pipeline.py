from typing import List, Dict, Any, Optional
from app.extraction.stages.base import ExtractionStage, ExtractionStageResult
from app.extraction.stages.template import TemplateExtractionStage
from app.extraction.stages.regex import RegexExtractionStage
from app.extraction.stages.llm import LlmExtractionStage
from app.extraction.stages.ml import MlExtractionStage

class ExtractionPipeline:
    """Orchestrates multiple extraction stages."""

    def __init__(self, stages: Optional[List[ExtractionStage]] = None):
        self.stages = stages or [
            TemplateExtractionStage(),
            RegexExtractionStage(),
            MlExtractionStage(),
            LlmExtractionStage()
        ]

    async def extract(self, text: str, field_types: List[str], context: Optional[Dict[str, Any]] = None) -> ExtractionStageResult:
        """Run all stages in sequence until sufficient results are found."""
        current_best = None
        
        for stage in self.stages:
            result = await stage.execute(text, field_types, context, current_best)
            current_best = result
            
            if result.is_sufficient:
                break
                
        return current_best
