"""ai_cache: validated AI tool payloads keyed by a hash of model, tool and prompt

Revision ID: a1c3e5f7b9d2
Revises: d5f7b9c1e3a6
Create Date: 2026-10-22 14:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1c3e5f7b9d2'
down_revision = 'd5f7b9c1e3a6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ai_cache',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('tool', sa.String(length=60), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    with op.batch_alter_table('ai_cache', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_cache_created_at'), ['created_at'], unique=False)


def downgrade():
    with op.batch_alter_table('ai_cache', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_cache_created_at'))
    op.drop_table('ai_cache')
