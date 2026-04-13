"""add ignored_indicators JSON to maintenance_device_list

Revision ID: r3s4t5u6v7w8
Revises: q2r3s4t5u6v7
Create Date: 2026-04-14

Changes:
- Add `ignored_indicators` JSON column (default '[]')
- Per-indicator ignore: e.g. ["fan","power"] ignores only those indicators
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "r3s4t5u6v7w8"
down_revision: Union[str, None] = "q2r3s4t5u6v7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(conn, table: str, column: str) -> bool:
    from sqlalchemy import text
    row = conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() "
            "AND table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).scalar()
    return bool(row)


def upgrade() -> None:
    conn = op.get_bind()

    # 移除舊的 boolean 欄位（如果存在）
    if _col_exists(conn, "maintenance_device_list", "indicator_ignored"):
        op.drop_column("maintenance_device_list", "indicator_ignored")

    # 新增 JSON 欄位
    if not _col_exists(conn, "maintenance_device_list", "ignored_indicators"):
        op.add_column(
            "maintenance_device_list",
            sa.Column(
                "ignored_indicators",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _col_exists(conn, "maintenance_device_list", "ignored_indicators"):
        op.drop_column("maintenance_device_list", "ignored_indicators")
