"""add_cases_and_case_notes_tables

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-02-16 12:00:00.000000

新增 cases 和 case_notes 表，用於案件管理功能。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cases',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('maintenance_id', sa.String(100), nullable=False, index=True),
        sa.Column('mac_address', sa.String(17), nullable=False, index=True),
        sa.Column(
            'status',
            sa.Enum(
                'UNASSIGNED', 'ASSIGNED', 'IN_PROGRESS', 'DISCUSSING', 'RESOLVED',
                name='casestatus',
            ),
            nullable=False,
            server_default='ASSIGNED',
        ),
        sa.Column('assignee', sa.String(100), nullable=True),
        sa.Column('summary', sa.String(500), nullable=True),
        sa.Column('last_ping_reachable', sa.Boolean, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('maintenance_id', 'mac_address', name='uk_case_maintenance_mac'),
    )

    op.create_table(
        'case_notes',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('case_id', sa.Integer, sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('author', sa.String(100), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('case_notes')
    op.drop_table('cases')
