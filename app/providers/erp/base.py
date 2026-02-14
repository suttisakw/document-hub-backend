from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class ErpProvider(ABC):
    """Base class for ERP integration providers."""
    
    @abstractmethod
    async def sync_document(self, document_id: str, data: Dict[str, Any]) -> bool:
        """Sync extracted document data to the ERP system."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Name of the ERP system (e.g., SAP, Xero)."""
        pass
