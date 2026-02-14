from abc import ABC, abstractmethod
from typing import List, Dict, Any
from app.core.enums import InvoiceFieldType, DocumentType

class DocumentTypeHandler(ABC):
    """Base class for document-specific extraction and validation logic."""
    
    @abstractmethod
    def get_document_type(self) -> DocumentType:
        """Return the document type this handler supports."""
        pass

    @abstractmethod
    def get_supported_fields(self) -> List[str]:
        """Return fields that should be extracted for this document type."""
        pass

    @abstractmethod
    def validate(self, extracted_data: Dict[str, Any]) -> bool:
        """Perform document-specific validation (e.g., mandatory fields)."""
        pass
