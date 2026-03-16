"""fix uplink unique constraint: local_interface -> expected_neighbor

Revision ID: i4c5d6e7f8g9
Revises: 9622f91e33ff
Create Date: 2026-03-16

Changes:
- Drop old uk_uplink_expectation on (maintenance_id, hostname, local_interface)
- Create new uk_uplink_expectation on (maintenance_id, hostname, expected_neighbor)
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect


revision: str = 'i4c5d6e7f8g9'
down_revision: Union[str, None] = '9622f91e33ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_unique_constraint_columns(conn, table_name: str, constraint_name: str) -> list[str] | None:
    """Return column list for a named unique constraint, or None if not found."""
    insp = inspect(conn)
    for uc in insp.get_unique_constraints(table_name):
        if uc['name'] == constraint_name:
            return uc['column_names']
    return None


def upgrade() -> None:
    conn = op.get_bind()
    cols = _get_unique_constraint_columns(conn, 'uplink_expectations', 'uk_uplink_expectation')

    # Already correct (e.g. fresh create_all DB)
    if cols and 'expected_neighbor' in cols:
        return

    # Old constraint exists on (maintenance_id, hostname, local_interface)
    if cols:
        op.drop_constraint('uk_uplink_expectation', 'uplink_expectations', type_='unique')

    op.create_unique_constraint(
        'uk_uplink_expectation',
        'uplink_expectations',
        ['maintenance_id', 'hostname', 'expected_neighbor'],
    )


def downgrade() -> None:
    op.drop_constraint('uk_uplink_expectation', 'uplink_expectations', type_='unique')
    op.create_unique_constraint(
        'uk_uplink_expectation',
        'uplink_expectations',
        ['maintenance_id', 'hostname', 'local_interface'],
    )
