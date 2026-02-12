from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_session
from app.main import app
from app.models import Document, User

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
def storage_dir(tmp_path):
    old = settings.storage_dir
    settings.storage_dir = str(tmp_path)
    yield tmp_path
    settings.storage_dir = old


@pytest.fixture
def current_user(storage_dir):
    with Session(engine) as session:
        user = User(
            email="owner@example.com",
            name="Owner",
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


def _create_document_with_file(user: User, filename: str, content: bytes) -> Document:
    with Session(engine) as session:
        doc = Document(
            user_id=user.id,
            name=filename,
            type="invoice",
            status="pending",
            file_path=f"docs/{uuid4()}_{filename}",
            file_size=len(content),
            mime_type="application/pdf",
            pages=1,
            confidence=None,
            scanned_at=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

    # write file to test storage
    from pathlib import Path

    abs_path = Path(settings.storage_dir) / doc.file_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(content)
    return doc


def test_export_documents_zip_returns_archive_with_counts(client, current_user):
    doc1 = _create_document_with_file(current_user, "invoice-a.pdf", b"AAA")
    doc2 = _create_document_with_file(current_user, "invoice-b.pdf", b"BBB")

    response = client.post(
        "/documents/export",
        json={"document_ids": [str(doc1.id), str(doc2.id)]},
    )

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/zip")
    assert response.headers.get("x-requested-count") == "2"
    assert response.headers.get("x-exported-count") == "2"

    with ZipFile(BytesIO(response.content), "r") as zf:
        names = zf.namelist()
        assert len(names) == 2
        assert any(str(doc1.id) in n for n in names)
        assert any(str(doc2.id) in n for n in names)
        body = zf.read(names[0])
        assert body in {b"AAA", b"BBB"}


def test_bulk_delete_flow_mixed_success_and_failure(client, current_user):
    doc1 = _create_document_with_file(current_user, "doc-1.pdf", b"111")
    doc2 = _create_document_with_file(current_user, "doc-2.pdf", b"222")

    ids = [str(doc1.id), str(uuid4()), str(doc2.id)]
    success = 0
    failed = 0
    for doc_id in ids:
        res = client.delete(f"/documents/{doc_id}")
        if res.status_code == 204:
            success += 1
        else:
            failed += 1

    assert success == 2
    assert failed == 1

    remaining = client.get("/documents/?limit=50&offset=0")
    assert remaining.status_code == 200
    body = remaining.json()
    assert body["items"] == []
    assert body["total"] == 0

    with Session(engine) as session:
        total = len(session.exec(select(Document)).all())
        assert total == 0
