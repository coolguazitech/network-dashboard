"""add_interface_status_records_table

Revision ID: b2c3d4e5f6a7
Revises: c3d4e5f6a7b8
Create Date: 2026-02-16 14:00:00.000000

新增 interface_status_records 表，用於介面狀態採集（速率/雙工/連線狀態）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'interface_status_records',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('batch_id', sa.Integer, sa.ForeignKey('collection_batches.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('switch_hostname', sa.String(255), nullable=False, index=True),
        sa.Column('maintenance_id', sa.String(100), nullable=False, index=True),
        sa.Column('collected_at', sa.DateTime, nullable=False, index=True),
        sa.Column('interface_name', sa.String(100), nullable=False),
        sa.Column('link_status', sa.String(20), nullable=False),
        sa.Column('speed', sa.String(20), nullable=True),
        sa.Column('duplex', sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('interface_status_records')
