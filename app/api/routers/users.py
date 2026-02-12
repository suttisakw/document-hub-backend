from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from app.api.deps import require_admin
from app.core.security import get_password_hash
from app.db.session import get_session
from app.models import User
from app.schemas import AdminUserCreate, AdminUserUpdate, UserResponse

router = APIRouter(prefix="/admin/users", tags=["users"])


@router.get("/", response_model=list[UserResponse])
def list_users(
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
) -> list[User]:
    users = session.exec(select(User).order_by(User.created_at.desc())).all()
    return list(users)


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    body: AdminUserCreate,
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
) -> User:
    existing = session.exec(select(User).where(User.email == body.email)).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    now = datetime.utcnow()
    user = User(
        email=body.email,
        name=body.name,
        password_hash=get_password_hash(body.password),
        role=body.role,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    body: AdminUserUpdate,
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
) -> User:
    user = session.exec(select(User).where(User.id == user_id)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    changed = False
    if body.name is not None:
        user.name = body.name
        changed = True
    if body.role is not None:
        user.role = body.role
        changed = True
    if body.password is not None:
        user.password_hash = get_password_hash(body.password)
        changed = True

    if changed:
        user.updated_at = datetime.utcnow()
        session.add(user)
        session.commit()
        session.refresh(user)

    return user


@router.delete(
    "/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
def delete_user(
    user_id: UUID,
    session: Session = Depends(get_session),
    current_admin: User = Depends(require_admin),
) -> Response:
    if current_admin.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own user")

    user = session.exec(select(User).where(User.id == user_id)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    session.delete(user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
