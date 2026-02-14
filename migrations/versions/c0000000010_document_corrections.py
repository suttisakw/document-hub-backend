"""Add document corrections support

Revision ID: c0000000010
Revises: c00000000009
Create Date: 2026-02-13

"""

import sqlalchemy as sa
from alembic import op

revision = "c0000000010"
down_revision = "c00000000009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create field_corrections table
    op.create_table(
        'field_corrections',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('extracted_field_id', sa.Uuid(), nullable=False),
        sa.Column('corrected_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('original_value', sa.String(), nullable=True),
        sa.Column('corrected_value', sa.String(), nullable=True),
        sa.Column('correction_type', sa.String(length=50), nullable=False),
        sa.Column('correction_reason', sa.String(length=50), nullable=False),
        sa.Column('reason_details', sa.String(), nullable=True),
        sa.Column('confidence_adjustment', sa.Float(), nullable=True),
        sa.Column('corrected_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('feedback_sentiment', sa.String(length=50), nullable=True),
        sa.Column('feedback_comment', sa.String(), nullable=True),
        sa.Column('is_critical', sa.Boolean(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['extracted_field_id'], ['extracted_fields.id'], ),
        sa.ForeignKeyConstraint(['corrected_by_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_field_corrections_extracted_field_id'), 'field_corrections', ['extracted_field_id'], unique=False)
    op.create_index(op.f('ix_field_corrections_corrected_at'), 'field_corrections', ['corrected_at'], unique=False)

    # Create document_correction_audits table
    op.create_table(
        'document_correction_audits',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('document_id', sa.Uuid(), nullable=False),
        sa.Column('corrected_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('total_fields_corrected', sa.Integer(), nullable=False),
        sa.Column('total_corrections', sa.Integer(), nullable=False),
        sa.Column('corrections_by_reason', sa.String(), nullable=True),
        sa.Column('has_critical_corrections', sa.Boolean(), nullable=False),
        sa.Column('critical_correction_count', sa.Integer(), nullable=False),
        sa.Column('feedback_provided_count', sa.Integer(), nullable=False),
        sa.Column('correction_started_at', sa.DateTime(), nullable=False),
        sa.Column('correction_completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('session_notes', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
        sa.ForeignKeyConstraint(['corrected_by_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_correction_audits_document_id'), 'document_correction_audits', ['document_id'], unique=False)

    # Add columns to extracted_fields table
    op.add_column('extracted_fields', sa.Column('is_corrected', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('extracted_fields', sa.Column('correction_version', sa.Integer(), nullable=True))

    # Add columns to documents table
    op.add_column('documents', sa.Column('has_corrections', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('documents', sa.Column('correction_status', sa.String(length=50), nullable=False, server_default='pending'))
    
    op.create_index(op.f('ix_documents_has_corrections'), 'documents', ['has_corrections'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index(op.f('ix_documents_has_corrections'), table_name='documents')
    op.drop_index(op.f('ix_document_correction_audits_document_id'), table_name='document_correction_audits')
    op.drop_index(op.f('ix_field_corrections_corrected_at'), table_name='field_corrections')
    op.drop_index(op.f('ix_field_corrections_extracted_field_id'), table_name='field_corrections')
    
    # Drop columns from documents
    op.drop_column('documents', 'correction_status')
    op.drop_column('documents', 'has_corrections')
    
    # Drop columns from extracted_fields
    op.drop_column('extracted_fields', 'correction_version')
    op.drop_column('extracted_fields', 'is_corrected')
    
    # Drop tables
    op.drop_table('document_correction_audits')
    op.drop_table('field_corrections')
