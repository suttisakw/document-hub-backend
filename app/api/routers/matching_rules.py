from __future__ import annotations

from datetime import UTC, datetime
from itertools import combinations
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models import (
    Document,
    ExtractedField,
    MatchingRule,
    MatchingRuleCondition,
    MatchingRuleField,
    User,
)
from app.schemas import (
    MatchingRuleCreate,
    MatchingRuleResponse,
    MatchingRuleTestMatch,
    MatchingRuleTestRequest,
    MatchingRuleTestResponse,
    MatchingRuleUpdate,
)
from app.services.matching_engine import RuleCondition, evaluate_pair

router = APIRouter(prefix="/matching/rules", tags=["matching-rules"])


def _get_rule_or_404(session: Session, user_id: UUID, rule_id: UUID) -> MatchingRule:
    rule = session.exec(
        select(MatchingRule).where(MatchingRule.id == rule_id, MatchingRule.user_id == user_id)
    ).first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Matching rule not found")
    return rule


def _build_rule_response(session: Session, rule: MatchingRule) -> MatchingRuleResponse:
    conditions = session.exec(
        select(MatchingRuleCondition)
        .where(MatchingRuleCondition.rule_id == rule.id)
        .order_by(MatchingRuleCondition.sort_order.asc(), MatchingRuleCondition.created_at.asc())
    ).all()
    fields = session.exec(
        select(MatchingRuleField)
        .where(MatchingRuleField.rule_id == rule.id)
        .order_by(MatchingRuleField.sort_order.asc(), MatchingRuleField.created_at.asc())
    ).all()
    return MatchingRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        enabled=rule.enabled,
        doc_types=list(rule.doc_types or []),
        created_at=rule.created_at,
        updated_at=rule.updated_at,
        conditions=list(conditions),
        fields=list(fields),
    )


def _replace_nested(
    session: Session,
    rule_id: UUID,
    body: MatchingRuleCreate | MatchingRuleUpdate,
    *,
    replace_conditions: bool,
    replace_fields: bool,
) -> None:
    now = datetime.now(UTC)
    if replace_conditions:
        session.exec(delete(MatchingRuleCondition).where(MatchingRuleCondition.rule_id == rule_id))
        for idx, cond in enumerate(body.conditions or []):
            session.add(
                MatchingRuleCondition(
                    rule_id=rule_id,
                    left_field=cond.left_field,
                    operator=cond.operator,
                    right_field=cond.right_field,
                    sort_order=cond.sort_order if cond.sort_order is not None else idx,
                    created_at=now,
                    updated_at=now,
                )
            )

    if replace_fields:
        session.exec(delete(MatchingRuleField).where(MatchingRuleField.rule_id == rule_id))
        for idx, field in enumerate(body.fields or []):
            session.add(
                MatchingRuleField(
                    rule_id=rule_id,
                    name=field.name,
                    field_type=field.field_type,
                    required=field.required,
                    sort_order=field.sort_order if field.sort_order is not None else idx,
                    created_at=now,
                    updated_at=now,
                )
            )


