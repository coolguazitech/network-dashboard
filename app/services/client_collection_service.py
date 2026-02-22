"""
Client Collection Service — 純 DB 讀取版。

從 scheduler 獨立採集的 typed record tables 讀取資料，
組裝成 ClientRecord 寫入 client_records 表。

資料來源：
  1. mac_table_records   → MAC 在哪台 switch / 哪個 interface / 哪個 VLAN
  2. interface_status_records → 該 interface 的 speed / duplex / link_status
  3. gnms_ping ping_records   → client IP 的 ping 狀態
  4. static_acl / dynamic_acl records → 該 interface 的 ACL 規則
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session_context
from app.db.models import ClientRecord, LatestClientRecord, MaintenanceMacList

logger = logging.getLogger(__name__)


class ClientCollectionService:
    """
    客戶端資料組裝服務。

    純 DB 讀取：從 scheduler 獨立採集的 typed record tables 讀取，
    組裝為 ClientRecord 寫入 DB。不直接呼叫任何 fetcher。
    """

    def __init__(self) -> None:
        pass

    async def collect_client_data(
        self,
        maintenance_id: str,
    ) -> dict[str, Any]:
        """
        主入口：從 DB 讀取已採集的資料，組裝 ClientRecord。

        Args:
            maintenance_id: 歲修 ID

        Returns:
            採集統計
        """
        results: dict[str, Any] = {
            "collection_type": "client",
            "maintenance_id": maintenance_id,
            "total": 0,
            "success": 0,
            "failed": 0,
            "errors": [],
            "client_records_count": 0,
        }

        now = datetime.now(timezone.utc)

        async with get_session_context() as session:
            # 1. 載入 MAC 白名單
            client_list = await self._load_client_list(
                maintenance_id, session,
            )

            if not client_list:
                await self._write_snapshot_marker(
                    session=session,
                    maintenance_id=maintenance_id,
                    collected_at=now,
                )
                logger.info(
                    "Wrote snapshot marker for %s (no clients configured)",
                    maintenance_id,
                )
                return results

            mac_to_client = {
                c.mac_address.upper(): c for c in client_list
            }

            # 2. 從 DB 讀取最新 mac_table_records
            from app.repositories.typed_records import get_typed_repo

            mac_repo = get_typed_repo("get_mac_table", session)
            mac_records = await mac_repo.get_latest_per_device(
                maintenance_id,
            )

            # 3. 從 DB 讀取最新 interface_status_records
            if_repo = get_typed_repo("get_interface_status", session)
            if_records = await if_repo.get_latest_per_device(
                maintenance_id,
            )

            # 4. 從 DB 讀取最新 gnms_ping records
            ping_repo = get_typed_repo("gnms_ping", session)
            ping_records = await ping_repo.get_latest_per_device(
                maintenance_id,
            )

            # 5. 從 DB 讀取最新 ACL records (static + dynamic)
            sacl_repo = get_typed_repo("get_static_acl", session)
            sacl_records = await sacl_repo.get_latest_per_device(
                maintenance_id,
            )
            dacl_repo = get_typed_repo("get_dynamic_acl", session)
            dacl_records = await dacl_repo.get_latest_per_device(
                maintenance_id,
            )

            # 6. 建立 lookup maps
            # interface_status: (switch_hostname, interface_name) → record
            if_map: dict[tuple[str, str], Any] = {}
            for r in if_records:
                if_map[(r.switch_hostname, r.interface_name)] = r

            # gnms_ping: target IP → is_reachable
            ping_map: dict[str, bool] = {}
            for r in ping_records:
                ping_map[r.target] = r.is_reachable

            # ACL: (switch_hostname, interface_name) → acl_number
            # static ACL 優先，dynamic ACL 補充
            acl_map: dict[tuple[str, str], str | None] = {}
            for r in dacl_records:
                if r.acl_number:
                    acl_map[(r.switch_hostname, r.interface_name)] = r.acl_number
            for r in sacl_records:
                if r.acl_number:
                    acl_map[(r.switch_hostname, r.interface_name)] = r.acl_number

            # 7. 組裝 ClientRecord（每個 MAC 只保留一筆最佳記錄）
            best_per_mac: dict[str, ClientRecord] = {}
            found_macs: set[str] = set()

            results["total"] = len(mac_records)

            for mac_rec in mac_records:
                mac_upper = mac_rec.mac_address.upper()
                if mac_upper not in mac_to_client:
                    continue

                found_macs.add(mac_upper)
                client = mac_to_client[mac_upper]

                # 查找 interface status
                intf_key = (mac_rec.switch_hostname, mac_rec.interface_name)
                if_rec = if_map.get(intf_key)

                # 查找 ping 狀態
                ping_ok = None
                if client.ip_address:
                    ping_ok = ping_map.get(client.ip_address)

                # 查找 ACL
                acl_number = acl_map.get(intf_key)

                record = ClientRecord(
                    maintenance_id=maintenance_id,
                    collected_at=now,
                    mac_address=mac_rec.mac_address,
                    ip_address=client.ip_address,
                    switch_hostname=mac_rec.switch_hostname,
                    interface_name=mac_rec.interface_name,
                    vlan_id=mac_rec.vlan_id,
                    speed=if_rec.speed if if_rec else None,
                    duplex=if_rec.duplex if if_rec else None,
                    link_status=if_rec.link_status if if_rec else None,
                    ping_reachable=ping_ok,
                    acl_rules_applied=acl_number,
                )

                # 同一 MAC 出現在多台 switch → 保留資料最完整的
                prev = best_per_mac.get(mac_upper)
                if prev is None:
                    best_per_mac[mac_upper] = record
                else:
                    # 優先選有 ACL、有 interface status、有 link_status 的
                    def _score(r: ClientRecord) -> int:
                        s = 0
                        if r.acl_rules_applied is not None:
                            s += 4
                        if r.speed is not None:
                            s += 2
                        if r.link_status is not None:
                            s += 1
                        return s

                    if _score(record) > _score(prev):
                        best_per_mac[mac_upper] = record

            all_records: list[ClientRecord] = list(best_per_mac.values())
            results["success"] = 1 if mac_records else 0
            results["client_records_count"] = len(all_records)

            # 8. 為未找到的 MAC 建立 None 記錄（保留 ping 結果）
            missing_macs = set(mac_to_client.keys()) - found_macs
            for mac_upper in missing_macs:
                client = mac_to_client[mac_upper]

                ping_ok = None
                if client.ip_address:
                    ping_ok = ping_map.get(client.ip_address)

                all_records.append(ClientRecord(
                    maintenance_id=maintenance_id,
                    collected_at=now,
                    mac_address=client.mac_address,
                    ip_address=client.ip_address,
                    switch_hostname=None,
                    interface_name=None,
                    vlan_id=None,
                    speed=None,
                    duplex=None,
                    link_status=None,
                    ping_reachable=ping_ok,
                    acl_rules_applied=None,
                ))

            if missing_macs:
                logger.info(
                    "Added %d None records for MACs not found in %s",
                    len(missing_macs), maintenance_id,
                )

            # 9. Per-MAC 變更偵測 + 選擇性寫入
            if all_records:
                records_to_write = await self._save_changed_records(
                    session=session,
                    maintenance_id=maintenance_id,
                    all_records=all_records,
                    now=now,
                )
                if records_to_write:
                    logger.info(
                        "Saved %d/%d changed client records for %s",
                        records_to_write, len(all_records), maintenance_id,
                    )
                else:
                    logger.debug(
                        "No client data change for %s (%d records checked)",
                        maintenance_id, len(all_records),
                    )
            else:
                await self._write_snapshot_marker(
                    session=session,
                    maintenance_id=maintenance_id,
                    collected_at=now,
                )
                logger.info(
                    "Wrote snapshot marker for %s (no records)",
                    maintenance_id,
                )

        # 清理超過 7 天的舊資料
        async with get_session_context() as session:
            deleted = await self._cleanup_old_records(
                session=session,
                maintenance_id=maintenance_id,
                retention_days=7,
            )
            if deleted > 0:
                results["deleted_old_records"] = deleted

        logger.info(
            "Client collection done for %s: %d records",
            maintenance_id, results["client_records_count"],
        )
        return results

    # ── Per-MAC change detection ────────────────────────────────

    @staticmethod
    def _compute_client_record_hash(record: ClientRecord) -> str:
        """計算單一 ClientRecord 資料欄位的 SHA-256 hash（16 hex chars）。

        只 hash 「狀態」欄位，不含 identity 欄位（mac_address, ip_address）。
        """
        import hashlib

        key = (
            f"{record.switch_hostname}|{record.interface_name}|"
            f"{record.vlan_id}|{record.speed}|{record.duplex}|"
            f"{record.link_status}|{record.ping_reachable}|"
            f"{record.acl_rules_applied}"
        )
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    async def _save_changed_records(
        self,
        session: AsyncSession,
        maintenance_id: str,
        all_records: list[ClientRecord],
        now: datetime,
    ) -> int:
        """Per-MAC hash 比對，只寫入有變化的 ClientRecord。

        Returns:
            寫入的記錄數量。
        """
        # 一次載入此歲修所有 LatestClientRecord
        latest_stmt = select(LatestClientRecord).where(
            LatestClientRecord.maintenance_id == maintenance_id,
        )
        latest_result = await session.execute(latest_stmt)
        latest_map: dict[str, LatestClientRecord] = {
            row.mac_address.upper(): row
            for row in latest_result.scalars().all()
        }

        records_to_write: list[ClientRecord] = []

        for record in all_records:
            mac_upper = (record.mac_address or "").upper()
            new_hash = self._compute_client_record_hash(record)
            existing = latest_map.get(mac_upper)

            if existing and existing.data_hash == new_hash:
                # 資料未變化 → 只更新 last_checked_at
                existing.last_checked_at = now
            else:
                # 資料有變化（或首次見到）→ 寫新 ClientRecord
                records_to_write.append(record)

                if existing:
                    existing.data_hash = new_hash
                    existing.collected_at = now
                    existing.last_checked_at = now
                else:
                    session.add(LatestClientRecord(
                        maintenance_id=maintenance_id,
                        mac_address=mac_upper,
                        data_hash=new_hash,
                        collected_at=now,
                        last_checked_at=now,
                    ))

        if records_to_write:
            await self._phase4_save(session, records_to_write)

        await session.flush()
        return len(records_to_write)

    # ── On-demand detection ─────────────────────────────────────

    async def detect_clients(
        self,
        maintenance_id: str,
    ) -> dict[str, Any]:
        """
        偵測客戶端狀態（純 DB 讀取版）。

        從已採集的 gnms_ping 和 mac_table 結果判斷偵測狀態：
        - MAC 在 mac_table 中且 ping 通 → DETECTED
        - MAC 在 mac_table 中但 ping 不通 → NOT_DETECTED
        - MAC 不在 mac_table 中 → NOT_DETECTED
        """
        from sqlalchemy import update

        from app.core.enums import ClientDetectionStatus
        from app.repositories.typed_records import get_typed_repo

        results: dict[str, Any] = {
            "maintenance_id": maintenance_id,
            "total": 0,
            "detected": 0,
            "not_detected": 0,
            "errors": [],
        }

        async with get_session_context() as session:
            clients = await self._load_client_list(maintenance_id, session)
            results["total"] = len(clients)

            if not clients:
                return results

            # Reset all to NOT_CHECKED
            reset_stmt = (
                update(MaintenanceMacList)
                .where(MaintenanceMacList.maintenance_id == maintenance_id)
                .values(detection_status=ClientDetectionStatus.NOT_CHECKED)
            )
            await session.execute(reset_stmt)

            # Read latest mac_table records
            mac_repo = get_typed_repo("get_mac_table", session)
            mac_records = await mac_repo.get_latest_per_device(
                maintenance_id,
            )
            found_macs = {r.mac_address.upper() for r in mac_records}

            # Read latest gnms_ping records
            ping_repo = get_typed_repo("gnms_ping", session)
            ping_records = await ping_repo.get_latest_per_device(
                maintenance_id,
            )
            ping_map = {r.target: r.is_reachable for r in ping_records}

            # Determine detection status
            for client in clients:
                mac_upper = client.mac_address.upper()
                ip = client.ip_address

                ping_ok = ping_map.get(ip) if ip else None
                in_mac_table = mac_upper in found_macs

                if in_mac_table and ping_ok:
                    status = ClientDetectionStatus.DETECTED
                    results["detected"] += 1
                else:
                    status = ClientDetectionStatus.NOT_DETECTED
                    results["not_detected"] += 1

                stmt = (
                    update(MaintenanceMacList)
                    .where(MaintenanceMacList.id == client.id)
                    .values(detection_status=status)
                )
                await session.execute(stmt)

            await session.commit()

        logger.info(
            "Client detection done for %s: %d detected, %d not_detected",
            maintenance_id,
            results["detected"],
            results["not_detected"],
        )
        return results

    # ── Helpers ───────────────────────────────────────────────────

    async def _load_client_list(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> list[MaintenanceMacList]:
        """載入完整的 Client 清單（包含 IP、MAC、tenant_group）。"""
        stmt = select(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        clients = result.scalars().all()

        logger.info(
            "Loaded client list for %s: %d clients",
            maintenance_id, len(clients),
        )
        return list(clients)

    async def _write_snapshot_marker(
        self,
        session: AsyncSession,
        maintenance_id: str,
        collected_at: datetime,
    ) -> None:
        """寫入快照時間點標記，確保 Checkpoint 列表有時間點可選。"""
        marker = ClientRecord(
            maintenance_id=maintenance_id,
            collected_at=collected_at,
            mac_address="__MARKER__",
            ip_address=None,
            switch_hostname="__SYSTEM__",
            interface_name=None,
            vlan_id=None,
            speed=None,
            duplex=None,
            link_status=None,
            ping_reachable=None,
            acl_rules_applied=None,
        )
        session.add(marker)
        await session.flush()

    async def _phase4_save(
        self,
        session: AsyncSession,
        records: list[ClientRecord],
    ) -> None:
        """批量寫入 ClientRecord 到 client_records 表。"""
        for record in records:
            session.add(record)
        await session.flush()

    async def _cleanup_old_records(
        self,
        session: AsyncSession,
        maintenance_id: str,
        retention_days: int = 30,
    ) -> int:
        """清理超過保留期限的舊 ClientRecord。"""
        from sqlalchemy import delete

        cutoff_time = datetime.now(timezone.utc) - timedelta(
            days=retention_days,
        )

        stmt = (
            delete(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.collected_at < cutoff_time,
            )
        )

        result = await session.execute(stmt)
        await session.commit()

        return result.rowcount or 0


# ── Singleton ────────────────────────────────────────────────────

_client_collection_service: ClientCollectionService | None = None


def get_client_collection_service() -> ClientCollectionService:
    """Get or create ClientCollectionService instance."""
    global _client_collection_service
    if _client_collection_service is None:
        _client_collection_service = ClientCollectionService()
    return _client_collection_service
