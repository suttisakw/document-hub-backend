"""External OCR interfaces

Revision ID: c00000000003
Revises: c00000000002
Create Date: 2026-02-10

"""

import sqlalchemy as sa
from alembic import op

revision = "c00000000003"
down_revision = "c00000000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_ocr_interfaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("trigger_url", sa.String(length=1000), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("webhook_secret", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_external_ocr_interfaces_id"),
        "external_ocr_interfaces",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_ocr_interfaces_user_id"),
        "external_ocr_interfaces",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_external_ocr_interfaces_user_id"), table_name="external_ocr_interfaces"
    )
    op.drop_index(
        op.f("ix_external_ocr_interfaces_id"), table_name="external_ocr_interfaces"
    )
    op.drop_table("external_ocr_interfaces")
