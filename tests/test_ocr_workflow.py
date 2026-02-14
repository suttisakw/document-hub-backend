from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.deps import get_current_user
from app.db.session import get_session
from app.main import app
from app.models import Document, OcrJob, User

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
def current_user():
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


def _seed_doc_and_jobs(user: User) -> tuple[UUID, OcrJob, OcrJob, OcrJob]:
    with Session(engine) as session:
        doc = Document(
            user_id=user.id,
            name="invoice-a",
            type="invoice",
            status="processing",
            file_path="docs/a.pdf",
            file_size=100,
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

        running = OcrJob(
            document_id=doc.id,
            provider="easyocr",
            status="running",
            requested_at=datetime.now(UTC),
        )
        completed = OcrJob(
            document_id=doc.id,
            provider="external",
            status="completed",
            requested_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            result_json={"ok": True},
        )
        failed = OcrJob(
            document_id=doc.id,
            provider="external",
            status="error",
            requested_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            error_message="bad file",
        )
        session.add(running)
        session.add(completed)
        session.add(failed)
        session.commit()
        session.refresh(running)
        session.refresh(completed)
        session.refresh(failed)
        return doc.id, running, completed, failed


def test_cancel_job_updates_status_and_document(client, current_user):
    doc_id, running, _, _ = _seed_doc_and_jobs(current_user)

    res = client.post(f"/ocr/jobs/{running.id}/cancel")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "cancelled"
    assert body["error_message"] == "Cancelled by user"

    with Session(engine) as session:
        db_doc = session.exec(select(Document).where(Document.id == doc_id)).first()
        assert db_doc is not None
        assert db_doc.status == "pending"


def test_history_returns_terminal_jobs_only(client, current_user):
    _, running, completed, failed = _seed_doc_and_jobs(current_user)

    res = client.get("/ocr/jobs/history?limit=50&offset=0")
    assert res.status_code == 200
    jobs = res.json()
    ids = {j["id"] for j in jobs}
    assert str(completed.id) in ids
    assert str(failed.id) in ids
    assert str(running.id) not in ids


def test_get_job_result_returns_payload(client, current_user):
    _, _, completed, _ = _seed_doc_and_jobs(current_user)

    res = client.get(f"/ocr/jobs/{completed.id}/result")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["result_json"] == {"ok": True}


def test_cancel_terminal_job_rejected(client, current_user):
    _, _, completed, _ = _seed_doc_and_jobs(current_user)
    res = client.post(f"/ocr/jobs/{completed.id}/cancel")
    assert res.status_code == 400


def test_run_easyocr_enqueues_pending_job(client, current_user):
    with Session(engine) as session:
        doc = Document(
            user_id=current_user.id,
            name="invoice-b",
            type="invoice",
            status="pending",
            file_path="docs/b.pdf",
            file_size=200,
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

    res = client.post(f"/ocr/run/easyocr/{doc.id}")
    assert res.status_code == 200
    body = res.json()
    assert body["provider"] == "easyocr"
    assert body["status"] in {"pending", "running"}

    with Session(engine) as session:
        db_doc = session.exec(select(Document).where(Document.id == doc.id)).first()
        assert db_doc is not None
        assert db_doc.status == "processing"


def test_ocr_ops_queue_stats_endpoint(client):
    res = client.get("/ocr/ops/queue/stats")
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"queue_depth", "delayed_depth", "dlq_depth"}


def test_ocr_ops_dlq_endpoints(client):
    list_res = client.get("/ocr/ops/dlq?limit=10")
    assert list_res.status_code == 200
    assert isinstance(list_res.json(), list)

    history_res = client.get("/ocr/ops/requeue-history?limit=10")
    assert history_res.status_code == 200
    assert isinstance(history_res.json(), list)

    requeue_res = client.post(
        "/ocr/ops/dlq/requeue/00000000-0000-0000-0000-000000000000"
    )
    assert requeue_res.status_code == 200
    body = requeue_res.json()
    assert body["ok"] is False

    purge_one = client.delete(
        "/ocr/ops/dlq/00000000-0000-0000-0000-000000000000"
    )
    assert purge_one.status_code == 200
    purge_one_body = purge_one.json()
    assert purge_one_body["ok"] is False

    purge_all = client.delete("/ocr/ops/dlq")
    assert purge_all.status_code == 200
    purge_all_body = purge_all.json()
    assert purge_all_body["ok"] is True
