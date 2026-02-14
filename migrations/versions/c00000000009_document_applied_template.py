"""Document applied_template_id and applied_template_name

Revision ID: c00000000009
Revises: c00000000008
Create Date: 2026-02-13

"""

import sqlalchemy as sa
from alembic import op

revision = "c00000000009"
down_revision = "c00000000008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("applied_template_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("applied_template_name", sa.String(length=255), nullable=True),
    )
    op.create_index(
        op.f("ix_documents_applied_template_id"),
        "documents",
        ["applied_template_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_documents_applied_template_id",
        "documents",
        "ocr_templates",
        ["applied_template_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_documents_applied_template_id",
        "documents",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_documents_applied_template_id"), table_name="documents")
    op.drop_column("documents", "applied_template_name")
    op.drop_column("documents", "applied_template_id")
