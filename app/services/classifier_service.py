import re
import logging
from typing import List, Optional
from sqlmodel import Session, select
from app.core.enums import DocumentType
from app.models import DocumentTypeDefinition
from app.services.llm_service import get_llm_provider

logger = logging.getLogger(__name__)

class DocumentClassifier:
    """
    Service to classify document types based on OCR text contents.
    (Phase 3.4 of the architecture plan)
    """

    # Static keyword patterns for basic types
    STATIC_PATTERNS = {
        DocumentType.INVOICE: [r"invoice", r"tax invoice", r"ใบแจ้งหนี้", r"ใบกำกับภาษี", r"bill"],
        DocumentType.RECEIPT: [r"receipt", r"official receipt", r"ใบเสร็จรับเงิน", r"slip"],
        DocumentType.PURCHASE_ORDER: [r"purchase order", r"ใบสั่งซื้อ", r"po"]
    }

    async def classify(self, text: str, db: Optional[Session] = None) -> DocumentType:
        """
        Dual-mode classification: Keyword matching -> LLM Fallback.
        """
        text_lower = (text or "")[:4000].lower() # First 4k chars usually enough
        
        # 1. Keyword Matching
        scores = {}
        patterns = self.STATIC_PATTERNS.copy()
        
        # Merge dynamic types if DB available
        if db:
            dynamic_defs = db.exec(select(DocumentTypeDefinition).where(DocumentTypeDefinition.active == True)).all()
            for d in dynamic_defs:
                # Use name and display_name as keywords
                patterns[d.name] = [d.name.lower(), d.display_name.lower()]

        for doc_type, keywords in patterns.items():
            score = 0
            for kw in keywords:
                if re.search(re.escape(kw.lower()), text_lower):
                    score += 1
            scores[doc_type] = score
            
        best_type = None
        best_score = 0
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        if sorted_scores and sorted_scores[0][1] > 0:
            # If top match is significantly better than second, or only one match
            if len(sorted_scores) == 1 or sorted_scores[0][1] > (sorted_scores[1][1] * 1.5):
                best_type = sorted_scores[0][0]
                logger.info(f"Keyword-based classification: {best_type} (score={sorted_scores[0][1]})")

        # 2. LLM Fallback
        if not best_type or best_score < 1:
            logger.info("Keyword classification low confidence, falling back to LLM")
            try:
                available_types = list(patterns.keys())
                provider = get_llm_provider()
                llm_result = await provider.classify_document(text[:8000], available_types)
                if llm_result in available_types:
                    best_type = llm_result
                    logger.info(f"LLM-based classification: {best_type}")
            except Exception as e:
                logger.error(f"LLM classification failed: {e}")

        # Final Fallback
        result = best_type or DocumentType.INVOICE
        return result if isinstance(result, DocumentType) else DocumentType(result)
