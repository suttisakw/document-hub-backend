import logging
import csv
import json
import io
from typing import Dict, Any, List, Optional
from sqlmodel import Session, select
from app.models import Document, ExtractedField
from app.providers.export.sap_adapter import SapAdapter
from app.providers.export.xero_adapter import XeroAdapter

logger = logging.getLogger(__name__)

class ExportService:
    """Orchestrates document data exports to different formats and systems."""
    
    def __init__(self, db: Session):
        self.db = db
        self.adapters = {
            "sap": SapAdapter(),
            "xero": XeroAdapter()
        }

    def _get_document_data(self, doc_id: str) -> Dict[str, Any]:
        """Collect all fields for a document."""
        doc = self.db.get(Document, doc_id)
        if not doc:
            raise ValueError("Document not found")
            
        fields = self.db.exec(
            select(ExtractedField).where(ExtractedField.document_id == doc.id)
        ).all()
        
        data = {
            "id": str(doc.id),
            "name": doc.name,
            "type": doc.type,
            "confidence": doc.confidence,
            "scanned_at": doc.scanned_at.isoformat() if doc.scanned_at else None,
            "ai_summary": doc.ai_summary,
            "ai_insight": doc.ai_insight
        }
        
        for f in fields:
            data[f.field_name] = f.field_value
            
        return data

    async def export_to_system(self, doc_id: str, target: str) -> Dict[str, Any]:
        """Export to a specific external system (SAP, Xero, etc)."""
        adapter = self.adapters.get(target.lower())
        if not adapter:
            raise ValueError(f"Unsupported export target: {target}")
            
        data = self._get_document_data(doc_id)
        return await adapter.export(data)

    def export_to_csv(self, doc_ids: List[str]) -> str:
        """Export multiple documents to a single CSV string."""
        output = io.StringIO()
        
        # Get data for all docs to determine headers
        all_data = []
        headers = set()
        for d_id in doc_ids:
            try:
                data = self._get_document_data(d_id)
                all_data.append(data)
                headers.update(data.keys())
            except Exception as e:
                logger.error(f"Error collecting data for doc {d_id}: {e}")
        
        if not all_data:
            return ""
            
        writer = csv.DictWriter(output, fieldnames=sorted(list(headers)))
        writer.writeheader()
        for row in all_data:
            writer.writerow(row)
            
        return output.getvalue()

    def export_to_json(self, doc_ids: List[str]) -> str:
        """Export multiple documents to a JSON string."""
        all_data = []
        for d_id in doc_ids:
            try:
                all_data.append(self._get_document_data(d_id))
            except Exception as e:
                logger.error(f"Error collecting data for doc {d_id}: {e}")
        
        return json.dumps(all_data, indent=2)
