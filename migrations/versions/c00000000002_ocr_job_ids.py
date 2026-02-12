"""Add external OCR identifiers

Revision ID: c00000000002
Revises: c00000000001
Create Date: 2026-02-10

"""

import sqlalchemy as sa
from alembic import op

revision = "c00000000002"
down_revision = "c00000000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ocr_jobs", sa.Column("interface_id", sa.Uuid(), nullable=True))
    op.add_column("ocr_jobs", sa.Column("transaction_id", sa.Uuid(), nullable=True))
    op.add_column("ocr_jobs", sa.Column("request_id", sa.Integer(), nullable=True))

    op.create_index(
        op.f("ix_ocr_jobs_interface_id"), "ocr_jobs", ["interface_id"], unique=False
    )
    op.create_index(
        op.f("ix_ocr_jobs_transaction_id"),
        "ocr_jobs",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ocr_jobs_request_id"), "ocr_jobs", ["request_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ocr_jobs_request_id"), table_name="ocr_jobs")
    op.drop_index(op.f("ix_ocr_jobs_transaction_id"), table_name="ocr_jobs")
    op.drop_index(op.f("ix_ocr_jobs_interface_id"), table_name="ocr_jobs")

    op.drop_column("ocr_jobs", "request_id")
    op.drop_column("ocr_jobs", "transaction_id")
    op.drop_column("ocr_jobs", "interface_id")
