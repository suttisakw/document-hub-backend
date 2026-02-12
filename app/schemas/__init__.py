from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr

UserRole = Literal["admin", "editor", "viewer"]


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: str | None = None


class UserBase(BaseModel):
    email: EmailStr
    name: str


class UserCreate(UserBase):
    password: str


class UserResponse(UserBase):
    id: UUID
    role: UserRole
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentBase(BaseModel):
    name: str
    type: str


class DocumentCreate(DocumentBase):
    pass


class DocumentUpdate(BaseModel):
    name: str | None = None
    type: str | None = None


class DocumentExportRequest(BaseModel):
    document_ids: list[UUID]


class DocumentResponse(DocumentBase):
    id: str
    user_id: str
    status: str
    file_path: str
    file_size: int
    mime_type: str | None = None
    pages: int
    confidence: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int


class ExtractedFieldResponse(BaseModel):
    id: str
    document_id: str
    page_number: int | None = None
    field_name: str
    field_value: str | None = None
    confidence: float | None = None
    bbox_x: float | None = None
    bbox_y: float | None = None
    bbox_width: float | None = None
    bbox_height: float | None = None
    is_edited: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentPageResponse(BaseModel):
    id: str
    page_number: int
    width: int | None = None
    height: int | None = None
    image_path: str | None = None

    model_config = {"from_attributes": True}


class DocumentDetailResponse(DocumentResponse):
    extracted_fields: list[ExtractedFieldResponse] = []
    page_images: list[DocumentPageResponse] = []


class OcrJobResponse(BaseModel):
    id: UUID
    document_id: UUID
    provider: str
    status: str
    external_job_id: str | None = None
    interface_id: UUID | None = None
    transaction_id: UUID | None = None
    request_id: int | None = None
    requested_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


class OcrJobWithDocumentResponse(OcrJobResponse):
    document_name: str
    document_type: str
    document_status: str


class OcrTriggerExternalRequest(BaseModel):
    filepath: str | None = None
    interface_id: str
    transaction_id: str


class ExternalOcrInterfaceCreate(BaseModel):
    interface_id: UUID
    name: str
    trigger_url: str
    enabled: bool = True
    is_default: bool = False
    api_key: str | None = None
    webhook_secret: str | None = None


class ExternalOcrInterfaceUpdate(BaseModel):
    name: str | None = None
    trigger_url: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None
    api_key: str | None = None
    webhook_secret: str | None = None


class ExternalOcrInterfaceResponse(BaseModel):
    interface_id: UUID
    name: str
    trigger_url: str
    enabled: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime
    has_api_key: bool
    has_webhook_secret: bool

    @classmethod
    def from_model(cls, m):
        return cls(
            interface_id=m.id,
            name=m.name,
            trigger_url=m.trigger_url,
            enabled=bool(m.enabled),
            is_default=bool(getattr(m, "is_default", False)),
            created_at=m.created_at,
            updated_at=m.updated_at,
            has_api_key=bool(m.api_key),
            has_webhook_secret=bool(m.webhook_secret),
        )


class ExtractedFieldUpdate(BaseModel):
    field_value: str | None


class AdminUserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: UserRole = "viewer"


class AdminUserUpdate(BaseModel):
    name: str | None = None
    password: str | None = None
    role: UserRole | None = None


class AuditLogResponse(BaseModel):
    id: UUID
    created_at: datetime
    actor_user_id: UUID
    actor_email: str | None = None
    actor_role: str | None = None
    action: str
    entity_type: str
    entity_id: UUID | None = None
    document_id: UUID | None = None
    ip: str | None = None
    user_agent: str | None = None
    meta: dict | None = None

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    key: str
    name: str
    description: str | None = None
    color: str | None = None
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    is_active: bool | None = None


class CategoryResponse(BaseModel):
    id: UUID
    key: str
    name: str
    description: str | None = None
    color: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CategoryStatsResponse(CategoryResponse):
    document_count: int


class TagCreate(BaseModel):
    name: str
    color: str | None = None


