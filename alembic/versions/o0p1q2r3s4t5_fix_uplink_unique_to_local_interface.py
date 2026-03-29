"""fix uplink unique constraint back to local_interface

Revision ID: o0p1q2r3s4t5
Revises: n9o0p1q2r3s4
Create Date: 2026-03-29

Changes:
- Drop uk_uplink_expectation on (maintenance_id, hostname, expected_neighbor)
- Recreate uk_uplink_expectation on (maintenance_id, hostname, local_interface)

The previous migration i4c5d6e7f8g9 incorrectly changed the constraint from
local_interface to expected_neighbor. A device can have multiple uplinks to
the same neighbor via different interfaces, so the constraint must be on
local_interface to allow that.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect as sa_inspect


revision: str = 'o0p1q2r3s4t5'
down_revision: Union[str, None] = 'n9o0p1q2r3s4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_unique_constraint_columns(conn, table_name, constraint_name):
    """Return column list for a named unique constraint, or None."""
    insp = sa_inspect(conn)
    for uc in insp.get_unique_constraints(table_name):
        if uc['name'] == constraint_name:
            return uc['column_names']
    return None


def upgrade() -> None:
    conn = op.get_bind()
    cols = _get_unique_constraint_columns(conn, 'uplink_expectations', 'uk_uplink_expectation')

    # Already correct
    if cols and 'local_interface' in cols and 'expected_neighbor' not in cols:
        return

    if cols:
        op.drop_constraint('uk_uplink_expectation', 'uplink_expectations', type_='unique')

    op.create_unique_constraint(
        'uk_uplink_expectation',
        'uplink_expectations',
        ['maintenance_id', 'hostname', 'local_interface'],
    )


def downgrade() -> None:
    op.drop_constraint('uk_uplink_expectation', 'uplink_expectations', type_='unique')
    op.create_unique_constraint(
        'uk_uplink_expectation',
        'uplink_expectations',
        ['maintenance_id', 'hostname', 'expected_neighbor'],
    )
