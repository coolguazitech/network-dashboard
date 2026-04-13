"""version_record: rename version column to packages (JSON)

Revision ID: p1q2r3s4t5u6
Revises: o0p1q2r3s4t5
Create Date: 2026-03-30

Changes:
- Rename column `version` (VARCHAR 255) to `packages` (JSON)
- Migrate existing data: wrap single version string into JSON array
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "p1q2r3s4t5u6"
down_revision: Union[str, None] = "o0p1q2r3s4t5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(conn, table: str, column: str) -> bool:
    from sqlalchemy import text
    row = conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() "
            "AND table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).scalar()
    return bool(row)


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add new JSON column (skip if already exists — create_all case)
    if not _col_exists(conn, "version_records", "packages"):
        op.add_column(
            "version_records",
            sa.Column("packages", sa.JSON(), nullable=True),
        )

    # 2. Migrate existing data: version string → JSON array ["version"]
    if _col_exists(conn, "version_records", "version"):
        op.execute(
            """
            UPDATE version_records
            SET packages = JSON_ARRAY(version)
            WHERE version IS NOT NULL AND version != ''
            """
        )
        # 3. Drop old column
        op.drop_column("version_records", "version")


def downgrade() -> None:
    # 1. Add back version column
    op.add_column(
        "version_records",
        sa.Column("version", sa.String(255), nullable=True),
    )

    # 2. Migrate data back: take first element of packages array
    op.execute(
        """
        UPDATE version_records
        SET version = JSON_UNQUOTE(JSON_EXTRACT(packages, '$[0]'))
        WHERE packages IS NOT NULL
        """
    )

    # 3. Drop packages column
    op.drop_column("version_records", "packages")
