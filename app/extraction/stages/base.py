from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from app.schemas.confidence import ConfidenceScore

class ExtractionStageResult(BaseModel):
    """Result from a single extraction stage."""
    fields: Dict[str, Any]
    confidence_scores: Dict[str, ConfidenceScore]
    stage_name: str
    is_sufficient: bool = False
    metadata: Dict[str, Any] = {}

class ExtractionStage(ABC):
    """Base class for an extraction stage."""
    
    @abstractmethod
    async def execute(
        self, 
        text: str, 
        field_types: List[str], 
        context: Optional[Dict[str, Any]] = None,
        previous_best: Optional[ExtractionStageResult] = None
    ) -> ExtractionStageResult:
        """Execute extraction logic for this stage."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Name of the stage."""
        pass
