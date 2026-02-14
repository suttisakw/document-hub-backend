import httpx
from typing import Dict, Any
from app.providers.erp.base import ErpProvider

class WebhookErpProvider(ErpProvider):
    """Generic Webhook-based ERP integration."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def sync_document(self, document_id: str, data: Dict[str, Any]) -> bool:
        """Send data to external webhook."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.webhook_url,
                    json={
                        "document_id": document_id,
                        "extracted_data": data,
                        "timestamp": "now" # In real app use UTC isoformat
                    }
                )
                return response.status_code < 400
            except Exception:
                return False

    def get_name(self) -> str:
        return "generic_webhook"
