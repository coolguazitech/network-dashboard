"""raw_data TEXT -> MEDIUMTEXT

Revision ID: j5d6e7f8g9h0
Revises: i4c5d6e7f8g9
Create Date: 2026-03-16

Changes:
- Alter collection_batches.raw_data from TEXT to MEDIUMTEXT (16MB limit)
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa


revision: str = 'j5d6e7f8g9h0'
down_revision: Union[str, None] = 'i4c5d6e7f8g9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_column_type_length(conn, table_name: str, column_name: str) -> int | None:
    """Return the column type length, or None if not found."""
    insp = inspect(conn)
    for col in insp.get_columns(table_name):
        if col['name'] == column_name:
            col_type = col['type']
            return getattr(col_type, 'length', None)
    return None


def upgrade() -> None:
    conn = op.get_bind()
    length = _get_column_type_length(conn, 'collection_batches', 'raw_data')

    # Already MEDIUMTEXT (e.g. fresh create_all DB)
    if length is not None and length >= 16_777_215:
        return

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
