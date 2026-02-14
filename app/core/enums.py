from enum import Enum

class InvoiceFieldType(str, Enum):
    """Supported invoice header fields."""
    INVOICE_NUMBER = "invoice_number"
    INVOICE_DATE = "invoice_date"
    VENDOR_NAME = "vendor_name"
    TAX_ID = "tax_id"
    SUBTOTAL = "subtotal"
    VAT = "vat"
    TOTAL_AMOUNT = "total_amount"

class DocumentType(str, Enum):
    """Supported document types."""
    INVOICE = "invoice"
    RECEIPT = "receipt"
    PURCHASE_ORDER = "purchase_order"
    STATEMENT = "statement"
    UNKNOWN = "unknown"
