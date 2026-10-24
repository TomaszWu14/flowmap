"""client_review: client verdicts on a shared map (accept / changes)

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d2
Create Date: 2026-10-22 18:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'b2d4f6a8c0e1'
down_revision = 'a1c3e5f7b9d2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'client_review',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('version_id', sa.Integer(), nullable=True),
        sa.Column('version_label', sa.String(length=300), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('decision', sa.String(length=10), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('client_review', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_client_review_project_id'), ['project_id'], unique=False)


def downgrade():
    with op.batch_alter_table('client_review', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_client_review_project_id'))
    op.drop_table('client_review')
