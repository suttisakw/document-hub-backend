"""External OCR default flag

Revision ID: c00000000004
Revises: c00000000003
Create Date: 2026-02-10

"""

import sqlalchemy as sa
from alembic import op

revision = "c00000000004"
down_revision = "c00000000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "external_ocr_interfaces",
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.create_index(
        op.f("ix_external_ocr_interfaces_is_default"),
        "external_ocr_interfaces",
        ["is_default"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_external_ocr_interfaces_is_default"),
        table_name="external_ocr_interfaces",
    )
    op.drop_column("external_ocr_interfaces", "is_default")
