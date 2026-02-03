"""remove_ip_address_from_arp_sources

Revision ID: 367a4017ffee
Revises:
Create Date: 2026-01-31 05:20:38.498985

移除 arp_sources 表的 ip_address 欄位。
ARP 來源設備不需要獨立的 IP 位址欄位，因為可以從設備清單取得。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '367a4017ffee'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """移除 ip_address 欄位。"""
    op.drop_column('arp_sources', 'ip_address')


def downgrade() -> None:
    """還原 ip_address 欄位。"""
    op.add_column(
        'arp_sources',
        sa.Column('ip_address', sa.String(45), nullable=False)
    )
