"""add_ping_reachable_since

Revision ID: f1a2b3c4d5e6
Revises: e4f5a6b7c8d9
Create Date: 2026-02-17 12:00:00.000000

新增 ping_reachable_since 欄位用於 anti-flapping（持續可達 10 分鐘才自動結案）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column("ping_reachable_since", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cases", "ping_reachable_since")
