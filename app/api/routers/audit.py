from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models import AuditLog, User
from app.schemas import AuditLogResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=list[AuditLogResponse])
def list_audit_logs(
    action: str | None = None,
    entity_type: str | None = None,
    document_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[AuditLog]:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    stmt = select(AuditLog)

    # Non-admin users can only view their own logs.
    if (current_user.role or "").lower() != "admin":
        stmt = stmt.where(AuditLog.actor_user_id == current_user.id)
    else:
        if actor_user_id is not None:
            stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)

    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if document_id is not None:
        stmt = stmt.where(AuditLog.document_id == document_id)

    if date_from:
        try:
            from_dt = datetime.fromisoformat(
                f"{date_from}T00:00:00" if len(date_from) == 10 else date_from
            )
            stmt = stmt.where(AuditLog.created_at >= from_dt)
        except ValueError:
            pass

    if date_to:
        try:
            to_dt = datetime.fromisoformat(
                f"{date_to}T23:59:59" if len(date_to) == 10 else date_to
            )
            stmt = stmt.where(AuditLog.created_at <= to_dt)
        except ValueError:
            pass

    stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    return list(session.exec(stmt).all())
