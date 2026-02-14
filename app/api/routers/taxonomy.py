from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models import (
    Document,
    DocumentCategory,
    DocumentGroup,
    DocumentGroupLink,
    DocumentTagLink,
    Tag,
    User,
)
from app.schemas import (
    CategoryCreate,
    CategoryResponse,
    CategoryStatsResponse,
    CategoryUpdate,
    DocumentGroupCreate,
    DocumentGroupResponse,
    DocumentGroupUpdate,
    SetCategoryRequest,
    SetGroupDocumentsRequest,
    SetTagsRequest,
    TagCreate,
    TagResponse,
    TagStatsResponse,
    TagUpdate,
)

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
    summary="List categories",
    description="All categories for current user.",
)
def list_categories(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[DocumentCategory]:
    items = session.exec(
        select(DocumentCategory)
        .where(DocumentCategory.user_id == current_user.id)
        .order_by(DocumentCategory.updated_at.desc())
    ).all()
    return list(items)


@router.get(
    "/categories/stats",
    response_model=list[CategoryStatsResponse],
    summary="Category stats",
    description="Categories with document counts.",
)
def category_stats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[CategoryStatsResponse]:
    cats = session.exec(
        select(DocumentCategory)
        .where(DocumentCategory.user_id == current_user.id)
        .order_by(DocumentCategory.updated_at.desc())
    ).all()

    docs = session.exec(
        select(Document).where(Document.user_id == current_user.id)
    ).all()

    counts: dict[UUID, int] = {}
    for d in docs:
        if d.category_id is None:
            continue
        counts[d.category_id] = counts.get(d.category_id, 0) + 1

    out: list[CategoryStatsResponse] = []
    for c in cats:
        out.append(
            CategoryStatsResponse(
                **CategoryResponse.model_validate(c, from_attributes=True).model_dump(),
                document_count=counts.get(c.id, 0),
            )
        )
    return out


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create category",
    description="Create document category.",
)
def create_category(
    body: CategoryCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DocumentCategory:
    existing = session.exec(
        select(DocumentCategory).where(
            DocumentCategory.user_id == current_user.id,
            DocumentCategory.key == body.key,
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Category key already exists")

    now = datetime.utcnow()
    item = DocumentCategory(
        user_id=current_user.id,
        key=body.key,
        name=body.name,
        description=body.description,
        color=body.color,
        is_active=body.is_active,
        created_at=now,
        updated_at=now,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryResponse,
    summary="Update category",
    description="Update name, description, color, is_active.",
)
def update_category(
    category_id: UUID,
    body: CategoryUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DocumentCategory:
    item = session.exec(
        select(DocumentCategory).where(
            DocumentCategory.user_id == current_user.id,
            DocumentCategory.id == category_id,
        )
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Category not found")

    changed = False
    if body.name is not None:
        item.name = body.name
        changed = True
    if body.description is not None:
        item.description = body.description
        changed = True
    if body.color is not None:
        item.color = body.color or None
        changed = True
    if body.is_active is not None:
        item.is_active = body.is_active
        changed = True

    if changed:
        item.updated_at = datetime.utcnow()
        session.add(item)
        session.commit()
        session.refresh(item)
    return item


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete category",
    description="Delete category and unset from documents.",
)
def delete_category(
    category_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    item = session.exec(
        select(DocumentCategory).where(
            DocumentCategory.user_id == current_user.id,
            DocumentCategory.id == category_id,
        )
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Category not found")

    # Unset from documents
    docs = session.exec(
        select(Document).where(
            Document.user_id == current_user.id,
            Document.category_id == item.id,
        )
    ).all()
    for d in docs:
        d.category_id = None
        session.add(d)

    session.delete(item)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/documents/{document_id}/category",
    response_model=dict,
    summary="Set document category",
    description="Set or clear category for document.",
)
def set_document_category(
    document_id: UUID,
    body: SetCategoryRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    doc = session.exec(
        select(Document).where(
            Document.id == document_id, Document.user_id == current_user.id
        )
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if body.category_id is None:
        doc.category_id = None
        session.add(doc)
        session.commit()
        return {"ok": True}

    cat = session.exec(
        select(DocumentCategory).where(
            DocumentCategory.user_id == current_user.id,
            DocumentCategory.id == body.category_id,
        )
    ).first()
    if cat is None:
        raise HTTPException(status_code=404, detail="Category not found")

    doc.category_id = cat.id
    doc.type = cat.name
    doc.updated_at = datetime.utcnow()
    session.add(doc)
    session.commit()
    return {"ok": True}


@router.get(
    "/tags",
    response_model=list[TagResponse],
    summary="List tags",
    description="All tags for current user.",
)
def list_tags(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[Tag]:
    items = session.exec(
        select(Tag)
        .where(Tag.user_id == current_user.id)
        .order_by(Tag.updated_at.desc())
    ).all()
    return list(items)


@router.get(
    "/tags/stats",
    response_model=list[TagStatsResponse],
    summary="Tag stats",
    description="Tags with document counts.",
)
def tag_stats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[TagStatsResponse]:
    tags = session.exec(
        select(Tag)
        .where(Tag.user_id == current_user.id)
        .order_by(Tag.updated_at.desc())
    ).all()
    docs = session.exec(
        select(Document).where(Document.user_id == current_user.id)
    ).all()
    doc_ids = {d.id for d in docs}

    links = session.exec(
        select(DocumentTagLink).where(DocumentTagLink.document_id.in_(doc_ids))
    ).all()
    counts: dict[UUID, int] = {}
    for link in links:
        counts[link.tag_id] = counts.get(link.tag_id, 0) + 1

    out: list[TagStatsResponse] = []
    for t in tags:
        out.append(
            TagStatsResponse(
                **TagResponse.model_validate(t, from_attributes=True).model_dump(),
                document_count=counts.get(t.id, 0),
            )
        )
    return out


@router.post(
    "/tags",
    response_model=TagResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create tag",
    description="Create tag.",
)
def create_tag(
    body: TagCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Tag:
    existing = session.exec(
        select(Tag).where(Tag.user_id == current_user.id, Tag.name == body.name)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Tag name already exists")

    now = datetime.utcnow()
    item = Tag(
        user_id=current_user.id,
        name=body.name,
        color=body.color,
        created_at=now,
        updated_at=now,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.patch(
    "/tags/{tag_id}",
    response_model=TagResponse,
    summary="Update tag",
    description="Update name, color.",
)
def update_tag(
    tag_id: UUID,
    body: TagUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Tag:
    item = session.exec(
        select(Tag).where(Tag.user_id == current_user.id, Tag.id == tag_id)
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Tag not found")

    changed = False
    if body.name is not None:
        item.name = body.name
        changed = True
    if body.color is not None:
        item.color = body.color or None
        changed = True

    if changed:
        item.updated_at = datetime.utcnow()
        session.add(item)
        session.commit()
        session.refresh(item)
    return item


@router.delete(
    "/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete tag",
    description="Delete tag and its document links.",
)
def delete_tag(
    tag_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    item = session.exec(
        select(Tag).where(Tag.user_id == current_user.id, Tag.id == tag_id)
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Tag not found")

    links = session.exec(
        select(DocumentTagLink).where(DocumentTagLink.tag_id == item.id)
    ).all()
    for link in links:
        session.delete(link)
    session.delete(item)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/documents/{document_id}/tags",
    response_model=list[TagResponse],
    summary="Get document tags",
    description="Tags assigned to document.",
)
def get_document_tags(
    document_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[Tag]:
    doc = session.exec(
        select(Document).where(
            Document.id == document_id, Document.user_id == current_user.id
        )
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    links = session.exec(
        select(DocumentTagLink).where(DocumentTagLink.document_id == doc.id)
    ).all()
    tag_ids = [link.tag_id for link in links]
    if not tag_ids:
        return []
    tags = session.exec(
        select(Tag).where(Tag.user_id == current_user.id, Tag.id.in_(tag_ids))
    ).all()
    return list(tags)


@router.put(
    "/documents/{document_id}/tags",
    response_model=dict,
    summary="Set document tags",
    description="Replace tags for document.",
)
def set_document_tags(
    document_id: UUID,
    body: SetTagsRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    doc = session.exec(
        select(Document).where(
            Document.id == document_id, Document.user_id == current_user.id
        )
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Validate tags belong to user
    if body.tag_ids:
        tags = session.exec(
            select(Tag).where(Tag.user_id == current_user.id, Tag.id.in_(body.tag_ids))
        ).all()
        if len(tags) != len(set(body.tag_ids)):
            raise HTTPException(status_code=400, detail="Invalid tag_ids")

    # Clear existing
    existing = session.exec(
        select(DocumentTagLink).where(DocumentTagLink.document_id == doc.id)
    ).all()
    for link in existing:
        session.delete(link)

    now = datetime.utcnow()
    for tid in body.tag_ids:
        session.add(DocumentTagLink(document_id=doc.id, tag_id=tid, created_at=now))

    session.commit()
    return {"ok": True}


@router.get(
    "/groups",
    response_model=list[DocumentGroupResponse],
    summary="List groups",
    description="All document groups for current user.",
)
def list_groups(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[DocumentGroup]:
    items = session.exec(
        select(DocumentGroup)
        .where(DocumentGroup.user_id == current_user.id)
        .order_by(DocumentGroup.updated_at.desc())
    ).all()
    return list(items)


@router.post(
    "/groups",
    response_model=DocumentGroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create group",
    description="Create document group.",
)
def create_group(
    body: DocumentGroupCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DocumentGroup:
    existing = session.exec(
        select(DocumentGroup).where(
            DocumentGroup.user_id == current_user.id,
            DocumentGroup.name == body.name,
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Group name already exists")

    now = datetime.utcnow()
    item = DocumentGroup(
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        created_at=now,
        updated_at=now,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.patch(
    "/groups/{group_id}",
    response_model=DocumentGroupResponse,
    summary="Update group",
    description="Update name, description.",
)
def update_group(
    group_id: UUID,
    body: DocumentGroupUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DocumentGroup:
    item = session.exec(
        select(DocumentGroup).where(
            DocumentGroup.user_id == current_user.id,
            DocumentGroup.id == group_id,
        )
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Group not found")

    changed = False
    if body.name is not None:
        item.name = body.name
        changed = True
    if body.description is not None:
        item.description = body.description
        changed = True

    if changed:
        item.updated_at = datetime.utcnow()
        session.add(item)
        session.commit()
        session.refresh(item)
    return item


@router.delete(
    "/groups/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete group",
    description="Delete group and its document links.",
)
def delete_group(
    group_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    item = session.exec(
        select(DocumentGroup).where(
            DocumentGroup.user_id == current_user.id,
            DocumentGroup.id == group_id,
        )
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Group not found")

    links = session.exec(
        select(DocumentGroupLink).where(DocumentGroupLink.group_id == item.id)
    ).all()
    for link in links:
        session.delete(link)
    session.delete(item)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/groups/{group_id}/documents",
    response_model=list[UUID],
    summary="Get group documents",
    description="Document IDs in group.",
)
def get_group_documents(
    group_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[UUID]:
    grp = session.exec(
        select(DocumentGroup).where(
            DocumentGroup.user_id == current_user.id,
            DocumentGroup.id == group_id,
        )
    ).first()
    if grp is None:
        raise HTTPException(status_code=404, detail="Group not found")

    links = session.exec(
        select(DocumentGroupLink).where(DocumentGroupLink.group_id == grp.id)
    ).all()
    return [link.document_id for link in links]


@router.put(
    "/groups/{group_id}/documents",
    response_model=dict,
    summary="Set group documents",
    description="Replace documents in group.",
)
def set_group_documents(
    group_id: UUID,
    body: SetGroupDocumentsRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    grp = session.exec(
        select(DocumentGroup).where(
            DocumentGroup.user_id == current_user.id,
            DocumentGroup.id == group_id,
        )
    ).first()
    if grp is None:
        raise HTTPException(status_code=404, detail="Group not found")

    # Validate docs belong to user
    if body.document_ids:
        docs = session.exec(
            select(Document).where(
                Document.user_id == current_user.id,
                Document.id.in_(body.document_ids),
            )
        ).all()
        if len(docs) != len(set(body.document_ids)):
            raise HTTPException(status_code=400, detail="Invalid document_ids")

    existing = session.exec(
        select(DocumentGroupLink).where(DocumentGroupLink.group_id == grp.id)
    ).all()
    for link in existing:
        session.delete(link)

    now = datetime.utcnow()
    for did in body.document_ids:
        session.add(DocumentGroupLink(group_id=grp.id, document_id=did, created_at=now))

    grp.updated_at = now
    session.add(grp)
    session.commit()
    return {"ok": True}
