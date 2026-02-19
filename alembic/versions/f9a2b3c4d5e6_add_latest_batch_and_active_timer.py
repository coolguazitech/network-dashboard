"""add_latest_collection_batch_and_active_timer

Revision ID: f9a2b3c4d5e6
Revises: 58b1bf2b2170
Create Date: 2026-02-13 10:00:00.000000

新增：
1. latest_collection_batches 表（基準+變化點策略核心）
2. maintenance_configs 新增 active_seconds_accumulated + last_activated_at（累計活躍計時器）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f9a2b3c4d5e6'
down_revision: Union[str, None] = '58b1bf2b2170'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 建立 latest_collection_batches 表
    op.create_table(
        'latest_collection_batches',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('maintenance_id', sa.String(length=100), nullable=False),
        sa.Column('collection_type', sa.String(length=100), nullable=False),
        sa.Column('switch_hostname', sa.String(length=255), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('data_hash', sa.String(length=16), nullable=False),
        sa.Column('collected_at', sa.DateTime(), nullable=False),
        sa.Column('last_checked_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['batch_id'], ['collection_batches.id'], ondelete='CASCADE'),
        sa.UniqueConstraint(
            'maintenance_id', 'collection_type', 'switch_hostname',
            name='uk_latest_batch',
        ),
    )
    op.create_index('ix_latest_collection_batches_maintenance_id', 'latest_collection_batches', ['maintenance_id'])
    op.create_index('ix_latest_collection_batches_batch_id', 'latest_collection_batches', ['batch_id'])

    # 2. maintenance_configs 新增累計活躍計時器欄位
    op.add_column('maintenance_configs', sa.Column(
        'active_seconds_accumulated', sa.Integer(), nullable=False, server_default='0',
    ))
    op.add_column('maintenance_configs', sa.Column(
        'last_activated_at', sa.DateTime(), nullable=True,
    ))


def downgrade() -> None:
    # 移除累計活躍計時器欄位
    op.drop_column('maintenance_configs', 'last_activated_at')
    op.drop_column('maintenance_configs', 'active_seconds_accumulated')

    # 移除 latest_collection_batches 表
    op.drop_index('ix_latest_collection_batches_batch_id', table_name='latest_collection_batches')
    op.drop_index('ix_latest_collection_batches_maintenance_id', table_name='latest_collection_batches')
    op.drop_table('latest_collection_batches')
