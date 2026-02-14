import logging
from typing import Dict, Any
from app.providers.export.base import ExportAdapter

logger = logging.getLogger(__name__)

class XeroAdapter(ExportAdapter):
    """Mock Xero implementation."""
    
    async def export(self, data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"Mock exporting to Xero: {data.get('invoice_number')}")
        return {
            "status": "success",
            "provider": "xero",
            "external_id": f"XERO_{data.get('invoice_number', 'unknown')}",
            "message": "Invoice pushed to Xero Accounting API via OAuth2."
        }

    def get_name(self) -> str:
        return "xero"
