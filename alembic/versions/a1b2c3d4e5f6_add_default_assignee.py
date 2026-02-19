"""add_default_assignee_to_maintenance_mac_list

Revision ID: a1b2c3d4e5f6
Revises: f9a2b3c4d5e6
Create Date: 2026-02-16 01:00:00.000000

新增 default_assignee 欄位至 maintenance_mac_list，
用於案件開啟時預設指派給誰。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f9a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'maintenance_mac_list',
        sa.Column('default_assignee', sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('maintenance_mac_list', 'default_assignee')
