"""project display settings (swimlane order and workstation icons)

Revision ID: c4f1a9e2d7b3
Revises: 26bedb340b1e
Create Date: 2026-10-19 12:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'c4f1a9e2d7b3'
down_revision = '26bedb340b1e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.add_column(sa.Column('display', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.drop_column('display')
