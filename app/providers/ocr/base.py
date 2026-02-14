from abc import ABC, abstractmethod
from typing import List, Optional, Any
from pydantic import BaseModel

class OcrResult(BaseModel):
    text: str
    lines: List[str]
    raw_data: Optional[Any] = None
    confidence: float = 0.0
    language: str = "en"

class OcrProvider(ABC):
    """Base class for all OCR providers."""
    
    @abstractmethod
    def extract_text(self, file_path: str, lang: str = "th") -> OcrResult:
        """Extract text from a file."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Return the name of the provider."""
        pass
