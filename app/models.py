from datetime import UTC, datetime
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship, SQLModel


def _utc_now() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    email: str = Field(unique=True, index=True, nullable=False)
    name: str
    password_hash: str
    role: str = Field(default="viewer", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    documents: List["Document"] = Relationship(back_populates="user")


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    category_id: UUID | None = Field(
        default=None, foreign_key="document_categories.id", index=True
    )
    name: str
    type: str = Field(index=True)  # e.g. Invoice/Receipt/etc
    status: str = Field(default="pending", index=True)
    file_path: str
    file_size: int
    mime_type: str | None = None
    pages: int = 1
    confidence: float | None = None
    scanned_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    user: "User" = Relationship(back_populates="documents")
    pages_list: List["DocumentPage"] = Relationship(back_populates="document")
    extracted_fields: List["ExtractedField"] = Relationship(back_populates="document")


class DocumentPage(SQLModel, table=True):
    __tablename__ = "document_pages"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    document_id: UUID = Field(foreign_key="documents.id", index=True)
    page_number: int
    image_path: str | None = None
    width: int | None = None
    height: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    document: "Document" = Relationship(back_populates="pages_list")
    extracted_fields: List["ExtractedField"] = Relationship(back_populates="page")


class ExtractedField(SQLModel, table=True):
    __tablename__ = "extracted_fields"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    document_id: UUID = Field(foreign_key="documents.id", index=True)
    page_id: UUID | None = Field(default=None, foreign_key="document_pages.id")
    page_number: int | None = Field(default=None, index=True)
    field_name: str
    field_value: str | None = None
    confidence: float | None = None
    bbox_x: float | None = None
    bbox_y: float | None = None
    bbox_width: float | None = None
    bbox_height: float | None = None
    is_edited: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    document: "Document" = Relationship(back_populates="extracted_fields")
    page: Optional["DocumentPage"] = Relationship(back_populates="extracted_fields")


class OcrJob(SQLModel, table=True):
    __tablename__ = "ocr_jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    document_id: UUID = Field(foreign_key="documents.id", index=True)

    provider: str = Field(index=True)  # "easyocr" | "external"
    status: str = Field(
        default="pending", index=True
    )  # pending|triggered|running|completed|error
    external_job_id: str | None = Field(default=None, index=True)
    interface_id: UUID | None = Field(default=None, index=True)
    transaction_id: UUID | None = Field(default=None, index=True)
    request_id: int | None = Field(default=None, index=True)

    requested_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    error_message: str | None = None
    result_json: dict | None = Field(default=None, sa_column=Column(JSON))


class ExternalOcrInterface(SQLModel, table=True):
    __tablename__ = "external_ocr_interfaces"

    id: UUID = Field(primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)

    name: str
    trigger_url: str
    api_key: str | None = None
    webhook_secret: str | None = None
    enabled: bool = True
    is_default: bool = False

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    created_at: datetime = Field(default_factory=_utc_now, index=True)

    actor_user_id: UUID = Field(foreign_key="users.id", index=True)
    actor_email: str | None = None
    actor_role: str | None = None

    action: str = Field(index=True)
    entity_type: str = Field(index=True)
    entity_id: UUID | None = Field(default=None, index=True)
    document_id: UUID | None = Field(default=None, index=True)

    ip: str | None = None
    user_agent: str | None = None

    meta: dict | None = Field(default=None, sa_column=Column(JSON))


class DocumentCategory(SQLModel, table=True):
    __tablename__ = "document_categories"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    key: str = Field(index=True)  # e.g. invoice, receipt
    name: str
    description: str | None = None
    color: str | None = None
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Tag(SQLModel, table=True):
    __tablename__ = "tags"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    name: str = Field(index=True)
    color: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentTagLink(SQLModel, table=True):
    __tablename__ = "document_tag_links"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    document_id: UUID = Field(foreign_key="documents.id", index=True)
    tag_id: UUID = Field(foreign_key="tags.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentGroup(SQLModel, table=True):
    __tablename__ = "document_groups"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    name: str
    description: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentGroupLink(SQLModel, table=True):
    __tablename__ = "document_group_links"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    group_id: UUID = Field(foreign_key="document_groups.id", index=True)
    document_id: UUID = Field(foreign_key="documents.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentMatchSet(SQLModel, table=True):
    __tablename__ = "document_match_sets"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    name: str
    status: str = Field(default="review", index=True)  # complete|partial|review
    source: str = Field(default="manual", index=True)  # manual|auto
    rule_id: UUID | None = Field(default=None, foreign_key="matching_rules.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentMatchSetLink(SQLModel, table=True):
    __tablename__ = "document_match_set_links"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    set_id: UUID = Field(foreign_key="document_match_sets.id", index=True)
    document_id: UUID = Field(foreign_key="documents.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MatchingRule(SQLModel, table=True):
    __tablename__ = "matching_rules"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    name: str
    description: str | None = None
    enabled: bool = Field(default=True, index=True)
    doc_types: list[str] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MatchingRuleCondition(SQLModel, table=True):
    __tablename__ = "matching_rule_conditions"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    rule_id: UUID = Field(foreign_key="matching_rules.id", index=True)
    left_field: str
    operator: str = Field(default="equals", index=True)
    right_field: str
    sort_order: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MatchingRuleField(SQLModel, table=True):
    __tablename__ = "matching_rule_fields"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    rule_id: UUID = Field(foreign_key="matching_rules.id", index=True)
    name: str
    field_type: str = Field(default="text")
    required: bool = False
    sort_order: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OcrTemplate(SQLModel, table=True):
    __tablename__ = "ocr_templates"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    name: str
    doc_type: str = Field(index=True)
    description: str | None = None
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OcrTemplateZone(SQLModel, table=True):
    __tablename__ = "ocr_template_zones"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    template_id: UUID = Field(foreign_key="ocr_templates.id", index=True)
    page_number: int = 1
    label: str
    field_type: str = Field(default="text")
    x: float
    y: float
    width: float
    height: float
    required: bool = False
    sort_order: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
