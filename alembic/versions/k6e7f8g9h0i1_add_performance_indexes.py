"""add performance indexes

Revision ID: k6e7f8g9h0i1
Revises: j5d6e7f8g9h0
Create Date: 2026-03-16

Changes:
- Add ix_cr_mid_mac_ts on client_records(maintenance_id, mac_address, collected_at)
- Add ix_mml_mid_mac on maintenance_mac_list(maintenance_id, mac_address)
- Add ix_cases_mid_status_ping on cases(maintenance_id, status, last_ping_reachable)
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect, text


revision: str = 'k6e7f8g9h0i1'
down_revision: Union[str, None] = 'j5d6e7f8g9h0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(conn, table_name: str, index_name: str) -> bool:
    insp = inspect(conn)
    return any(idx['name'] == index_name for idx in insp.get_indexes(table_name))


def upgrade() -> None:
    conn = op.get_bind()
    if not _index_exists(conn, 'client_records', 'ix_cr_mid_mac_ts'):
        op.create_index(
            'ix_cr_mid_mac_ts',
            'client_records',
            ['maintenance_id', 'mac_address', 'collected_at'],
        )
    if not _index_exists(conn, 'maintenance_mac_list', 'ix_mml_mid_mac'):
        op.create_index(
            'ix_mml_mid_mac',
            'maintenance_mac_list',
            ['maintenance_id', 'mac_address'],
        )
    if not _index_exists(conn, 'cases', 'ix_cases_mid_status_ping'):
        op.create_index(
            'ix_cases_mid_status_ping',
            'cases',
            ['maintenance_id', 'status', 'last_ping_reachable'],
        )


def downgrade() -> None:
    op.drop_index('ix_cases_mid_status_ping', table_name='cases')
    op.drop_index('ix_mml_mid_mac', table_name='maintenance_mac_list')
    op.drop_index('ix_cr_mid_mac_ts', table_name='client_records')
