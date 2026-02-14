from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from enum import Enum

class ExtractedSource(str, Enum):
    TEMPLATE = "template"
    REGEX = "regex"
    ML = "ml"
    LLM = "llm"
    MANUAL = "manual"

class ExtractionStage(str, Enum):
    TEMPLATE = "stage_1_template"
    REGEX = "stage_2_regex"
    ML = "stage_3_ml"
    LLM = "stage_4_llm"

class ConfidenceScore(BaseModel):
    """
    Unified confidence score schema across all extraction engines.
    """
    value: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0.0-1.0)")
    source: ExtractedSource = Field(..., description="Method/Source of extraction")
    stage: ExtractionStage = Field(..., description="Pipeline stage that performed extraction")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Metadata/Evidence for the score")
    validation_adjusted: bool = Field(default=False, description="Whether the score was adjusted by validation")
    history: List[float] = Field(default_factory=list, description="Tracking score changes through pipeline")

    class Config:
        json_schema_extra = {
            "example": {
                "value": 0.95,
                "source": "template",
                "stage": "stage_1_template",
                "evidence": {"match_quality": 0.98},
                "validation_adjusted": False,
                "history": [0.95]
            }
        }
