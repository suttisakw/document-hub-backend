from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models import ExternalOcrInterface, User
from app.schemas import (
    ExternalOcrInterfaceCreate,
    ExternalOcrInterfaceResponse,
    ExternalOcrInterfaceUpdate,
    StorageConnectionTestResponse,
    StorageStatusResponse,
)
from app.services.storage import (
    StorageConfigurationError,
    StorageError,
    get_storage,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get(
    "/storage",
    response_model=StorageStatusResponse,
    summary="Storage status",
    description="Current storage provider and health.",
)
def get_storage_status(
    current_user: User = Depends(get_current_user),
) -> StorageStatusResponse:
    _ = current_user
    try:
        storage = get_storage()
        healthy, message = storage.healthcheck(perform_write=False)
        return StorageStatusResponse(
            provider=storage.provider,
            healthy=healthy,
            message=message,
            details=storage.describe(),
        )
    except StorageConfigurationError as e:
        return StorageStatusResponse(
            provider="unknown",
            healthy=False,
            message=str(e),
            details={},
        )


@router.post(
    "/storage/test",
    response_model=StorageConnectionTestResponse,
    summary="Test storage connection",
    description="Healthcheck with write test.",
)
def test_storage_connection(
    current_user: User = Depends(get_current_user),
) -> StorageConnectionTestResponse:
    _ = current_user
    try:
        storage = get_storage()
        ok, message = storage.healthcheck(perform_write=True)
        return StorageConnectionTestResponse(
            provider=storage.provider,
            ok=ok,
            message=message,
        )
    except (StorageConfigurationError, StorageError) as e:
        return StorageConnectionTestResponse(provider="unknown", ok=False, message=str(e))


@router.get(
    "/external-ocr",
    response_model=list[ExternalOcrInterfaceResponse],
    summary="List external OCR interfaces",
    description="User's external OCR interface configs.",
)
def list_external_ocr_interfaces(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ExternalOcrInterfaceResponse]:
    items = session.exec(
        select(ExternalOcrInterface)
        .where(ExternalOcrInterface.user_id == current_user.id)
        .order_by(ExternalOcrInterface.created_at.desc())
    ).all()

    return [ExternalOcrInterfaceResponse.from_model(i) for i in items]


@router.post(
    "/external-ocr",
    response_model=ExternalOcrInterfaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create external OCR interface",
    description="Register a new external OCR interface.",
)
def create_external_ocr_interface(
    body: ExternalOcrInterfaceCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ExternalOcrInterfaceResponse:
    existing = session.exec(
        select(ExternalOcrInterface).where(
            ExternalOcrInterface.user_id == current_user.id,
            ExternalOcrInterface.id == body.interface_id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Interface already exists")

    now = datetime.utcnow()
    item = ExternalOcrInterface(
        id=body.interface_id,
        user_id=current_user.id,
        name=body.name,
        trigger_url=body.trigger_url,
        api_key=body.api_key,
        webhook_secret=body.webhook_secret,
        enabled=body.enabled,
        is_default=body.is_default,
        created_at=now,
        updated_at=now,
    )

    if body.is_default:
        others = session.exec(
            select(ExternalOcrInterface).where(
                ExternalOcrInterface.user_id == current_user.id,
                ExternalOcrInterface.id != body.interface_id,
            )
        ).all()
        for o in others:
            o.is_default = False
            o.updated_at = now
            session.add(o)

    session.add(item)
    session.commit()
    session.refresh(item)
    return ExternalOcrInterfaceResponse.from_model(item)


@router.patch(
    "/external-ocr/{interface_id}",
    response_model=ExternalOcrInterfaceResponse,
    summary="Update external OCR interface",
    description="Update name, URL, enabled, is_default, secrets.",
)
def update_external_ocr_interface(
    interface_id: UUID,
    body: ExternalOcrInterfaceUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ExternalOcrInterfaceResponse:
    item = session.exec(
        select(ExternalOcrInterface).where(
            ExternalOcrInterface.user_id == current_user.id,
            ExternalOcrInterface.id == interface_id,
        )
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Interface not found")

    changed = False
    if body.name is not None:
        item.name = body.name
        changed = True
    if body.trigger_url is not None:
        item.trigger_url = body.trigger_url
        changed = True
    if body.enabled is not None:
        item.enabled = body.enabled
        changed = True

    if body.is_default is not None:
        item.is_default = body.is_default
        changed = True

    # Secrets: only update when provided (can clear by sending empty string)
    if body.api_key is not None:
        item.api_key = body.api_key or None
        changed = True
    if body.webhook_secret is not None:
        item.webhook_secret = body.webhook_secret or None
        changed = True

    if changed:
        item.updated_at = datetime.utcnow()

        if item.is_default:
            others = session.exec(
                select(ExternalOcrInterface).where(
                    ExternalOcrInterface.user_id == current_user.id,
                    ExternalOcrInterface.id != item.id,
                )
            ).all()
            for o in others:
                if o.is_default:
                    o.is_default = False
                    o.updated_at = item.updated_at
                    session.add(o)

        session.add(item)
        session.commit()
        session.refresh(item)

    return ExternalOcrInterfaceResponse.from_model(item)


@router.delete(
    "/external-ocr/{interface_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete external OCR interface",
    description="Remove interface config.",
)
def delete_external_ocr_interface(
    interface_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    item = session.exec(
        select(ExternalOcrInterface).where(
            ExternalOcrInterface.user_id == current_user.id,
            ExternalOcrInterface.id == interface_id,
        )
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Interface not found")

    session.delete(item)
    session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