@router.get("", response_model=list[MatchingRuleResponse])
def list_rules(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[MatchingRuleResponse]:
    rules = session.exec(
        select(MatchingRule)
        .where(MatchingRule.user_id == current_user.id)
        .order_by(MatchingRule.updated_at.desc())
    ).all()
    return [_build_rule_response(session, r) for r in rules]


@router.post("", response_model=MatchingRuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(
    body: MatchingRuleCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> MatchingRuleResponse:
    now = datetime.now(UTC)
    rule = MatchingRule(
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        enabled=body.enabled,
        doc_types=body.doc_types,
        created_at=now,
        updated_at=now,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)

    _replace_nested(
        session,
        rule.id,
        body,
        replace_conditions=True,
        replace_fields=True,
    )
    session.commit()
    return _build_rule_response(session, rule)


@router.get("/{rule_id}", response_model=MatchingRuleResponse)
def get_rule(
    rule_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> MatchingRuleResponse:
    rule = _get_rule_or_404(session, current_user.id, rule_id)
    return _build_rule_response(session, rule)


@router.patch("/{rule_id}", response_model=MatchingRuleResponse)
def update_rule(
    rule_id: UUID,
    body: MatchingRuleUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> MatchingRuleResponse:
    rule = _get_rule_or_404(session, current_user.id, rule_id)
    changed = False

    if body.name is not None:
        rule.name = body.name
        changed = True
    if body.description is not None:
        rule.description = body.description
        changed = True
    if body.enabled is not None:
        rule.enabled = body.enabled
        changed = True
    if body.doc_types is not None:
        rule.doc_types = body.doc_types
        changed = True

    if changed:
        rule.updated_at = datetime.now(UTC)
        session.add(rule)

    _replace_nested(
        session,
        rule.id,
        body,
        replace_conditions=body.conditions is not None,
        replace_fields=body.fields is not None,
    )
    session.commit()
    session.refresh(rule)
    return _build_rule_response(session, rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_rule(
    rule_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    rule = _get_rule_or_404(session, current_user.id, rule_id)
    session.exec(delete(MatchingRuleCondition).where(MatchingRuleCondition.rule_id == rule.id))
    session.exec(delete(MatchingRuleField).where(MatchingRuleField.rule_id == rule.id))
    session.delete(rule)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{rule_id}/enable", response_model=MatchingRuleResponse)
def enable_rule(
    rule_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> MatchingRuleResponse:
    rule = _get_rule_or_404(session, current_user.id, rule_id)
    rule.enabled = True
    rule.updated_at = datetime.now(UTC)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return _build_rule_response(session, rule)


@router.post("/{rule_id}/disable", response_model=MatchingRuleResponse)
def disable_rule(
    rule_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> MatchingRuleResponse:
    rule = _get_rule_or_404(session, current_user.id, rule_id)
    rule.enabled = False
    rule.updated_at = datetime.now(UTC)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return _build_rule_response(session, rule)


@router.post("/{rule_id}/test", response_model=MatchingRuleTestResponse)
def test_rule(
    rule_id: UUID,
    body: MatchingRuleTestRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> MatchingRuleTestResponse:
    rule = _get_rule_or_404(session, current_user.id, rule_id)
    if not body.document_ids:
        return MatchingRuleTestResponse(matches=[])

    docs = session.exec(
        select(Document).where(
            Document.user_id == current_user.id,
            Document.id.in_(body.document_ids),
        )
    ).all()
    if len(docs) < 2:
        return MatchingRuleTestResponse(matches=[])

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
        return MatchingRuleTestResponse(matches=[])

    fields = session.exec(
        select(ExtractedField).where(ExtractedField.document_id.in_([d.id for d in docs]))
    ).all()
    fields_by_doc: dict[UUID, dict[str, str | None]] = {}
    for f in fields:
        fields_by_doc.setdefault(f.document_id, {})[f.field_name] = f.field_value

    allowed_doc_types = {x.strip().lower() for x in (rule.doc_types or []) if x.strip()}

    out: list[MatchingRuleTestMatch] = []
    evaluated_pairs = 0
    skipped_pairs = 0
    for left, right in combinations(docs, 2):
        if allowed_doc_types and (
            left.type.lower() not in allowed_doc_types
            or right.type.lower() not in allowed_doc_types
        ):
            skipped_pairs += 1
            continue
        evaluated_pairs += 1
        if evaluate_pair(
            fields_by_doc.get(left.id, {}),
            fields_by_doc.get(right.id, {}),
            conditions,
        ):
            out.append(
                MatchingRuleTestMatch(
                    left_document_id=left.id,
                    right_document_id=right.id,
                    left_name=left.name,
                    right_name=right.name,
                )
            )

    return MatchingRuleTestResponse(
        matches=out,
        evaluated_pairs=evaluated_pairs,
        matched_pairs=len(out),
        skipped_pairs=skipped_pairs,
        applied_doc_types=sorted(allowed_doc_types),
    )
