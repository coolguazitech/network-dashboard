"""drop_ping_success_rate_rtt

Revision ID: h3b4c5d6e7f8
Revises: g2a3b4c5d6e7
Create Date: 2026-02-25 00:00:00.000000

移除 ping_records 中未使用的 success_rate 和 avg_rtt_ms 欄位。
系統只使用 is_reachable 判斷連通性。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h3b4c5d6e7f8"
down_revision: Union[str, None] = "g2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("ping_records", "success_rate")
    op.drop_column("ping_records", "avg_rtt_ms")


def downgrade() -> None:
    op.add_column(
        "ping_records",
        sa.Column("success_rate", sa.Float(), nullable=False, server_default="1.0"),
    )
    op.add_column(
        "ping_records",
        sa.Column("avg_rtt_ms", sa.Float(), nullable=True),
    )
