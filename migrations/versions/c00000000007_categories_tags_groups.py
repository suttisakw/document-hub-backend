"""Categories, tags, groups

Revision ID: c00000000007
Revises: c00000000006
Create Date: 2026-02-11

"""

import sqlalchemy as sa
from alembic import op

revision = "c00000000007"
down_revision = "c00000000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=30), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_document_categories_user_key"),
    )
    op.create_index(
        op.f("ix_document_categories_id"),
        "document_categories",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_categories_user_id"),
        "document_categories",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_categories_key"),
        "document_categories",
        ["key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_categories_is_active"),
        "document_categories",
        ["is_active"],
        unique=False,
    )

    op.add_column("documents", sa.Column("category_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_documents_category_id"),
        "documents",
        ["category_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_documents_category_id_document_categories",
        "documents",
        "document_categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("color", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_tags_user_name"),
    )
    op.create_index(op.f("ix_tags_id"), "tags", ["id"], unique=False)
    op.create_index(op.f("ix_tags_user_id"), "tags", ["user_id"], unique=False)
    op.create_index(op.f("ix_tags_name"), "tags", ["name"], unique=False)

    op.create_table(
        "document_tag_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "tag_id", name="uq_document_tag_links_doc_tag"
        ),
    )
    op.create_index(
        op.f("ix_document_tag_links_id"),
        "document_tag_links",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_tag_links_document_id"),
        "document_tag_links",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_tag_links_tag_id"),
        "document_tag_links",
        ["tag_id"],
        unique=False,
    )

    op.create_table(
        "document_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_document_groups_user_name"),
    )
    op.create_index(
        op.f("ix_document_groups_id"),
        "document_groups",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_groups_user_id"),
        "document_groups",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "document_group_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"], ["document_groups.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "group_id", "document_id", name="uq_document_group_links_group_doc"
        ),
    )
    op.create_index(
        op.f("ix_document_group_links_id"),
        "document_group_links",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_group_links_group_id"),
        "document_group_links",
        ["group_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_group_links_document_id"),
        "document_group_links",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_document_group_links_document_id"), table_name="document_group_links"
    )
    op.drop_index(
        op.f("ix_document_group_links_group_id"), table_name="document_group_links"
    )
    op.drop_index(op.f("ix_document_group_links_id"), table_name="document_group_links")
    op.drop_table("document_group_links")

    op.drop_index(op.f("ix_document_groups_user_id"), table_name="document_groups")
    op.drop_index(op.f("ix_document_groups_id"), table_name="document_groups")
    op.drop_table("document_groups")

    op.drop_index(op.f("ix_document_tag_links_tag_id"), table_name="document_tag_links")
    op.drop_index(
        op.f("ix_document_tag_links_document_id"), table_name="document_tag_links"
    )
    op.drop_index(op.f("ix_document_tag_links_id"), table_name="document_tag_links")
    op.drop_table("document_tag_links")

    op.drop_index(op.f("ix_tags_name"), table_name="tags")
    op.drop_index(op.f("ix_tags_user_id"), table_name="tags")
    op.drop_index(op.f("ix_tags_id"), table_name="tags")
    op.drop_table("tags")

    op.drop_constraint(
        "fk_documents_category_id_document_categories",
        "documents",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_documents_category_id"), table_name="documents")
    op.drop_column("documents", "category_id")

    op.drop_index(
        op.f("ix_document_categories_is_active"), table_name="document_categories"
    )
    op.drop_index(op.f("ix_document_categories_key"), table_name="document_categories")
    op.drop_index(
        op.f("ix_document_categories_user_id"), table_name="document_categories"
    )
    op.drop_index(op.f("ix_document_categories_id"), table_name="document_categories")
    op.drop_table("document_categories")
