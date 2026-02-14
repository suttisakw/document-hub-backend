from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.config import settings
from app.models import Document, OcrJob, User
from app.services.ocr_queue import process_easyocr_job
from app.services.storage import get_storage

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@pytest.fixture(autouse=True)
def reset_db(tmp_path):
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    old_provider = settings.storage_provider
    old_dir = settings.storage_dir
    old_max_attempts = settings.ocr_queue_max_attempts
    old_retry_base = settings.ocr_queue_retry_base_seconds
    old_retry_max = settings.ocr_queue_retry_max_seconds

    settings.storage_provider = "local"
    settings.storage_dir = str(tmp_path)
    settings.ocr_queue_max_attempts = 2
    settings.ocr_queue_retry_base_seconds = 1
    settings.ocr_queue_retry_max_seconds = 2

    yield

    settings.storage_provider = old_provider
    settings.storage_dir = old_dir
    settings.ocr_queue_max_attempts = old_max_attempts
    settings.ocr_queue_retry_base_seconds = old_retry_base
    settings.ocr_queue_retry_max_seconds = old_retry_max


def _seed_running_job() -> OcrJob:
    with Session(engine) as session:
        user = User(
            email="retry-owner@example.com",
            name="Retry Owner",
            password_hash="x",
            role="admin",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        doc = Document(
            user_id=user.id,
            name="retry-invoice",
            type="invoice",
            status="processing",
            file_path="retry/invoice.png",
            file_size=5,
            mime_type="image/png",
            pages=1,
            confidence=None,
            scanned_at=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

        storage = get_storage()
        storage.save_bytes(doc.file_path, b"dummy")

        job = OcrJob(
            document_id=doc.id,
            provider="easyocr",
            status="running",
            requested_at=datetime.now(UTC),
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job


def test_easyocr_job_retries_then_moves_to_error(monkeypatch):
    job = _seed_running_job()

    def always_fail(_payload: bytes):
        raise RuntimeError("ocr crashed")

    monkeypatch.setattr("app.services.ocr_queue.run_easyocr_on_image_bytes", always_fail)

    with Session(engine) as session:
        out1 = process_easyocr_job(session=session, job_id=job.id)
        assert out1.status == "pending"
        assert out1.error_message is not None
        assert "retry scheduled" in out1.error_message

    with Session(engine) as session:
        db_job = session.exec(select(OcrJob).where(OcrJob.id == job.id)).first()
        assert db_job is not None
        db_job.status = "running"
        session.add(db_job)
        session.commit()

    with Session(engine) as session:
        out2 = process_easyocr_job(session=session, job_id=job.id)
        assert out2.status == "error"
        assert out2.error_message == "ocr crashed"
