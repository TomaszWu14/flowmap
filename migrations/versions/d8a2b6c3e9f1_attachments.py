"""attachments (images for projects and steps)

Revision ID: d8a2b6c3e9f1
Revises: c4f1a9e2d7b3
Create Date: 2026-10-19 14:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'd8a2b6c3e9f1'
down_revision = 'c4f1a9e2d7b3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'attachment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('node_key', sa.String(length=16), server_default='', nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('filename', sa.String(length=200), nullable=False),
        sa.Column('mime', sa.String(length=30), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('caption', sa.String(length=200), server_default='', nullable=False),
        sa.Column('is_cover', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('attachment', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_attachment_project_id'), ['project_id'], unique=False)


def downgrade():
    with op.batch_alter_table('attachment', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_attachment_project_id'))
    op.drop_table('attachment')
