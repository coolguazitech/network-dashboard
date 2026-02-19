"""add_ping_recovered_at_to_cases

Revision ID: d3e4f5a6b7c8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-17 03:00:00.000000

新增 ping_recovered_at 欄位，用於 GC 機制追蹤 ping 恢復時間。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column("ping_recovered_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cases", "ping_recovered_at")
