"""Add user roles

Revision ID: c00000000005
Revises: c00000000004
Create Date: 2026-02-11

"""

import sqlalchemy as sa
from alembic import op

revision = "c00000000005"
down_revision = "c00000000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'viewer'"),
        ),
    )
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_column("users", "role")
