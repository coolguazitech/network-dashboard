"""add arp source unique constraint

Revision ID: d7e0f1a2b3c4
Revises: c6d9e0f1a2b3
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd7e0f1a2b3c4'
down_revision: Union[str, None] = 'c6d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add unique constraint for maintenance_id + hostname
    op.create_unique_constraint(
        'uk_arp_source',
        'arp_sources',
        ['maintenance_id', 'hostname']
    )


def downgrade() -> None:
    op.drop_constraint(
        'uk_arp_source',
        'arp_sources',
        type_='unique'
    )
