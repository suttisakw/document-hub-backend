"""Matching, rules, OCR templates

Revision ID: c00000000008
Revises: c00000000007
Create Date: 2026-02-11

"""

import sqlalchemy as sa
from alembic import op

revision = "c00000000008"
down_revision = "c00000000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "matching_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("doc_types", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_matching_rules_id"), "matching_rules", ["id"], unique=False)
    op.create_index(op.f("ix_matching_rules_user_id"), "matching_rules", ["user_id"], unique=False)
    op.create_index(op.f("ix_matching_rules_enabled"), "matching_rules", ["enabled"], unique=False)

    op.create_table(
        "matching_rule_conditions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("left_field", sa.String(length=255), nullable=False),
        sa.Column("operator", sa.String(length=50), nullable=False),
        sa.Column("right_field", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["matching_rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_matching_rule_conditions_id"),
        "matching_rule_conditions",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_matching_rule_conditions_rule_id"),
        "matching_rule_conditions",
        ["rule_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_matching_rule_conditions_operator"),
        "matching_rule_conditions",
        ["operator"],
        unique=False,
    )

    op.create_table(
        "matching_rule_fields",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("field_type", sa.String(length=100), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["matching_rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_matching_rule_fields_id"), "matching_rule_fields", ["id"], unique=False)
    op.create_index(
        op.f("ix_matching_rule_fields_rule_id"),
        "matching_rule_fields",
        ["rule_id"],
        unique=False,
    )

    op.create_table(
        "document_match_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="review"),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("rule_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["matching_rules.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_document_match_sets_id"), "document_match_sets", ["id"], unique=False)
    op.create_index(
        op.f("ix_document_match_sets_user_id"),
        "document_match_sets",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_match_sets_status"),
        "document_match_sets",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_match_sets_source"),
        "document_match_sets",
        ["source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_match_sets_rule_id"),
        "document_match_sets",
        ["rule_id"],
        unique=False,
    )

    op.create_table(
        "document_match_set_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("set_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["set_id"], ["document_match_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("set_id", "document_id", name="uq_document_match_set_links_set_doc"),
        sa.UniqueConstraint("document_id", name="uq_document_match_set_links_document_once"),
    )
    op.create_index(
        op.f("ix_document_match_set_links_id"),
        "document_match_set_links",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_match_set_links_set_id"),
        "document_match_set_links",
        ["set_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_match_set_links_document_id"),
        "document_match_set_links",
        ["document_id"],
        unique=False,
    )

    op.create_table(
        "ocr_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("doc_type", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ocr_templates_id"), "ocr_templates", ["id"], unique=False)
    op.create_index(op.f("ix_ocr_templates_user_id"), "ocr_templates", ["user_id"], unique=False)
    op.create_index(op.f("ix_ocr_templates_doc_type"), "ocr_templates", ["doc_type"], unique=False)
    op.create_index(op.f("ix_ocr_templates_is_active"), "ocr_templates", ["is_active"], unique=False)

    op.create_table(
        "ocr_template_zones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("field_type", sa.String(length=100), nullable=False, server_default="text"),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("width", sa.Float(), nullable=False),
        sa.Column("height", sa.Float(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["ocr_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ocr_template_zones_id"), "ocr_template_zones", ["id"], unique=False)
    op.create_index(
        op.f("ix_ocr_template_zones_template_id"),
        "ocr_template_zones",
        ["template_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ocr_template_zones_template_id"), table_name="ocr_template_zones")
    op.drop_index(op.f("ix_ocr_template_zones_id"), table_name="ocr_template_zones")
    op.drop_table("ocr_template_zones")

    op.drop_index(op.f("ix_ocr_templates_is_active"), table_name="ocr_templates")
    op.drop_index(op.f("ix_ocr_templates_doc_type"), table_name="ocr_templates")
    op.drop_index(op.f("ix_ocr_templates_user_id"), table_name="ocr_templates")
    op.drop_index(op.f("ix_ocr_templates_id"), table_name="ocr_templates")
    op.drop_table("ocr_templates")

    op.drop_index(op.f("ix_document_match_set_links_document_id"), table_name="document_match_set_links")
    op.drop_index(op.f("ix_document_match_set_links_set_id"), table_name="document_match_set_links")
    op.drop_index(op.f("ix_document_match_set_links_id"), table_name="document_match_set_links")
    op.drop_table("document_match_set_links")

    op.drop_index(op.f("ix_document_match_sets_rule_id"), table_name="document_match_sets")
    op.drop_index(op.f("ix_document_match_sets_source"), table_name="document_match_sets")
    op.drop_index(op.f("ix_document_match_sets_status"), table_name="document_match_sets")
    op.drop_index(op.f("ix_document_match_sets_user_id"), table_name="document_match_sets")
    op.drop_index(op.f("ix_document_match_sets_id"), table_name="document_match_sets")
    op.drop_table("document_match_sets")

    op.drop_index(op.f("ix_matching_rule_fields_rule_id"), table_name="matching_rule_fields")
    op.drop_index(op.f("ix_matching_rule_fields_id"), table_name="matching_rule_fields")
    op.drop_table("matching_rule_fields")

    op.drop_index(op.f("ix_matching_rule_conditions_operator"), table_name="matching_rule_conditions")
    op.drop_index(op.f("ix_matching_rule_conditions_rule_id"), table_name="matching_rule_conditions")
    op.drop_index(op.f("ix_matching_rule_conditions_id"), table_name="matching_rule_conditions")
    op.drop_table("matching_rule_conditions")

    op.drop_index(op.f("ix_matching_rules_enabled"), table_name="matching_rules")
    op.drop_index(op.f("ix_matching_rules_user_id"), table_name="matching_rules")
    op.drop_index(op.f("ix_matching_rules_id"), table_name="matching_rules")
    op.drop_table("matching_rules")