class TagUpdate(BaseModel):
    name: str | None = None
    color: str | None = None


class TagResponse(BaseModel):
    id: UUID
    name: str
    color: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TagStatsResponse(TagResponse):
    document_count: int


class SetCategoryRequest(BaseModel):
    category_id: UUID | None = None


class SetTagsRequest(BaseModel):
    tag_ids: list[UUID] = []


class DocumentGroupCreate(BaseModel):
    name: str
    description: str | None = None


class DocumentGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class DocumentGroupResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SetGroupDocumentsRequest(BaseModel):
    document_ids: list[UUID] = []


class DocumentMatchSetCreate(BaseModel):
    name: str
    status: str = "review"


class DocumentMatchSetUpdate(BaseModel):
    name: str | None = None
    status: str | None = None


class AddDocumentsToMatchSetRequest(BaseModel):
    document_ids: list[UUID]


class MatchSetDocumentResponse(BaseModel):
    id: UUID
    name: str
    type: str
    status: str
    confidence: float | None = None

    model_config = {"from_attributes": True}


class DocumentMatchSetResponse(BaseModel):
    id: UUID
    name: str
    status: str
    source: str
    rule_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    documents: list[MatchSetDocumentResponse] = []


class MatchingRuleConditionInput(BaseModel):
    left_field: str
    operator: str = "equals"
    right_field: str
    sort_order: int = 0


class MatchingRuleFieldInput(BaseModel):
    name: str
    field_type: str = "text"
    required: bool = False
    sort_order: int = 0


class MatchingRuleCreate(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    doc_types: list[str] = []
    conditions: list[MatchingRuleConditionInput] = []
    fields: list[MatchingRuleFieldInput] = []


class MatchingRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    doc_types: list[str] | None = None
    conditions: list[MatchingRuleConditionInput] | None = None
    fields: list[MatchingRuleFieldInput] | None = None


class MatchingRuleConditionResponse(BaseModel):
    id: UUID
    left_field: str
    operator: str
    right_field: str
    sort_order: int

    model_config = {"from_attributes": True}


class MatchingRuleFieldResponse(BaseModel):
    id: UUID
    name: str
    field_type: str
    required: bool
    sort_order: int

    model_config = {"from_attributes": True}


class MatchingRuleResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    enabled: bool
    doc_types: list[str] = []
    created_at: datetime
    updated_at: datetime
    conditions: list[MatchingRuleConditionResponse] = []
    fields: list[MatchingRuleFieldResponse] = []


class MatchingRuleTestRequest(BaseModel):
    document_ids: list[UUID] = []


class MatchingRuleTestMatch(BaseModel):
    left_document_id: UUID
    right_document_id: UUID
    left_name: str
    right_name: str


class MatchingRuleTestResponse(BaseModel):
    matches: list[MatchingRuleTestMatch] = []
    evaluated_pairs: int = 0
    matched_pairs: int = 0
    skipped_pairs: int = 0
    applied_doc_types: list[str] = []


class OcrTemplateZoneInput(BaseModel):
    page_number: int = 1
    label: str
    field_type: str = "text"
    x: float
    y: float
    width: float
    height: float
    required: bool = False
    sort_order: int = 0


class OcrTemplateCreate(BaseModel):
    name: str
    doc_type: str
    description: str | None = None
    is_active: bool = True
    zones: list[OcrTemplateZoneInput] = []


class OcrTemplateUpdate(BaseModel):
    name: str | None = None
    doc_type: str | None = None
    description: str | None = None
    is_active: bool | None = None
    zones: list[OcrTemplateZoneInput] | None = None


class OcrTemplateZoneResponse(BaseModel):
    id: UUID
    page_number: int
    label: str
    field_type: str
    x: float
    y: float
    width: float
    height: float
    required: bool
    sort_order: int

    model_config = {"from_attributes": True}


class OcrTemplateResponse(BaseModel):
    id: UUID
    name: str
    doc_type: str
    description: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    zones: list[OcrTemplateZoneResponse] = []
