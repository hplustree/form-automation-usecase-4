"""Add parallel queue tables for document and field processing

Revision ID: 002
Revises: 001
Create Date: 2024-01-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    # Create document_queue table
    op.create_table('document_queue',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('document_id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('worker_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=True),
        sa.Column('max_retries', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('queued_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for document_queue
    op.create_index('idx_doc_queue_status', 'document_queue', ['status'], unique=False)
    op.create_index('idx_doc_queue_priority', 'document_queue', ['priority'], unique=False)
    op.create_index('idx_doc_queue_document_id', 'document_queue', ['document_id'], unique=False)
    
    # Create field_queue table
    op.create_table('field_queue',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('document_id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('field_name', sa.String(), nullable=False),
        sa.Column('field_config', sa.JSON(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('worker_id', sa.String(), nullable=True),
        sa.Column('depends_on_doc', sa.Boolean(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=True),
        sa.Column('max_retries', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('queued_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for field_queue
    op.create_index('idx_field_queue_status', 'field_queue', ['status'], unique=False)
    op.create_index('idx_field_queue_priority', 'field_queue', ['priority'], unique=False)
    op.create_index('idx_field_queue_document_id', 'field_queue', ['document_id'], unique=False)
    op.create_index('idx_field_queue_field_name', 'field_queue', ['field_name'], unique=False)


def downgrade():
    # Drop indexes
    op.drop_index('idx_field_queue_field_name', table_name='field_queue')
    op.drop_index('idx_field_queue_document_id', table_name='field_queue')
    op.drop_index('idx_field_queue_priority', table_name='field_queue')
    op.drop_index('idx_field_queue_status', table_name='field_queue')
    
    op.drop_index('idx_doc_queue_document_id', table_name='document_queue')
    op.drop_index('idx_doc_queue_priority', table_name='document_queue')
    op.drop_index('idx_doc_queue_status', table_name='document_queue')
    
    # Drop tables
    op.drop_table('field_queue')
    op.drop_table('document_queue')
