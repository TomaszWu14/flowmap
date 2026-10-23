"""demo_visitor: visitor gate records (name, surname, company; 90-day retention)

Revision ID: c5e7a9b1d3f2
Revises: b2d4f6a8c0e1
Create Date: 2026-10-23 10:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'c5e7a9b1d3f2'
down_revision = 'b2d4f6a8c0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'demo_visitor',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('company', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('demo_visitor', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_demo_visitor_created_at'), ['created_at'], unique=False)


def downgrade():
    with op.batch_alter_table('demo_visitor', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_demo_visitor_created_at'))
    op.drop_table('demo_visitor')
