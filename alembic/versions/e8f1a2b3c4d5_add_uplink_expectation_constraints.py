"""add uplink expectation constraints

Revision ID: e8f1a2b3c4d5
Revises: d7e0f1a2b3c4
Create Date: 2026-02-03

Changes:
- Make expected_interface NOT NULL (update existing NULLs to 'UNKNOWN')
- Add unique constraint on (maintenance_id, hostname, local_interface)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8f1a2b3c4d5'
down_revision: Union[str, None] = 'd7e0f1a2b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # First, update any NULL expected_interface to 'UNKNOWN'
    op.execute(
        "UPDATE uplink_expectations SET expected_interface = 'UNKNOWN' "
        "WHERE expected_interface IS NULL"
    )

    # Make expected_interface NOT NULL
    op.alter_column(
        'uplink_expectations',
        'expected_interface',
        existing_type=sa.String(100),
        nullable=False
    )

    # Add unique constraint
    op.create_unique_constraint(
        'uk_uplink_expectation',
        'uplink_expectations',
        ['maintenance_id', 'hostname', 'local_interface']
    )


def downgrade() -> None:
    # Drop unique constraint
    op.drop_constraint(
        'uk_uplink_expectation',
        'uplink_expectations',
        type_='unique'
    )

    # Make expected_interface nullable again
    op.alter_column(
        'uplink_expectations',
        'expected_interface',
        existing_type=sa.String(100),
        nullable=True
    )
