from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel

class LlmResult(BaseModel):
    data: Dict[str, Any]
    raw_response: str
    model_name: str
    usage: Optional[Dict[str, int]] = None

class LlmProvider(ABC):
    """Base class for all LLM providers."""
    
    @abstractmethod
    async def extract_fields(self, text: str, schema_description: str) -> LlmResult:
        """Extract structured fields from text."""
        pass
    
    @abstractmethod
    async def classify_document(self, text: str, categories: list[str]) -> str:
        """Classify document into one of the given categories."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Return the name of the provider."""
        pass

    @abstractmethod
    async def get_embedding(self, text: str) -> list[float]:
        """Generate vector embedding for the given text."""
        pass
