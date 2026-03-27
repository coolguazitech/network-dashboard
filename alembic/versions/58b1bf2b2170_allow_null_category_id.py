"""allow null category_id

Revision ID: 58b1bf2b2170
Revises: e8f1a2b3c4d5
Create Date: 2026-02-04 21:55:28.575530

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '58b1bf2b2170'
down_revision: Union[str, Sequence[str], None] = 'e8f1a2b3c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    # Make contacts.category_id nullable and change FK ondelete to SET NULL
    op.alter_column('contacts', 'category_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=True)

    # Drop old FK only if it exists
    result = conn.execute(
        sa.text("SELECT COUNT(*) FROM information_schema.table_constraints "
                "WHERE table_schema = DATABASE() AND table_name = 'contacts' "
                "AND constraint_name = 'fk_contacts_category_id_contact_categories'")
    )
    if result.scalar() > 0:
        op.drop_constraint('fk_contacts_category_id_contact_categories', 'contacts', type_='foreignkey')

    # Re-create FK with SET NULL (drop first if it was re-created above scenario)
    op.create_foreign_key('fk_contacts_category_id_contact_categories', 'contacts', 'contact_categories', ['category_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    # Revert to NOT NULL and CASCADE
    op.drop_constraint('fk_contacts_category_id_contact_categories', 'contacts', type_='foreignkey')
    op.create_foreign_key('fk_contacts_category_id_contact_categories', 'contacts', 'contact_categories', ['category_id'], ['id'], ondelete='CASCADE')
    op.alter_column('contacts', 'category_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=False)
