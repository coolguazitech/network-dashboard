"""add_new_is_reachable_to_device_list

Revision ID: 9622f91e33ff
Revises: h3b4c5d6e7f8
Create Date: 2026-02-28 17:00:57.563721

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9622f91e33ff'
down_revision: Union[str, Sequence[str], None] = 'h3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('maintenance_device_list', sa.Column('new_is_reachable', sa.Boolean(), nullable=True))
    op.add_column('maintenance_device_list', sa.Column('new_last_check_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('maintenance_device_list', 'new_last_check_at')
    op.drop_column('maintenance_device_list', 'new_is_reachable')
