"""Mock data generator for testing data flows.

生成隨機但真實的 Mock 資料，用於測試整體資料流。
"""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ClientRecord,
    MaintenanceMacList,
    MaintenanceDeviceList,
    CollectionBatch,
    VersionRecord,
    VersionExpectation,
)
from app.core.enums import MaintenancePhase, TenantGroup


class MockDataGenerator:
    """生成隨機但真實的 Mock 資料。

    用於定期產生 ClientRecord 資料，模擬真實網路環境的變化。
    """

    # 變化機率配置
    SPEED_CHANGE_PROB = 0.05      # 5% 機率速度變化
    DUPLEX_CHANGE_PROB = 0.02     # 2% 機率雙工變化
    LINK_DOWN_PROB = 0.03         # 3% 機率連結斷線
    PING_FAIL_PROB = 0.05         # 5% 機率 ping 失敗
    PORT_CHANGE_PROB = 0.02       # 2% 機率埠口變化
    VLAN_CHANGE_PROB = 0.01       # 1% 機率 VLAN 變化

    # 可能的值
    SPEEDS = ["100M", "1G", "1000M", "10G"]
    DUPLEXES = ["full", "half"]

    # Tenant Group 對應表
    TENANT_TO_CATEGORY = {
        TenantGroup.F18: "EQP",
        TenantGroup.F6: "AMHS",
        TenantGroup.AP: "SNR",
        TenantGroup.F14: "OTHERS",
        TenantGroup.F12: "OTHERS",
    }

    TENANT_TO_VLAN = {
        TenantGroup.F18: 10,
        TenantGroup.F6: 20,
        TenantGroup.AP: 30,
        TenantGroup.F14: 40,
        TenantGroup.F12: 40,
    }

    async def generate_client_records(
        self,
        maintenance_id: str,
        phase: MaintenancePhase,
        session: AsyncSession,
        base_records: list[ClientRecord] | None = None,
    ) -> list[ClientRecord]:
        """
        生成 ClientRecord 資料。

        如果提供 base_records，會基於它們產生變化版本。
        否則從 MaintenanceMacList 產生全新資料。

        Args:
            maintenance_id: 歲修 ID
            phase: 階段（OLD 或 NEW）
            session: DB session
            base_records: 基準記錄（可選，用於產生變化）

        Returns:
            生成的 ClientRecord 列表
        """
        now = datetime.now(timezone.utc)
        records = []

        # 獲取有效的交換機 hostname 列表
        valid_hostnames = await self._get_valid_switch_hostnames(
            maintenance_id, phase, session
        )

        if base_records:
            # 基於現有記錄產生變化
            for base in base_records:
                record = self._create_varied_record(base, now)
                records.append(record)
        else:
            # 從 MAC 清單產生新記錄
            stmt = select(MaintenanceMacList).where(
                MaintenanceMacList.maintenance_id == maintenance_id
            )
            result = await session.execute(stmt)
            mac_list = result.scalars().all()

            for mac_entry in mac_list:
                record = self._create_new_record(
                    mac_entry, maintenance_id, phase, now, valid_hostnames,
                )
                records.append(record)

        return records

    async def generate_version_records(
        self,
        maintenance_id: str,
        phase: MaintenancePhase,
        session: AsyncSession,
    ) -> list[VersionRecord]:
        """
        生成 VersionRecord 資料。

        根據 MaintenanceDeviceList 中的設備，產生版本採集記錄。
        如果設備有 VersionExpectation，會以一定機率符合期望版本。

        Args:
            maintenance_id: 歲修 ID
            phase: 階段（OLD 或 NEW）
            session: DB session

        Returns:
            生成的 VersionRecord 列表
        """
        now = datetime.now(timezone.utc)
        records = []

        # 獲取設備列表
        stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        devices = result.scalars().all()

        if not devices:
            return records

        # 獲取版本期望（用於模擬符合/不符合）
        exp_stmt = select(VersionExpectation).where(
            VersionExpectation.maintenance_id == maintenance_id
        )
        exp_result = await session.execute(exp_stmt)
        expectations = exp_result.scalars().all()
        exp_map = {exp.hostname: exp.expected_versions.split(";")[0] for exp in expectations}

        # 可能的版本列表
        VERSIONS = ["16.12.4", "17.3.2", "17.3.3", "15.2.4", "9.3(8)", "7.0(3)I7(6)"]

        for device in devices:
            # 根據 phase 選擇 hostname 和檢查可達性
            if phase == MaintenancePhase.NEW:
                hostname = device.new_hostname
                is_reachable = device.is_reachable
            else:
                hostname = device.old_hostname
                is_reachable = device.old_is_reachable

            # 只對可達的設備生成版本記錄
            if not hostname or not is_reachable:
                continue

            # 創建 CollectionBatch
            batch = CollectionBatch(
                collection_type="version",
                switch_hostname=hostname,
                phase=phase,
                maintenance_id=maintenance_id,
                collected_at=now,
                raw_data=str({"mock": True}),
                item_count=1,
            )
            session.add(batch)
            await session.flush()  # 獲取 batch.id

            # 決定版本：80% 機率符合期望，20% 機率隨機
            if hostname in exp_map and random.random() < 0.8:
                version = exp_map[hostname]
            else:
                version = random.choice(VERSIONS)

            # 創建 VersionRecord
            record = VersionRecord(
                batch_id=batch.id,
                switch_hostname=hostname,
                phase=phase,
                maintenance_id=maintenance_id,
                collected_at=now,
                version=version,
                model=f"Catalyst {random.choice(['9300', '9400', '9500'])}",
                serial_number=f"SN{random.randint(100000, 999999)}",
                uptime=f"{random.randint(1, 365)} days",
            )
            records.append(record)

        return records

    async def _get_valid_switch_hostnames(
        self,
        maintenance_id: str,
        phase: MaintenancePhase,
        session: AsyncSession,
    ) -> list[str]:
        """獲取有效的交換機 hostname 列表。

        根據 phase 決定使用 old_hostname 或 new_hostname。
        只返回可達 (is_reachable=True) 的設備，與真實採集邏輯一致。
        """
        stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        devices = result.scalars().all()

        if phase == MaintenancePhase.OLD:
            # OLD 階段：只返回舊設備可達的 hostname
            return [
                d.old_hostname for d in devices
                if d.old_hostname and d.old_is_reachable
            ]
        else:
            # NEW 階段：只返回新設備可達的 hostname
            return [
                d.new_hostname for d in devices
                if d.new_hostname and d.is_reachable
            ]

    def _create_varied_record(
        self,
        base: ClientRecord,
        collected_at: datetime,
    ) -> ClientRecord:
        """基於現有記錄創建變化版本。

        以一定機率隨機套用各種變化，模擬真實網路環境。
        """
        # 複製基本屬性
        speed = base.speed
        duplex = base.duplex
        link_status = base.link_status
        ping_reachable = base.ping_reachable
        interface_name = base.interface_name
        vlan_id = base.vlan_id

        # 隨機套用變化
        if random.random() < self.SPEED_CHANGE_PROB:
            speed = random.choice(self.SPEEDS)

        if random.random() < self.DUPLEX_CHANGE_PROB:
            duplex = random.choice(self.DUPLEXES)

        if random.random() < self.LINK_DOWN_PROB:
            link_status = "down" if link_status == "up" else "up"

        if random.random() < self.PING_FAIL_PROB:
            ping_reachable = not ping_reachable if ping_reachable is not None else False

        if random.random() < self.PORT_CHANGE_PROB:
            # 變更埠口編號
            port_num = random.randint(1, 48)
            interface_name = f"GE1/0/{port_num}"

        if random.random() < self.VLAN_CHANGE_PROB:
            # VLAN 變化（加減一個小數值）
            if vlan_id:
                vlan_id = vlan_id + random.choice([-1, 1, 100, -100])
                vlan_id = max(1, min(4094, vlan_id))  # 確保在有效範圍內

        return ClientRecord(
            maintenance_id=base.maintenance_id,
            phase=base.phase,
            collected_at=collected_at,
            mac_address=base.mac_address,
            ip_address=base.ip_address,
            switch_hostname=base.switch_hostname,
            interface_name=interface_name,
            vlan_id=vlan_id,
            speed=speed,
            duplex=duplex,
            link_status=link_status,
            ping_reachable=ping_reachable,
            acl_passes=base.acl_passes,
        )

    def _create_new_record(
        self,
        mac_entry: MaintenanceMacList,
        maintenance_id: str,
        phase: MaintenancePhase,
        collected_at: datetime,
        valid_hostnames: list[str] | None = None,
    ) -> ClientRecord:
        """從 MAC 清單條目創建新記錄。

        使用 MaintenanceDeviceList 中的有效交換機 hostname。
        """
        # 從有效的交換機列表中隨機選擇
        if valid_hostnames:
            switch_hostname = random.choice(valid_hostnames)
        else:
            # Fallback: 如果沒有有效列表，使用舊的隨機生成邏輯
            switch_num = random.randint(11, 34)
            category = self._tenant_to_category(mac_entry.tenant_group)
            switch_hostname = f"SW-NEW-{switch_num:03d}-{category}"

        return ClientRecord(
            maintenance_id=maintenance_id,
            phase=phase,
            collected_at=collected_at,
            mac_address=mac_entry.mac_address,
            ip_address=mac_entry.ip_address,
            switch_hostname=switch_hostname,
            interface_name=f"GE1/0/{random.randint(1, 48)}",
            vlan_id=self._tenant_to_vlan(mac_entry.tenant_group),
            speed=random.choice(["1G", "1000M"]),
            duplex="full",
            link_status="up",
            ping_reachable=True,
            acl_passes=True,
        )

    def _tenant_to_category(self, tenant_group: TenantGroup | None) -> str:
        """將 TenantGroup 轉換為設備類別。"""
        if tenant_group is None:
            return "EQP"
        return self.TENANT_TO_CATEGORY.get(tenant_group, "EQP")

    def _tenant_to_vlan(self, tenant_group: TenantGroup | None) -> int:
        """將 TenantGroup 轉換為 VLAN ID。"""
        if tenant_group is None:
            return 10
        return self.TENANT_TO_VLAN.get(tenant_group, 10)


# Singleton instance
_mock_data_generator: MockDataGenerator | None = None


def get_mock_data_generator() -> MockDataGenerator:
    """獲取 MockDataGenerator 單例。"""
    global _mock_data_generator
    if _mock_data_generator is None:
        _mock_data_generator = MockDataGenerator()
    return _mock_data_generator
