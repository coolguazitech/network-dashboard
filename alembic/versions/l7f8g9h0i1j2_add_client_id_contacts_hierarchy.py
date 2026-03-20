"""add client_id to 7 tables, contacts hierarchy and fields

Revision ID: l7f8g9h0i1j2
Revises: k6e7f8g9h0i1
Create Date: 2026-03-20

Changes:
- Add client_id (FK -> maintenance_mac_list.id) to: cases, client_records,
  client_comparisons, latest_client_records, client_severity_overrides,
  reference_clients, client_category_members
- Add parent_id (self-FK) to contact_categories
- Add department, extension, notes to contacts
- Widen contacts.title from VARCHAR(100) to VARCHAR(115)
- Drop contacts.email column
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect


revision: str = 'l7f8g9h0i1j2'
down_revision: Union[str, None] = 'k6e7f8g9h0i1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(conn, table: str, column: str) -> bool:
    insp = sa_inspect(conn)
    try:
        cols = {c["name"] for c in insp.get_columns(table)}
    except Exception:
        return False
    return column in cols


def _table_exists(conn, table: str) -> bool:
    insp = sa_inspect(conn)
    return table in insp.get_table_names()


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Add client_id to 7 tables ────────────────────────────────────
    tables_needing_client_id = [
        "cases",
        "client_records",
        "client_comparisons",
        "latest_client_records",
        "client_severity_overrides",
        "reference_clients",
        "client_category_members",
    ]
    for table in tables_needing_client_id:
        if _table_exists(conn, table) and not _col_exists(conn, table, "client_id"):
            op.add_column(table, sa.Column("client_id", sa.Integer(), nullable=True))
            # Add FK constraint
            op.create_foreign_key(
                f"fk_{table}_client_id_maintenance_mac_list",
                table, "maintenance_mac_list",
                ["client_id"], ["id"],
                ondelete="CASCADE",
            )
            # Add index for performance
            op.create_index(f"ix_{table}_client_id", table, ["client_id"])

    # ── 2. Add parent_id to contact_categories ──────────────────────────
    if _table_exists(conn, "contact_categories") and not _col_exists(conn, "contact_categories", "parent_id"):
        op.add_column("contact_categories", sa.Column("parent_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_contact_categories_parent_id_contact_categories",
            "contact_categories", "contact_categories",
            ["parent_id"], ["id"],
        )
        op.create_index("ix_contact_categories_parent_id", "contact_categories", ["parent_id"])

    # ── 3. Add new columns to contacts ──────────────────────────────────
    if _table_exists(conn, "contacts"):
        if not _col_exists(conn, "contacts", "department"):
            op.add_column("contacts", sa.Column("department", sa.String(100), nullable=True))
        if not _col_exists(conn, "contacts", "extension"):
            op.add_column("contacts", sa.Column("extension", sa.String(20), nullable=True))
        if not _col_exists(conn, "contacts", "notes"):
            op.add_column("contacts", sa.Column("notes", sa.Text(), nullable=True))

    # ── 4. Widen contacts.title ──────────────────────────────────────────
    if _table_exists(conn, "contacts") and _col_exists(conn, "contacts", "title"):
        op.alter_column("contacts", "title",
                        existing_type=sa.String(100),
                        type_=sa.String(115),
                        existing_nullable=True)

    # ── 5. Drop contacts.email ──────────────────────────────────────────
    if _table_exists(conn, "contacts") and _col_exists(conn, "contacts", "email"):
        op.drop_column("contacts", "email")


def downgrade() -> None:
    conn = op.get_bind()

    # Restore email
    if _table_exists(conn, "contacts") and not _col_exists(conn, "contacts", "email"):
        op.add_column("contacts", sa.Column("email", sa.String(200), nullable=True))

    # Restore title width
    if _table_exists(conn, "contacts") and _col_exists(conn, "contacts", "title"):
        op.alter_column("contacts", "title",
                        existing_type=sa.String(115),
                        type_=sa.String(100),
                        existing_nullable=True)

    # Drop new contact columns
    for col in ("notes", "extension", "department"):
        if _table_exists(conn, "contacts") and _col_exists(conn, "contacts", col):
            op.drop_column("contacts", col)

    # Drop parent_id from contact_categories
    if _table_exists(conn, "contact_categories") and _col_exists(conn, "contact_categories", "parent_id"):
        op.drop_constraint("fk_contact_categories_parent_id_contact_categories",
                           "contact_categories", type_="foreignkey")
        op.drop_index("ix_contact_categories_parent_id", table_name="contact_categories")
        op.drop_column("contact_categories", "parent_id")

    # Drop client_id from tables
    tables = [
        "client_category_members", "reference_clients",
        "client_severity_overrides", "latest_client_records",
        "client_comparisons", "client_records", "cases",
    ]
    for table in tables:
        if _table_exists(conn, table) and _col_exists(conn, table, "client_id"):
            op.drop_constraint(f"fk_{table}_client_id_maintenance_mac_list",
                               table, type_="foreignkey")
            op.drop_index(f"ix_{table}_client_id", table_name=table)
            op.drop_column(table, "client_id")
