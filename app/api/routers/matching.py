from __future__ import annotations

from datetime import datetime
from itertools import combinations
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models import (
    Document,
    DocumentMatchSet,
    DocumentMatchSetLink,
    ExtractedField,
    MatchingRule,
    MatchingRuleCondition,
    User,
)
from app.schemas import (
    AddDocumentsToMatchSetRequest,
    AutoMatchPairItem,
    AutoMatchResponse,
    DocumentMatchSetCreate,
    DocumentMatchSetResponse,
    DocumentMatchSetUpdate,
    MatchSetDocumentResponse,
)
from app.services.matching_engine import RuleCondition, evaluate_pair

router = APIRouter(prefix="/matching", tags=["matching"])


def _set_or_404(session: Session, set_id: UUID, user_id: UUID) -> DocumentMatchSet:
    item = session.exec(
        select(DocumentMatchSet).where(
            DocumentMatchSet.id == set_id,
            DocumentMatchSet.user_id == user_id,
        )
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Match set not found")
    return item


def _build_set_response(session: Session, item: DocumentMatchSet) -> DocumentMatchSetResponse:
    links = session.exec(
        select(DocumentMatchSetLink).where(DocumentMatchSetLink.set_id == item.id)
    ).all()
    doc_ids = [link.document_id for link in links]
    docs = []
    if doc_ids:
        docs = session.exec(select(Document).where(Document.id.in_(doc_ids))).all()
    return DocumentMatchSetResponse(
        id=item.id,
        name=item.name,
        status=item.status,
        source=item.source,
        rule_id=item.rule_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
        documents=[MatchSetDocumentResponse.model_validate(d, from_attributes=True) for d in docs],
    )


def _doc_in_any_set(session: Session, document_id: UUID) -> bool:
    return (
        session.exec(
            select(DocumentMatchSetLink).where(DocumentMatchSetLink.document_id == document_id)
        ).first()
        is not None
    )


@router.get(
    "/sets",
    response_model=list[DocumentMatchSetResponse],
    summary="List match sets",
    description="All match sets for current user.",
)
def list_sets(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[DocumentMatchSetResponse]:
    items = session.exec(
        select(DocumentMatchSet)
        .where(DocumentMatchSet.user_id == current_user.id)
        .order_by(DocumentMatchSet.updated_at.desc())
    ).all()
    return [_build_set_response(session, item) for item in items]


@router.post(
    "/sets",
    response_model=DocumentMatchSetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create match set",
    description="Create a new match set (manual).",
)
def create_set(
    body: DocumentMatchSetCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DocumentMatchSetResponse:
    now = datetime.utcnow()
    item = DocumentMatchSet(
        user_id=current_user.id,
        name=body.name,
        status=body.status,
        source="manual",
        created_at=now,
        updated_at=now,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return _build_set_response(session, item)


@router.get(
    "/sets/{set_id}",
    response_model=DocumentMatchSetResponse,
    summary="Get match set",
    description="Single set with documents.",
)
def get_set(
    set_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DocumentMatchSetResponse:
    item = _set_or_404(session, set_id, current_user.id)
    return _build_set_response(session, item)


@router.patch(
    "/sets/{set_id}",
    response_model=DocumentMatchSetResponse,
    summary="Update match set",
    description="Update name, status.",
)
def update_set(
    set_id: UUID,
    body: DocumentMatchSetUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DocumentMatchSetResponse:
    item = _set_or_404(session, set_id, current_user.id)
    changed = False
    if body.name is not None:
        item.name = body.name
        changed = True
    if body.status is not None:
        item.status = body.status
        changed = True
    if changed:
        item.updated_at = datetime.utcnow()
        session.add(item)
        session.commit()
        session.refresh(item)
    return _build_set_response(session, item)


@router.delete(
    "/sets/{set_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete match set",
    description="Delete set and its document links.",
)
def delete_set(
    set_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    item = _set_or_404(session, set_id, current_user.id)
    session.exec(delete(DocumentMatchSetLink).where(DocumentMatchSetLink.set_id == item.id))
    session.delete(item)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sets/{set_id}/documents",
    response_model=DocumentMatchSetResponse,
    summary="Add documents to set",
    description="Add documents to match set; document must not be in another set.",
)
def add_documents_to_set(
    set_id: UUID,
    body: AddDocumentsToMatchSetRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DocumentMatchSetResponse:
    item = _set_or_404(session, set_id, current_user.id)
    if not body.document_ids:
        return _build_set_response(session, item)

    docs = session.exec(
        select(Document).where(
            Document.user_id == current_user.id,
            Document.id.in_(body.document_ids),
        )
    ).all()
    if len(docs) != len(set(body.document_ids)):
        raise HTTPException(status_code=400, detail="Invalid document_ids")

    now = datetime.utcnow()
    for doc_id in body.document_ids:
        existing_link = session.exec(
            select(DocumentMatchSetLink).where(
                DocumentMatchSetLink.set_id == item.id,
                DocumentMatchSetLink.document_id == doc_id,
            )
        ).first()
        if existing_link is not None:
            continue
        if _doc_in_any_set(session, doc_id):
            raise HTTPException(
                status_code=409,
                detail=f"Document {doc_id} is already in another set",
            )
        session.add(DocumentMatchSetLink(set_id=item.id, document_id=doc_id, created_at=now))

    item.updated_at = now
    session.add(item)
    session.commit()
    session.refresh(item)
    return _build_set_response(session, item)


@router.delete(
    "/sets/{set_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Remove document from set",
    description="Remove document from match set.",
)
def remove_document_from_set(
    set_id: UUID,
    document_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    item = _set_or_404(session, set_id, current_user.id)
    link = session.exec(
        select(DocumentMatchSetLink).where(
            DocumentMatchSetLink.set_id == item.id,
            DocumentMatchSetLink.document_id == document_id,
        )
    ).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Document is not in this set")

    session.delete(link)
    item.updated_at = datetime.utcnow()
    session.add(item)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/unmatched",
    response_model=list[MatchSetDocumentResponse],
    summary="List unmatched documents",
    description="Documents not in any match set.",
)
def list_unmatched(
    limit: int = 200,
    offset: int = 0,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[MatchSetDocumentResponse]:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    linked_doc_ids = session.exec(select(DocumentMatchSetLink.document_id)).all()
    stmt = select(Document).where(Document.user_id == current_user.id)
    if linked_doc_ids:
        stmt = stmt.where(Document.id.notin_(linked_doc_ids))
    docs = session.exec(
        stmt.order_by(Document.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return [MatchSetDocumentResponse.model_validate(d, from_attributes=True) for d in docs]


@router.post(
    "/auto-match",
    response_model=AutoMatchResponse,
    summary="Auto-match documents",
    description="Apply enabled rules to unmatched documents; create sets for pairs.",
)
def auto_match(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AutoMatchResponse:
    rules = session.exec(
        select(MatchingRule)
        .where(MatchingRule.user_id == current_user.id, MatchingRule.enabled.is_(True))
        .order_by(MatchingRule.updated_at.desc())
    ).all()
    if not rules:
        return AutoMatchResponse(created_sets=0, matched_pairs=[])

    linked_doc_ids = session.exec(select(DocumentMatchSetLink.document_id)).all()
    doc_stmt = select(Document).where(Document.user_id == current_user.id)
    if linked_doc_ids:
        doc_stmt = doc_stmt.where(Document.id.notin_(linked_doc_ids))
    docs = session.exec(doc_stmt.order_by(Document.created_at.asc())).all()
    if len(docs) < 2:
        return AutoMatchResponse(created_sets=0, matched_pairs=[])

    fields = session.exec(
        select(ExtractedField).where(ExtractedField.document_id.in_([d.id for d in docs]))
    ).all()
    by_doc: dict[UUID, dict[str, str | None]] = {}
    for f in fields:
        by_doc.setdefault(f.document_id, {})[f.field_name] = f.field_value

    consumed_docs: set[UUID] = set()
    created_sets = 0
    matched_pairs: list[AutoMatchPairItem] = []
    now = datetime.utcnow()

    for rule in rules:
        cond_rows = session.exec(
            select(MatchingRuleCondition)
            .where(MatchingRuleCondition.rule_id == rule.id)
            .order_by(MatchingRuleCondition.sort_order.asc())
        ).all()
        conditions = [
            RuleCondition(left_field=c.left_field, operator=c.operator, right_field=c.right_field)
            for c in cond_rows
        ]
        if not conditions:
            continue

        allowed_doc_types = {x.strip().lower() for x in (rule.doc_types or []) if x.strip()}
        candidates = [
            d
            for d in docs
            if d.id not in consumed_docs
            and (not allowed_doc_types or d.type.strip().lower() in allowed_doc_types)
        ]

        for left, right in combinations(candidates, 2):
            if left.id in consumed_docs or right.id in consumed_docs:
                continue

            if evaluate_pair(by_doc.get(left.id, {}), by_doc.get(right.id, {}), conditions):
                set_item = DocumentMatchSet(
                    user_id=current_user.id,
                    name=f"Auto Match {left.name} + {right.name}",
                    status="review",
                    source="auto",
                    rule_id=rule.id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(set_item)
                session.commit()
                session.refresh(set_item)
                session.add(
                    DocumentMatchSetLink(
                        set_id=set_item.id,
                        document_id=left.id,
                        created_at=now,
                    )
                )
                session.add(
                    DocumentMatchSetLink(
                        set_id=set_item.id,
                        document_id=right.id,
                        created_at=now,
                    )
                )
                session.commit()

                consumed_docs.add(left.id)
                consumed_docs.add(right.id)
                created_sets += 1
                matched_pairs.append(
                    AutoMatchPairItem(
                        set_id=set_item.id,
                        rule_id=rule.id,
                        left_document_id=left.id,
                        right_document_id=right.id,
                    )
                )

    return AutoMatchResponse(created_sets=created_sets, matched_pairs=matched_pairs)
