"""add port channel expectation unique constraint

Revision ID: b5c8d9e0f1a2
Revises: a32b63eec0e7
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5c8d9e0f1a2'
down_revision: Union[str, None] = 'a32b63eec0e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add unique constraint for maintenance_id + hostname + port_channel
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT COUNT(*) FROM information_schema.table_constraints "
                "WHERE table_schema = DATABASE() AND table_name = 'port_channel_expectations' "
                "AND constraint_name = 'uk_port_channel_expectation'")
    )
    if result.scalar() > 0:
        return  # constraint already exists
    op.create_unique_constraint(
        'uk_port_channel_expectation',
        'port_channel_expectations',
        ['maintenance_id', 'hostname', 'port_channel']
    )


def downgrade() -> None:
    op.drop_constraint(
        'uk_port_channel_expectation',
        'port_channel_expectations',
        type_='unique'
    )
