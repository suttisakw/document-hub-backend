from datetime import UTC, datetime
from uuid import UUID
from sqlmodel import Session, select
import logging

from app.models import Document, ExtractedField, DocumentPage
from app.services.ocr_service import extract_text_detailed
from app.extraction.pipeline import ExtractionPipeline
from app.extraction.handlers.invoice import InvoiceHandler
from app.extraction.handlers.receipt import ReceiptHandler
from app.core.enums import DocumentType
from app.services.validation_and_normalization import ValidationAndNormalizationEngine
from app.services.storage import get_storage
from sqlalchemy import delete
import os

logger = logging.getLogger(__name__)

class ExtractionService:
    """
    High-level service to orchestrate the full extraction pipeline:
    OCR -> Document Classification -> Field Extraction -> Validation -> Persistence
    """

    def __init__(self, db: Session):
        self.db = db
        self.pipeline = ExtractionPipeline()
        self.validator = ValidationAndNormalizationEngine()
        # Handlers registry
        self.handlers = {
            DocumentType.INVOICE: InvoiceHandler(),
            DocumentType.RECEIPT: ReceiptHandler(),
        }

    async def process_document(self, document_id: UUID, ocr_result: dict | None = None):
        """
        Orchestrates the full extraction process by delegating to specialized engines.
        (Phase 4.1 Refactor)
        """
        from app.services.extraction.preprocessor import DocumentPreProcessor
        from app.services.extraction.ocr_engine import OcrEngine
        from app.services.extraction.table_engine import TableExtractionEngine
        from app.services.classifier_service import DocumentClassifier
        from app.services.config_service import ConfigService
        from app.models import DocumentTypeDefinition, DocumentPage
        import json

        doc = self.db.exec(select(Document).where(Document.id == document_id)).first()
        if not doc:
            logger.error(f"Document {document_id} not found")
            return

        try:
            if not ocr_result:
                doc.status = "processing"
                self.db.add(doc)
                self.db.commit()

                # 1. Pre-processing
                preprocessor = DocumentPreProcessor(self.db)
                pages = await preprocessor.prepare_pages(doc)

                # 2. OCR Execution
                ocr_engine = OcrEngine()
                processed_ocr = await ocr_engine.run_ocr(pages)
                full_text = processed_ocr.full_text
                pages_raw = processed_ocr.pages_raw
            else:
                full_text = ocr_result["full_text"]
                pages_raw = ocr_result["pages_raw"]
                pages = self.db.exec(select(DocumentPage).where(DocumentPage.document_id == document_id)).all()

            # 3. Classification
            classifier = DocumentClassifier()
            doc_type = classifier.classify(full_text)
            doc.type = doc_type.value

            # Load Schema & Validation Rules (Dynamic or Static)
            definition = self.db.exec(
                select(DocumentTypeDefinition).where(DocumentTypeDefinition.name == doc_type.value)
            ).first()
            
            validation_schema = None
            if definition and definition.active:
                try:
                    fields_to_extract = json.loads(definition.fields_schema)
                    if definition.validation_rules:
                        validation_schema = json.loads(definition.validation_rules)
                except Exception:
                    handler = self.handlers.get(doc_type, self.handlers[DocumentType.INVOICE])
                    fields_to_extract = handler.get_supported_fields()
            else:
                handler = self.handlers.get(doc_type, self.handlers[DocumentType.INVOICE])
                fields_to_extract = handler.get_supported_fields()

            # 5. Extraction Pipeline
            config_service = ConfigService(self.db)
            context = {
                "ocr_result": {
                    "text": full_text,
                    "raw_data": pages_raw,
                    "pages_count": len(pages)
                },
                "document": doc,
                "thresholds": config_service.get_thresholds()
            }
            extraction_result = await self.pipeline.extract(full_text, fields_to_extract, context=context)

            # 6. Table Extraction
            table_engine = TableExtractionEngine(self.db)
            doc.extracted_tables = await table_engine.extract_all_tables(doc, pages)

            # 7. Validation & Normalization
            # Extract report and updated_fields separately if needed, but validator currently returns Dict in our refactored flow?
            # Wait, our validator.validate_document_fields returns (report, updated_doc)
            # But in the orchestrator, we used it like this:
            # validated_fields = self.validator.validate_document_fields(extraction_result.fields)
            
            # I need to fix the call to match the engine's signature
            report, validated_doc_fields = self.validator.validate_document_fields(
                extraction_result.fields, 
                validation_schema=validation_schema
            )
            
            # 8. Persistence
            from sqlalchemy import delete
            from app.models import ExtractedField
            self.db.exec(delete(ExtractedField).where(ExtractedField.document_id == doc.id))
            
            for name, value in validated_doc_fields.items():
                conf = extraction_result.confidence_scores.get(name)
                ef = ExtractedField(
                    document_id=doc.id,
                    field_name=name,
                    field_value=str(value) if value is not None else None,
                    confidence=conf.value if conf else None,
                    created_at=datetime.utcnow()
                )
                self.db.add(ef)

            # 9. Confidence-Based Routing (Phase 6.1)
            stp_threshold = config_service.get_thresholds().get("sufficient_total_confidence", 0.8)
            
            reasons = []
            if doc.confidence and doc.confidence < stp_threshold:
                reasons.append(f"Low confidence ({doc.confidence:.2f} < {stp_threshold})")
            
            if not report.overall_valid:
                reasons.append("Validation failed (logical inconsistencies or schema issues)")

            if reasons:
                doc.status = "needs_review"
                doc.review_reason = " | ".join(reasons)
                logger.info(f"Document {doc.id} routed to review: {doc.review_reason}")
            else:
                doc.status = "completed"
                logger.info(f"Document {doc.id} passed STP criteria.")

            doc.scanned_at = datetime.utcnow()
            doc.full_text = full_text
            doc.confidence_report = {n: s.model_dump() for n, s in extraction_result.confidence_scores.items()}
            doc.extraction_report = {
                "stages": [stage.get_name() for stage in self.pipeline.stages],
                "metadata": extraction_result.metadata
            }
            # Add dynamic validation report
            from dataclasses import asdict
            doc.validation_report = {
                "overall_valid": report.overall_valid,
                "issues_count": report.invalid_count,
                "fields_needing_review": report.fields_needing_review,
                "results": [asdict(r) for r in report.results]
            }
            
            if extraction_result.confidence_scores:
                doc.confidence = sum(c.value for c in extraction_result.confidence_scores.values()) / len(extraction_result.confidence_scores)
            
            self.db.add(doc)
            self.db.commit()
            self.db.add(doc)
            self.db.commit()
            logger.info(f"Extraction completed for {doc.id}")
            
            # 10. Deep Intelligence: AI Summarization (Phase 3) - ASYNC
            try:
                from app.services.llm_queue_service import LlmQueueService
                
                llm_queue = LlmQueueService()
                
                # Submit summary task (non-blocking)
                summary_prompt = (
                    f"Summarize this {doc.type} in 1 brief sentence. "
                    "Include key entities like vendor, total amount, and dates. "
                    "Example: 'Invoice INV-001 from ACME Corp for $500.00 dated 2023-01-01.'"
                )
                summary_task_id = llm_queue.submit_task(
                    document_id=str(doc.id),
                    task_type="summary",
                    text=full_text[:2000],
                    schema=summary_prompt,
                    priority=1
                )
                
                # Submit insight task (non-blocking)
                insight_prompt = (
                    f"Analyze this {doc.type} text for anomalies or insights by returning a JSON object with keys: "
                    "'risk_level' (low/medium/high), 'flags' (list of strings), 'category_suggestion' (string). "
                    "Focus on unusual dates, extremely high amounts, or missing critical info."
                )
                insight_task_id = llm_queue.submit_task(
                    document_id=str(doc.id),
                    task_type="insight",
                    text=full_text[:3000],
                    schema=insight_prompt,
                    priority=1
                )
                
                logger.info(f"Submitted Deep Intelligence tasks for {doc.id}: summary={summary_task_id}, insight={insight_task_id}")
                # Note: Results will be updated by LLM worker asynchronously
                
            except Exception as e:
                logger.error(f"Deep Intelligence task submission failed for {doc.id}: {e}")

            # Phase 5.1: Semantic Indexing
            try:
                from app.services.vector_service import VectorService
                vector_service = VectorService(self.db)
                await vector_service.index_document(str(doc.id))
            except Exception as e:
                logger.error(f"Semantic indexing failed for {doc.id}: {e}")

        except Exception as e:
            logger.exception(f"Extraction failed for {doc.id}: {e}")
            doc.status = "error"
            self.db.add(doc)
            self.db.commit()
