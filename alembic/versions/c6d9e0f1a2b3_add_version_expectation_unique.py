"""add version expectation unique constraint

Revision ID: c6d9e0f1a2b3
Revises: b5c8d9e0f1a2
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c6d9e0f1a2b3'
down_revision: Union[str, None] = 'b5c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add unique constraint for maintenance_id + hostname
    op.create_unique_constraint(
        'uk_version_expectation',
        'version_expectations',
        ['maintenance_id', 'hostname']
    )


def downgrade() -> None:
    op.drop_constraint(
        'uk_version_expectation',
        'version_expectations',
        type_='unique'
    )
