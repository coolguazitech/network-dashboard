"""add_old_is_reachable_to_device_list

Revision ID: a32b63eec0e7
Revises: 367a4017ffee
Create Date: 2026-02-01 11:11:40.411392

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a32b63eec0e7'
down_revision: Union[str, Sequence[str], None] = '367a4017ffee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add old_is_reachable and old_last_check_at columns to maintenance_device_list."""
    op.add_column('maintenance_device_list', sa.Column('old_is_reachable', sa.Boolean(), nullable=True))
    op.add_column('maintenance_device_list', sa.Column('old_last_check_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove old_is_reachable and old_last_check_at columns from maintenance_device_list."""
    op.drop_column('maintenance_device_list', 'old_last_check_at')
    op.drop_column('maintenance_device_list', 'old_is_reachable')
