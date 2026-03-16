"""raw_data TEXT -> MEDIUMTEXT

Revision ID: j5d6e7f8g9h0
Revises: i4c5d6e7f8g9
Create Date: 2026-03-16

Changes:
- Alter collection_batches.raw_data from TEXT to MEDIUMTEXT (16MB limit)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'j5d6e7f8g9h0'
down_revision: Union[str, None] = 'i4c5d6e7f8g9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'collection_batches',
        'raw_data',
        existing_type=sa.Text(),
        type_=sa.Text(16_777_215),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'collection_batches',
        'raw_data',
        existing_type=sa.Text(16_777_215),
        type_=sa.Text(),
        existing_nullable=True,
    )
