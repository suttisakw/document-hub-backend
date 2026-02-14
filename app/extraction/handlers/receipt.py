from typing import List, Dict, Any
from app.extraction.handlers.base import DocumentTypeHandler
from app.core.enums import DocumentType

class ReceiptHandler(DocumentTypeHandler):
    """Handler for Receipt documents."""

    def get_document_type(self) -> DocumentType:
        return DocumentType.RECEIPT

    def get_supported_fields(self) -> List[str]:
        return [
            "receipt_number",
            "date",
            "vendor",
            "total_amount",
            "payment_method"
        ]

    def validate(self, extracted_data: Dict[str, Any]) -> bool:
        return "total_amount" in extracted_data and extracted_data["total_amount"]
