from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_current_user
from app.models import User
from app.services.llm_service import extract_invoice_fields
from app.services.ocr_service import extract_text

router = APIRouter(tags=["document-extraction"])


@router.post("/extract-document")
def extract_document(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
) -> dict[str, object]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    tmp_dir = Path("/tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename).suffix
    temp_path = tmp_dir / f"{uuid4()}{suffix}"

    try:
        with temp_path.open("wb") as out_file:
            shutil.copyfileobj(file.file, out_file)

        ocr_text = extract_text(str(temp_path))
        extracted = extract_invoice_fields(ocr_text)

        return {
            "ocr_text": ocr_text,
            "extracted": extracted,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}") from exc
    finally:
        try:
            file.file.close()
        except Exception:
            pass
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
