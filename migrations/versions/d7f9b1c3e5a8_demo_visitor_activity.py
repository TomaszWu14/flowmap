"""demo_visitor activity: screens viewed, last view, sections

Revision ID: d7f9b1c3e5a8
Revises: c5e7a9b1d3f2
Create Date: 2026-10-23 14:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'd7f9b1c3e5a8'
down_revision = 'c5e7a9b1d3f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('demo_visitor', schema=None) as batch_op:
        batch_op.add_column(sa.Column('page_views', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('last_seen_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('sections', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('demo_visitor', schema=None) as batch_op:
        batch_op.drop_column('sections')
        batch_op.drop_column('last_seen_at')
        batch_op.drop_column('page_views')
