from __future__ import annotations
import logging
from typing import Dict, List, Any
from uuid import UUID
from sqlmodel import Session, select, func
from app.models import FieldCorrectionRecord, ExtractedField, Document
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class LearningService:
    """
    Analyzes user corrections to improve extraction accuracy.
    (Phase 3.1 of the architecture plan)
    """

    def __init__(self, db: Session):
        self.db = db

    def get_field_accuracy_report(self, days: int = 30) -> List[Dict[str, Any]]:
        """Calculate accuracy metrics for each field type."""
        since = datetime.utcnow() - timedelta(days=days)
        
        # Get all extracted fields since period
        fields = self.db.exec(
            select(ExtractedField).where(ExtractedField.created_at >= since)
        ).all()
        
        stats = {}
        for f in fields:
            if f.field_name not in stats:
                stats[f.field_name] = {"total": 0, "corrected": 0, "sum_confidence": 0.0}
            
            stats[f.field_name]["total"] += 1
            if f.is_corrected:
                stats[f.field_name]["corrected"] += 1
            stats[f.field_name]["sum_confidence"] += (f.confidence or 0.0)

        report = []
        for name, data in stats.items():
            accuracy = (data["total"] - data["corrected"]) / data["total"] if data["total"] > 0 else 0
            avg_conf = data["sum_confidence"] / data["total"] if data["total"] > 0 else 0
            
            report.append({
                "field_name": name,
                "total_extractions": data["total"],
                "corrected_count": data["corrected"],
                "accuracy": round(accuracy, 2),
                "avg_confidence": round(avg_conf, 2),
                "calibration_error": round(avg_conf - accuracy, 2)
            })
            
        return report

    def suggest_heuristic_adjustments(self) -> List[str]:
        """Identify fields that are consistently over-confident but wrong."""
        report = self.get_field_accuracy_report(days=90)
        suggestions = []
        for r in report:
            if r["calibration_error"] > 0.3 and r["total_extractions"] > 10:
                suggestions.append(
                    f"Field '{r['field_name']}' is over-confident (avg_conf={r['avg_confidence']}) "
                    f"but has low accuracy ({r['accuracy']}). Consider increasing validation strictness."
                )
        return suggestions

    def apply_auto_calibration(self) -> Dict[str, Any]:
        """
        Automatically adjust system confidence thresholds based on 
        recent extraction accuracy (Phase 3.1).
        """
        report = self.get_field_accuracy_report(days=60)
        from app.services.config_service import ConfigService
        config_service = ConfigService(self.db)
        
        updates = {}
        for r in report:
            # If AI is overconfident but wrong, increase the required threshold
            if r["calibration_error"] > 0.2:
                current_threshold = config_service.get_config("extraction_threshold", "0.7")
                new_threshold = min(0.95, float(current_threshold) + 0.05)
                config_service.set_config("extraction_threshold", str(new_threshold))
                updates["extraction_threshold"] = new_threshold
        
        return {
            "status": "success",
            "updated_configs": updates,
            "analysis_based_on": len(report)
        }

    def suggest_new_templates(self) -> List[Dict[str, Any]]:
        """
        Analyze recurring field patterns to suggest new document templates (Phase 5.3).
        If multiple documents of 'unknown' or 'generic' type have similar fields,
        suggest a new DocumentTypeDefinition.
        """
        # 1. Identify documents with high number of manually added fields or corrections
        # For simplicity, we look for recurring field names in recent documents
        since = datetime.utcnow() - timedelta(days=90)
        fields = self.db.exec(
            select(ExtractedField).where(ExtractedField.created_at >= since)
        ).all()

        # Count occurrences of field sets per document type
        doc_field_sets = {}
        for f in fields:
            doc_id = str(f.document_id)
            if doc_id not in doc_field_sets:
                doc_field_sets[doc_id] = set()
            doc_field_sets[doc_id].add(f.field_name)

        # Cluster documents by their field sets
        field_clusters = {}
        for doc_id, field_set in doc_field_sets.items():
            cluster_key = tuple(sorted(list(field_set)))
            if cluster_key not in field_clusters:
                field_clusters[cluster_key] = []
            field_clusters[cluster_key].append(doc_id)

        suggestions = []
        for field_set, doc_ids in field_clusters.items():
            # If we see the same field set in 3+ documents, it's a potential template
            if len(doc_ids) >= 3:
                # Check if a template with these fields already exists
                # (Simple check: is there a definition with exactly these fields?)
                import json
                from app.models import DocumentTypeDefinition
                
                existing = self.db.exec(select(DocumentTypeDefinition)).all()
                is_new = True
                for defn in existing:
                    try:
                        defn_fields = set(json.loads(defn.fields_schema))
                        if defn_fields == set(field_set):
                            is_new = False
                            break
                    except: continue
                
                if is_new:
                    suggestions.append({
                        "suggested_name": f"Template_{len(suggestions)+1}",
                        "fields": list(field_set),
                        "evidence_count": len(doc_ids),
                        "reason": f"Found {len(doc_ids)} documents sharing these exact {len(field_set)} fields."
                    })

        return suggestions
