from abc import ABC, abstractmethod
from typing import Dict, Any

class ExportAdapter(ABC):
    """Base interface for ERP export adapters."""
    
    @abstractmethod
    async def export(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Export data to the external system."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Return provider name."""
        pass
