from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Request
from sqlmodel import Session

from app.models import AuditLog, User


def get_request_ip(req: Request | None) -> str | None:
    if req is None:
        return None
    if req.client is None:
        return None
    return req.client.host


def get_user_agent(req: Request | None) -> str | None:
    if req is None:
        return None
    return req.headers.get("user-agent")


def write_audit_log(
    *,
    session: Session,
    actor: User,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    document_id: UUID | None = None,
    request: Request | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_user_id=actor.id,
            actor_email=actor.email,
            actor_role=getattr(actor, "role", None),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            document_id=document_id,
            ip=get_request_ip(request),
            user_agent=get_user_agent(request),
            meta=meta,
        )
    )
