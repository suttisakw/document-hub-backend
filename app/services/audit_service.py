import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from sqlmodel import Session, select
from app.models import Document, ExtractedField
from app.services.llm_service import get_llm_provider

logger = logging.getLogger(__name__)

class AuditIssue(BaseModel):
    field_name: str
    issue_type: str  # logical_inconsistency, data_mismatch, missing_logic
    description: str
    severity: str  # warning, high, medium
    suggested_fix: Optional[str] = None

class AuditReport(BaseModel):
    overall_status: str
    issues: List[AuditIssue]
    metadata: Dict[str, Any]

class AuditService:
    """Uses LLM to verify business logic and data consistency."""
    
    def __init__(self, db: Session):
        self.db = db
        self.llm = get_llm_provider()

    async def audit_document(self, doc_id: str) -> AuditReport:
        """Runs a deep logic audit on extracted data."""
        doc = self.db.get(Document, doc_id)
        if not doc:
            raise ValueError("Document not found")
            
        fields = self.db.exec(
            select(ExtractedField).where(ExtractedField.document_id == doc.id)
        ).all()
        
        field_map = {f.field_name: f.field_value for f in fields}
        
        prompt = (
            f"Act as a business logic auditor. I have extracted fields from an OCR document ({doc.type}).\n"
            f"Review the extracted fields below against common business logic (e.g., total = subtotal + vat).\n\n"
            f"Extracted Data:\n{field_map}\n\n"
            f"Document Text Context (Snippets):\n{doc.full_text[:2000] if doc.full_text else 'No text available'}\n\n"
            f"Return a list of logical inconsistencies or errors in JSON format with keys:\n"
            f"- field_name, issue_type, description, severity, suggested_fix"
        )
        
        # We use the generic extract_fields but with a specialized prompt
        audit_result = await self.llm.extract_fields(prompt, "JSON list of objects with field_name, issue_type, description, severity, suggested_fix")
        
        issues_raw = audit_result.data.get("items", []) if isinstance(audit_result.data, dict) else audit_result.data
        if not isinstance(issues_raw, list):
            issues_raw = []
            
        issues = [AuditIssue(**i) for i in issues_raw if isinstance(i, dict)]
        
        report = AuditReport(
            overall_status="pass" if not issues else "fail",
            issues=issues,
            metadata={"model": audit_result.model_name}
        )
        
        return report
