"""exercises: project.exercise_key/exercise_stage and exercise_attempt

Revision ID: b9d1f3a5c7e2
Revises: a7e9c3d5b1f8
Create Date: 2026-10-20 10:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'b9d1f3a5c7e2'
down_revision = 'a7e9c3d5b1f8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.add_column(sa.Column('exercise_key', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('exercise_stage', sa.Integer(), server_default='1', nullable=False))
    op.create_table(
        'exercise_attempt',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('stage', sa.Integer(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('feedback', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('exercise_attempt', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_exercise_attempt_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_exercise_attempt_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('exercise_attempt', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_exercise_attempt_user_id'))
        batch_op.drop_index(batch_op.f('ix_exercise_attempt_project_id'))
    op.drop_table('exercise_attempt')
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.drop_column('exercise_stage')
        batch_op.drop_column('exercise_key')
