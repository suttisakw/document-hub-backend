import logging
from typing import Dict, Any
from app.providers.export.base import ExportAdapter

logger = logging.getLogger(__name__)

class SapAdapter(ExportAdapter):
    """Mock SAP implementation."""
    
    async def export(self, data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"Mock exporting to SAP: {data.get('invoice_number')}")
        return {
            "status": "success",
            "provider": "sap",
            "external_id": f"SAP_{data.get('invoice_number', 'unknown')}",
            "message": "Data successfully mapped to SAP S/4HANA OData format."
        }

    def get_name(self) -> str:
        return "sap"
