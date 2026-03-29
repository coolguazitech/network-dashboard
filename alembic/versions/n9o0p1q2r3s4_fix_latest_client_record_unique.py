"""fix latest_client_records unique constraint to use client_id

Revision ID: n9o0p1q2r3s4
Revises: m8n9o0p1q2r3
Create Date: 2026-03-28

Changes:
- Drop old unique constraint uk_latest_client_record (maintenance_id, mac_address)
- Create new unique constraint uk_latest_client_record (maintenance_id, client_id)
  to match the ORM model definition.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect as sa_inspect


revision: str = 'n9o0p1q2r3s4'
down_revision: Union[str, None] = 'm8n9o0p1q2r3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, table: str) -> bool:
    insp = sa_inspect(conn)
    return table in insp.get_table_names()


def _constraint_exists(conn, table: str, constraint_name: str) -> bool:
    insp = sa_inspect(conn)
    try:
        uqs = insp.get_unique_constraints(table)
        return any(c["name"] == constraint_name for c in uqs)
    except Exception:
        return False


def upgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "latest_client_records"):
        return

    # Drop the old (maintenance_id, mac_address) unique constraint
    if _constraint_exists(conn, "latest_client_records", "uk_latest_client_record"):
        op.drop_constraint("uk_latest_client_record", "latest_client_records", type_="unique")

    # Create the correct (maintenance_id, client_id) unique constraint
    op.create_unique_constraint(
        "uk_latest_client_record",
        "latest_client_records",
        ["maintenance_id", "client_id"],
    )


def downgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "latest_client_records"):
        return

    if _constraint_exists(conn, "latest_client_records", "uk_latest_client_record"):
        op.drop_constraint("uk_latest_client_record", "latest_client_records", type_="unique")

    op.create_unique_constraint(
        "uk_latest_client_record",
        "latest_client_records",
        ["maintenance_id", "mac_address"],
    )
