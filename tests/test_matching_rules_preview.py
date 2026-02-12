from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.deps import get_current_user
from app.db.session import get_session
from app.main import app
from app.models import Document, ExtractedField, User

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


def _seed_docs_and_fields(user: User):
    with Session(engine) as session:
        d1 = Document(
            user_id=user.id,
            name="A",
            type="invoice",
            status="scanned",
            file_path="a.pdf",
            file_size=1,
            mime_type="application/pdf",
            pages=1,
            confidence=95,
            scanned_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        d2 = Document(
            user_id=user.id,
            name="B",
            type="invoice",
            status="scanned",
            file_path="b.pdf",
            file_size=1,
            mime_type="application/pdf",
            pages=1,
            confidence=94,
            scanned_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        d3 = Document(
            user_id=user.id,
            name="C",
            type="receipt",
            status="scanned",
            file_path="c.pdf",
            file_size=1,
            mime_type="application/pdf",
            pages=1,
            confidence=91,
            scanned_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(d1)
        session.add(d2)
        session.add(d3)
        session.commit()
        session.refresh(d1)
        session.refresh(d2)
        session.refresh(d3)

        for doc, inv_no in [(d1, "INV-001"), (d2, "INV-001"), (d3, "RCPT-9")]:
            session.add(
                ExtractedField(
                    document_id=doc.id,
                    page_id=None,
                    page_number=1,
                    field_name="invoice_number",
                    field_value=inv_no,
                    confidence=99,
                    bbox_x=None,
                    bbox_y=None,
                    bbox_width=None,
                    bbox_height=None,
                    is_edited=False,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
        session.commit()
        return str(d1.id), str(d2.id), str(d3.id)


def test_matching_rule_test_returns_preview_metadata(client, current_user):
    d1_id, d2_id, d3_id = _seed_docs_and_fields(current_user)

    create = client.post(
        "/matching/rules",
        json={
            "name": "Invoice Number Rule",
            "description": "match invoice number",
            "enabled": True,
            "doc_types": ["invoice"],
            "conditions": [
                {
                    "left_field": "invoice_number",
                    "operator": "equals",
                    "right_field": "invoice_number",
                    "sort_order": 0,
                }
            ],
            "fields": [],
        },
    )
    assert create.status_code == 201
    rule_id = create.json()["id"]

    test = client.post(
        f"/matching/rules/{rule_id}/test",
        json={"document_ids": [d1_id, d2_id, d3_id]},
    )
    assert test.status_code == 200
    body = test.json()

    assert body["evaluated_pairs"] == 1
    assert body["matched_pairs"] == 1
    assert body["skipped_pairs"] == 2
    assert body["applied_doc_types"] == ["invoice"]
    assert len(body["matches"]) == 1
    assert body["matches"][0]["left_name"] in {"A", "B"}
