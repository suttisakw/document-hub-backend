from typing import List, Dict, Any
from app.extraction.handlers.base import DocumentTypeHandler
from app.core.enums import InvoiceFieldType, DocumentType

class InvoiceHandler(DocumentTypeHandler):
    """Handler for Invoice documents."""

    def get_document_type(self) -> DocumentType:
        return DocumentType.INVOICE

    def get_supported_fields(self) -> List[str]:
        return [
            InvoiceFieldType.INVOICE_NUMBER,
            InvoiceFieldType.INVOICE_DATE,
            InvoiceFieldType.VENDOR_NAME,
            InvoiceFieldType.TOTAL_AMOUNT,
            InvoiceFieldType.TAX_ID,
            InvoiceFieldType.SUBTOTAL,
            InvoiceFieldType.VAT
        ]

    def validate(self, extracted_data: Dict[str, Any]) -> bool:
        # Mandatory fields for invoice
        mandatory = [InvoiceFieldType.INVOICE_NUMBER, InvoiceFieldType.TOTAL_AMOUNT]
        return all(f in extracted_data and extracted_data[f] for f in mandatory)
