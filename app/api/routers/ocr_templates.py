from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models import Document, ExtractedField, OcrTemplate, OcrTemplateZone, User
from app.schemas import OcrTemplateCreate, OcrTemplateResponse, OcrTemplateUpdate

router = APIRouter(prefix="/ocr/templates", tags=["ocr-templates"])


def _template_or_404(session: Session, user_id: UUID, template_id: UUID) -> OcrTemplate:
    tpl = session.exec(
        select(OcrTemplate).where(OcrTemplate.id == template_id, OcrTemplate.user_id == user_id)
    ).first()
    if tpl is None:
        raise HTTPException(status_code=404, detail="OCR template not found")
    return tpl


def _build_template_response(session: Session, tpl: OcrTemplate) -> OcrTemplateResponse:
    zones = session.exec(
        select(OcrTemplateZone)
        .where(OcrTemplateZone.template_id == tpl.id)
        .order_by(OcrTemplateZone.sort_order.asc(), OcrTemplateZone.created_at.asc())
    ).all()
    return OcrTemplateResponse(
        id=tpl.id,
        name=tpl.name,
        doc_type=tpl.doc_type,
        description=tpl.description,
        is_active=tpl.is_active,
        created_at=tpl.created_at,
        updated_at=tpl.updated_at,
        zones=list(zones),
    )


def _replace_zones(session: Session, template_id: UUID, zones: list) -> None:
    session.exec(delete(OcrTemplateZone).where(OcrTemplateZone.template_id == template_id))
    now = datetime.utcnow()
    for idx, z in enumerate(zones):
        session.add(
            OcrTemplateZone(
                template_id=template_id,
                page_number=z.page_number,
                label=z.label,
                field_type=z.field_type,
                x=z.x,
                y=z.y,
                width=z.width,
                height=z.height,
                required=z.required,
                sort_order=z.sort_order if z.sort_order is not None else idx,
                created_at=now,
                updated_at=now,
            )
        )


@router.get("", response_model=list[OcrTemplateResponse])
def list_templates(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[OcrTemplateResponse]:
    rows = session.exec(
        select(OcrTemplate)
        .where(OcrTemplate.user_id == current_user.id)
        .order_by(OcrTemplate.updated_at.desc())
    ).all()
    return [_build_template_response(session, r) for r in rows]


@router.post("", response_model=OcrTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(
    body: OcrTemplateCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OcrTemplateResponse:
    now = datetime.utcnow()
    tpl = OcrTemplate(
        user_id=current_user.id,
        name=body.name,
        doc_type=body.doc_type,
        description=body.description,
        is_active=body.is_active,
        created_at=now,
        updated_at=now,
    )
    session.add(tpl)
    session.commit()
    session.refresh(tpl)

    _replace_zones(session, tpl.id, body.zones)
    session.commit()
    return _build_template_response(session, tpl)


@router.get("/{template_id}", response_model=OcrTemplateResponse)
def get_template(
    template_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OcrTemplateResponse:
    tpl = _template_or_404(session, current_user.id, template_id)
    return _build_template_response(session, tpl)


@router.patch("/{template_id}", response_model=OcrTemplateResponse)
def update_template(
    template_id: UUID,
    body: OcrTemplateUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OcrTemplateResponse:
    tpl = _template_or_404(session, current_user.id, template_id)
    changed = False

    if body.name is not None:
        tpl.name = body.name
        changed = True
    if body.doc_type is not None:
        tpl.doc_type = body.doc_type
        changed = True
    if body.description is not None:
        tpl.description = body.description
        changed = True
    if body.is_active is not None:
        tpl.is_active = body.is_active
        changed = True

    if changed:
        tpl.updated_at = datetime.utcnow()
        session.add(tpl)

    if body.zones is not None:
        _replace_zones(session, tpl.id, body.zones)

    session.commit()
    session.refresh(tpl)
    return _build_template_response(session, tpl)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_template(
    template_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    tpl = _template_or_404(session, current_user.id, template_id)
    session.exec(delete(OcrTemplateZone).where(OcrTemplateZone.template_id == tpl.id))
    session.delete(tpl)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{template_id}/apply/{document_id}", response_model=dict)
def apply_template_to_document(
    template_id: UUID,
    document_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    tpl = _template_or_404(session, current_user.id, template_id)
    doc = session.exec(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    zones = session.exec(
        select(OcrTemplateZone)
        .where(OcrTemplateZone.template_id == tpl.id)
        .order_by(OcrTemplateZone.sort_order.asc())
    ).all()
    if not zones:
        return {"applied": 0}

    existing_fields = session.exec(
        select(ExtractedField).where(ExtractedField.document_id == doc.id)
    ).all()

    def overlap_score(zone: OcrTemplateZone, field: ExtractedField) -> float:
        if field.bbox_x is None or field.bbox_y is None:
            return -1.0
        if field.bbox_width is None or field.bbox_height is None:
            return -1.0
        cx = field.bbox_x + (field.bbox_width / 2)
        cy = field.bbox_y + (field.bbox_height / 2)
        inside_x = zone.x <= cx <= (zone.x + zone.width)
        inside_y = zone.y <= cy <= (zone.y + zone.height)
        return 1.0 if inside_x and inside_y else -1.0

    now = datetime.utcnow()
    applied = 0
    for zone in zones:
        best: ExtractedField | None = None
        best_score = -1.0
        for f in existing_fields:
            if (f.page_number or 1) != zone.page_number:
                continue
            score = overlap_score(zone, f)
            if score > best_score:
                best = f
                best_score = score

        existing_target = next(
            (
                f
                for f in existing_fields
                if f.field_name == zone.label and (f.page_number or 1) == zone.page_number
            ),
            None,
        )

        value = best.field_value if best is not None else None

        if existing_target is None:
            session.add(
                ExtractedField(
                    document_id=doc.id,
                    page_id=None,
                    page_number=zone.page_number,
                    field_name=zone.label,
                    field_value=value,
                    confidence=best.confidence if best is not None else None,
                    bbox_x=zone.x,
                    bbox_y=zone.y,
                    bbox_width=zone.width,
                    bbox_height=zone.height,
                    is_edited=False,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            existing_target.field_value = value
            existing_target.confidence = best.confidence if best is not None else None
            existing_target.bbox_x = zone.x
            existing_target.bbox_y = zone.y
            existing_target.bbox_width = zone.width
            existing_target.bbox_height = zone.height
            existing_target.updated_at = now
            session.add(existing_target)
        applied += 1

    doc.updated_at = now
    session.add(doc)
    session.commit()
    return {"applied": applied}
