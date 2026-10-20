"""ai_usage: tokens and cost of every Anthropic API call

Revision ID: d5f7b9c1e3a6
Revises: c3e5a7b9d1f4
Create Date: 2026-10-20 16:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'd5f7b9c1e3a6'
down_revision = 'c3e5a7b9d1f4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ai_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('feature', sa.String(length=40), nullable=False),
        sa.Column('model', sa.String(length=60), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('ai_usage', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_usage_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_usage_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('ai_usage', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_usage_user_id'))
        batch_op.drop_index(batch_op.f('ix_ai_usage_created_at'))
    op.drop_table('ai_usage')
