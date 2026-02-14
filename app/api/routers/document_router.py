from __future__ import annotations

import shutil
import tempfile
import os
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models import User
from app.core.enums import DocumentType
from app.services.extraction_service import ExtractionService
from app.services.ocr_service import extract_text_detailed
from app.services.classifier_service import DocumentClassifier

router = APIRouter(tags=["document-extraction"])

@router.post(
    "/extract-document",
    summary="Extract document",
    description="Full modular extraction (OCR -> Classify -> Extract -> Validate) from uploaded file.",
)
async def extract_document(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> dict[str, object]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    suffix = Path(file.filename).suffix
    fd, temp_path_str = tempfile.mkstemp(suffix=suffix)
    temp_path = Path(temp_path_str)

    try:
        with os.fdopen(fd, "wb") as out_file:
            shutil.copyfileobj(file.file, out_file)

        # 1. OCR
        ocr_result = extract_text_detailed(str(temp_path))
        
        # 2. Classification
        classifier = DocumentClassifier()
        doc_type = classifier.classify(ocr_result.text)
        
        # 3. Extraction
        service = ExtractionService(session)
        handler = service.handlers.get(doc_type, service.handlers[DocumentType.INVOICE])
        fields_to_extract = handler.get_supported_fields()
        
        extraction_result = await service.pipeline.extract(ocr_result.text, fields_to_extract)
        
        # 4. Validation
        validated_fields = service.validator.validate_document_fields(extraction_result.fields)

        return {
            "ocr_text": ocr_result.text,
            "doc_type": doc_type.value,
            "extracted": validated_fields,
            "confidence": {
                name: score.model_dump() 
                for name, score in extraction_result.confidence_scores.items()
            }
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}") from exc
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
