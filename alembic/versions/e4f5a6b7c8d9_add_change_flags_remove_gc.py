"""add_change_flags_remove_ping_recovered_at

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-02-17 10:00:00.000000

新增 change_flags JSON 欄位（預先計算屬性變化），移除 ping_recovered_at（不再需要 GC）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column("change_flags", sa.JSON(), nullable=True),
    )
    op.drop_column("cases", "ping_recovered_at")


def downgrade() -> None:
    op.drop_column("cases", "change_flags")
    op.add_column(
        "cases",
        sa.Column("ping_recovered_at", sa.DateTime(), nullable=True),
    )
