"""add indicator_ignored to maintenance_device_list

Revision ID: r3s4t5u6v7w8
Revises: q2r3s4t5u6v7
Create Date: 2026-04-14

Changes:
- Add `indicator_ignored` BOOLEAN column to maintenance_device_list
- Default FALSE; when TRUE, device failures count as passes in dashboard
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
    if not _col_exists(conn, "maintenance_device_list", "indicator_ignored"):
        op.add_column(
            "maintenance_device_list",
            sa.Column(
                "indicator_ignored",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _col_exists(conn, "maintenance_device_list", "indicator_ignored"):
        op.drop_column("maintenance_device_list", "indicator_ignored")
