"""add_latest_client_record

Revision ID: g2a3b4c5d6e7
Revises: f1a2b3c4d5e6
Create Date: 2026-02-21 12:00:00.000000

Per-MAC 變化偵測：取代 in-memory ClientChangeCache，改用 DB 層 per-MAC hash 追蹤。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g2a3b4c5d6e7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "latest_client_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("maintenance_id", sa.String(length=100), nullable=False),
        sa.Column("mac_address", sa.String(length=17), nullable=False),
        sa.Column("data_hash", sa.String(length=16), nullable=False),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "maintenance_id", "mac_address",
            name="uk_latest_client_record",
        ),
    )
    op.create_index(
        "ix_latest_client_records_maintenance_id",
        "latest_client_records",
        ["maintenance_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_latest_client_records_maintenance_id",
        table_name="latest_client_records",
    )
    op.drop_table("latest_client_records")
