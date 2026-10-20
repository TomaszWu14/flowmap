"""recruit_session: timed recruitment case with an AI interview

Revision ID: c3e5a7b9d1f4
Revises: b9d1f3a5c7e2
Create Date: 2026-10-20 14:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3e5a7b9d1f4'
down_revision = 'b9d1f3a5c7e2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'recruit_session',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('minutes', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('deadline', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('grade', sa.JSON(), nullable=True),
        sa.Column('questions', sa.JSON(), nullable=True),
        sa.Column('answers', sa.JSON(), server_default='[]', nullable=False),
        sa.Column('report', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id'),
    )
    with op.batch_alter_table('recruit_session', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recruit_session_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('recruit_session', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_recruit_session_user_id'))
    op.drop_table('recruit_session')
