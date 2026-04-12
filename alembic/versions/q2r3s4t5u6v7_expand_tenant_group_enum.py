"""expand tenant_group enum with all fab tenants

Revision ID: q2r3s4t5u6v7
Revises: p1q2r3s4t5u6
Create Date: 2026-04-13

Changes:
- Expand tenant_group ENUM in maintenance_device_list and maintenance_mac_list
- Add: Infra, 200mm, F15, F16, F20, F21, F22, F23
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "q2r3s4t5u6v7"
down_revision: Union[str, None] = "p1q2r3s4t5u6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_ENUM = "'Infra','Fab200mm','AP','F6','F12','F14','F15','F16','F18','F20','F21','F22','F23'"

TABLES = ["maintenance_device_list", "maintenance_mac_list"]


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = :t"
        ),
        {"t": table},
    ).scalar()
    return bool(row)


def upgrade() -> None:
    conn = op.get_bind()
    for table in TABLES:
        if not _table_exists(conn, table):
            continue
        op.execute(
            f"ALTER TABLE {table} "
            f"MODIFY COLUMN tenant_group ENUM({NEW_ENUM}) NOT NULL DEFAULT 'F18'"
        )


def downgrade() -> None:
    old_enum = "'F18','F6','AP','F14','F12'"
    conn = op.get_bind()
    for table in TABLES:
        if not _table_exists(conn, table):
            continue
        op.execute(
            f"ALTER TABLE {table} "
            f"MODIFY COLUMN tenant_group ENUM({old_enum}) NOT NULL DEFAULT 'F18'"
        )
