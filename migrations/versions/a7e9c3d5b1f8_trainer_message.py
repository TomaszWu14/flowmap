"""trainer chat messages

Revision ID: a7e9c3d5b1f8
Revises: f1d3b5a7c9e2
Create Date: 2026-10-19 22:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'a7e9c3d5b1f8'
down_revision = 'f1d3b5a7c9e2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'trainer_message',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=10), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('trainer_message', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_trainer_message_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_trainer_message_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('trainer_message', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_trainer_message_user_id'))
        batch_op.drop_index(batch_op.f('ix_trainer_message_project_id'))
    op.drop_table('trainer_message')
