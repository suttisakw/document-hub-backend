from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class BaseValidator(ABC):
    """Base class for field validation rules."""
    
    @abstractmethod
    def validate(self, value: Any, context: Optional[Dict[str, Any]] = None) -> bool:
        """Return True if value is valid."""
        pass

    @abstractmethod
    def normalize(self, value: Any) -> Any:
        """Normalize the value (e.g., date to ISO string)."""
        pass
