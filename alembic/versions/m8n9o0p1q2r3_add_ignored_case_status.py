"""add IGNORED to casestatus enum

Revision ID: m8n9o0p1q2r3
Revises: l7f8g9h0i1j2
Create Date: 2026-03-28 12:00:00.000000

新增「不處理」(IGNORED) 案件狀態。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'm8n9o0p1q2r3'
down_revision: Union[str, None] = 'l7f8g9h0i1j2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Check if IGNORED already exists in the enum
    result = conn.execute(
        sa.text(
            "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'cases' AND COLUMN_NAME = 'status'"
        )
    )
    col_type = result.scalar() or ""
    if "'IGNORED'" not in col_type:
        op.execute(
            "ALTER TABLE cases MODIFY COLUMN status "
            "ENUM('UNASSIGNED','ASSIGNED','IN_PROGRESS','DISCUSSING','RESOLVED','IGNORED') "
            "NOT NULL DEFAULT 'ASSIGNED'"
        )


def downgrade() -> None:
    # Convert any IGNORED back to ASSIGNED before shrinking enum
    op.execute("UPDATE cases SET status = 'ASSIGNED' WHERE status = 'IGNORED'")
    op.execute(
        "ALTER TABLE cases MODIFY COLUMN status "
        "ENUM('UNASSIGNED','ASSIGNED','IN_PROGRESS','DISCUSSING','RESOLVED') "
        "NOT NULL DEFAULT 'ASSIGNED'"
    )
