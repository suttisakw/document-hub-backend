from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_session
from app.main import app
from app.models import User

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def override_get_session():
    with Session(engine) as session:
        yield session


@pytest.fixture(autouse=True)
def reset_db():
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


@pytest.fixture
def storage_env(tmp_path):
    old_provider = settings.storage_provider
    old_dir = settings.storage_dir
    settings.storage_provider = "local"
    settings.storage_dir = str(tmp_path)
    yield tmp_path
    settings.storage_provider = old_provider
    settings.storage_dir = old_dir


@pytest.fixture
def current_user(storage_env):
    with Session(engine) as session:
        user = User(
            email="storage-owner@example.com",
            name="Storage Owner",
            password_hash="x",
            role="admin",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.clear()


@pytest.fixture
def client(current_user):
    return TestClient(app)


def test_storage_status_endpoint(client):
    response = client.get("/settings/storage")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "local"
    assert body["healthy"] is True
    assert body["details"]["provider"] == "local"
    assert "storage_dir" in body["details"]


def test_storage_test_connection_endpoint(client):
    response = client.post("/settings/storage/test")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "local"
    assert body["ok"] is True
    assert body["message"] is None
