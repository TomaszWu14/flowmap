"""trainer evaluation history

Revision ID: f1d3b5a7c9e2
Revises: e5c7a1b9d2f4
Create Date: 2026-10-19 21:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'f1d3b5a7c9e2'
down_revision = 'e5c7a1b9d2f4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'evaluation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('source', sa.String(length=10), server_default='rules', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('evaluation', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_evaluation_project_id'), ['project_id'], unique=False)


def downgrade():
    with op.batch_alter_table('evaluation', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_evaluation_project_id'))
    op.drop_table('evaluation')
