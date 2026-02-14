from typing import List, Optional
from app.providers.erp.base import ErpProvider
from app.providers.erp.webhook_provider import WebhookErpProvider

class ErpService:
    """Service to handle ERP integrations."""

    def __init__(self, providers: Optional[List[ErpProvider]] = None):
        self.providers = providers or [
            # In real app, these would be loaded from DB/Config
            # WebhookErpProvider(webhook_url="https://api.erp.com/v1/sync")
        ]

    async def sync_all(self, document_id: str, data: dict):
        """Sync a document to all enabled ERP systems."""
        results = {}
        for provider in self.providers:
            success = await provider.sync_document(document_id, data)
            results[provider.get_name()] = success
        return results
