"""learning mode: project.learning and question_log.hint_level

Revision ID: e5c7a1b9d2f4
Revises: d8a2b6c3e9f1
Create Date: 2026-10-19 20:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5c7a1b9d2f4'
down_revision = 'd8a2b6c3e9f1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.add_column(sa.Column('learning', sa.Boolean(), server_default=sa.false(), nullable=False))
    with op.batch_alter_table('question_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hint_level', sa.Integer(), server_default='0', nullable=False))


def downgrade():
    with op.batch_alter_table('question_log', schema=None) as batch_op:
        batch_op.drop_column('hint_level')
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.drop_column('learning')
