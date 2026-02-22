"""Mock data generator for testing data flows.

生成隨機但真實的 Mock 資料，用於測試整體資料流。
模擬真實的設備遷移情境：MAC 從 OLD 設備遷移到對應的 NEW 設備。
"""
from __future__ import annotations

import hashlib
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
from app.core.enums import TenantGroup


class MockDataGenerator:
    """生成隨機但真實的 Mock 資料。

    模擬真實網路環境：
    - 每個 MAC 有固定的「原始位置」（基於 hash 決定的 OLD 設備和 port）
    - 歲修後，MAC 應出現在對應的 NEW 設備（根據設備對應清單）
    - 小機率產生異常情況以測試比對邏輯
    """

    # ========== 異常機率配置（用於測試比對邏輯）==========
    NOT_DETECTED_PROB = 0.03      # 3% 機率：MAC 突然消失（未偵測）
    WRONG_SWITCH_PROB = 0.05      # 5% 機率：MAC 出現在錯誤的交換機
    WRONG_PORT_PROB = 0.02        # 2% 機率：MAC 在對的交換機但錯的 port

    # ========== 一般變化機率 ==========
    SPEED_CHANGE_PROB = 0.05      # 5% 機率速度變化
    DUPLEX_CHANGE_PROB = 0.02     # 2% 機率雙工變化
    LINK_DOWN_PROB = 0.03         # 3% 機率連結斷線
    PING_FAIL_PROB = 0.05         # 5% 機率 ping 失敗
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

    def _mac_to_deterministic_index(self, mac_address: str, list_length: int) -> int:
        """根據 MAC 地址計算確定性的索引。

        同一個 MAC 永遠會得到同一個索引，確保分配的一致性。
        """
        if list_length <= 0:
            return 0
        # 使用 MD5 hash 來獲得確定性但分散的結果
        mac_hash = hashlib.md5(mac_address.upper().encode()).hexdigest()
        return int(mac_hash, 16) % list_length

    def _mac_to_deterministic_port(self, mac_address: str) -> int:
        """根據 MAC 地址計算確定性的 port 號（1-48）。"""
        mac_hash = hashlib.md5(f"port_{mac_address.upper()}".encode()).hexdigest()
        return (int(mac_hash, 16) % 48) + 1

    async def generate_client_records(
        self,
        maintenance_id: str,
        is_old: bool,
        session: AsyncSession,
        base_records: list[ClientRecord] | None = None,
    ) -> list[ClientRecord]:
        """
        生成 ClientRecord 資料。

        模擬真實遷移情境：
        - is_old=True：MAC 在其「原始」OLD 設備上
        - is_old=False：MAC 應在對應的 NEW 設備上（根據設備對應清單）
        - 小機率產生異常（未偵測、位置錯誤）以測試比對邏輯
        - **重要**：只有可達的設備才能偵測到 MAC

        Args:
            maintenance_id: 歲修 ID
            is_old: 是否為 OLD 階段
            session: DB session
            base_records: 基準記錄（可選，用於產生變化）

        Returns:
            生成的 ClientRecord 列表
        """
        now = datetime.now(timezone.utc)
        records = []

        # 獲取設備對應清單（包含 old -> new 的映射和可達性狀態）
        device_mapping = await self._get_device_mapping(maintenance_id, session)

        # 構建可達設備集合（根據 is_old 決定）
        reachable_devices = self._get_reachable_devices(device_mapping, is_old=is_old)

        if base_records:
            # 基於現有記錄產生變化
            for base in base_records:
                record = self._create_varied_record(
                    base, now, device_mapping, is_old, reachable_devices
                )
                if record:  # None 表示該 MAC 「消失」了
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
                    mac_entry, maintenance_id, is_old, now,
                    device_mapping, reachable_devices,
                )
                if record:  # None 表示該 MAC 「消失」了
                    records.append(record)

        return records

    async def generate_client_records_realistic(
        self,
        maintenance_id: str,
        has_converged: bool,
        reachable_devices: set[str],
        session: AsyncSession,
        base_records: list[ClientRecord] | None = None,
        can_ping: bool = True,
    ) -> list[ClientRecord]:
        """
        生成 ClientRecord 資料（更真實的模擬）。

        模擬真實情境：
        - MAC 物理位置由 has_converged 決定
        - has_converged=True: MAC 已遷移到 NEW 設備
        - has_converged=False: MAC 仍在 OLD 設備上

        Args:
            maintenance_id: 歲修 ID
            has_converged: MAC 是否已收斂到 NEW 設備
            reachable_devices: 所有可達設備的集合（包含 OLD 和 NEW）
            session: DB session
            base_records: 基準記錄（可選，用於產生變化）
            can_ping: 是否可執行 ping（決定 ping_reachable 是否有值）
                      True → ping 可執行，結果為 True/False
                      False → ping 未執行，結果為 None

        Returns:
            生成的 ClientRecord 列表
        """
        now = datetime.now(timezone.utc)
        records = []

        # 獲取設備對應清單
        device_mapping = await self._get_device_mapping(maintenance_id, session)

        if base_records:
            # 基於現有記錄產生變化
            for base in base_records:
                record = self._create_varied_record_realistic(
                    base, now, device_mapping,
                    has_converged, reachable_devices,
                    can_ping=can_ping,
                )
                if record:
                    records.append(record)
        else:
            # 從 MAC 清單產生新記錄
            stmt = select(MaintenanceMacList).where(
                MaintenanceMacList.maintenance_id == maintenance_id
            )
            result = await session.execute(stmt)
            mac_list = result.scalars().all()

            for mac_entry in mac_list:
                record = self._create_new_record_realistic(
                    mac_entry, maintenance_id,
                    has_converged,
                    now, device_mapping, reachable_devices,
                    can_ping=can_ping,
                )
                if record:
                    records.append(record)

        return records

    def _get_reachable_devices(
        self,
        device_mapping: dict[str, dict],
        is_old: bool = False,
    ) -> set[str]:
        """根據 is_old 獲取可達設備的集合。

        Args:
            device_mapping: 設備對應清單
            is_old: 是否為 OLD 階段

        Returns:
            可達設備的 hostname 集合
        """
        reachable = set()
        devices = device_mapping.get('_devices', [])

        for d in devices:
            if is_old:
                if d.old_hostname:
                    reachable.add(d.old_hostname)
            else:
                if d.new_hostname:
                    reachable.add(d.new_hostname)

        return reachable

    async def _get_device_mapping(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> dict[str, dict]:
        """獲取設備對應清單。

        Returns:
            dict: {
                old_hostname: {
                    'new_hostname': str,
                    'old_hostname': str,
                },
                ...
            }
            以及一個特殊的 '_all_devices' 鍵包含所有設備列表
        """
        stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        devices = result.scalars().all()

        mapping = {
            '_old_hostnames': [],
            '_new_hostnames': [],
            '_devices': devices,
        }

        for d in devices:
            if d.old_hostname:
                mapping['_old_hostnames'].append(d.old_hostname)
                mapping[d.old_hostname] = {
                    'new_hostname': d.new_hostname,
                    'old_hostname': d.old_hostname,
                }
            if d.new_hostname:
                mapping['_new_hostnames'].append(d.new_hostname)

        return mapping

    async def generate_version_records(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> list[VersionRecord]:
        """
        生成 VersionRecord 資料。

        根據 MaintenanceDeviceList 中的設備，產生版本採集記錄。
        如果設備有 VersionExpectation，會以一定機率符合期望版本。
        只對 NEW 設備生成記錄。

        Args:
            maintenance_id: 歲修 ID
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
            hostname = device.new_hostname
            if not hostname:
                continue

            # 創建 CollectionBatch
            batch = CollectionBatch(
                collection_type="version",
                switch_hostname=hostname,
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
        is_old: bool,
        session: AsyncSession,
        require_reachable: bool = False,
    ) -> list[str]:
        """獲取有效的交換機 hostname 列表。

        根據 is_old 決定使用 old_hostname 或 new_hostname。

        Args:
            maintenance_id: 歲修 ID
            is_old: 是否為 OLD 階段
            session: DB session
            require_reachable: 是否只返回可達設備（預設 False，用於 Mock 資料）
        """
        stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        devices = result.scalars().all()

        if is_old:
            return [d.old_hostname for d in devices if d.old_hostname]
        else:
            return [d.new_hostname for d in devices if d.new_hostname]

    def _create_varied_record(
        self,
        base: ClientRecord,
        collected_at: datetime,
        device_mapping: dict[str, dict],
        is_old: bool = False,
        reachable_devices: set[str] | None = None,
    ) -> ClientRecord | None:
        """基於現有記錄創建變化版本。

        模擬真實情境的變化，包含小機率異常。
        **重要**：只有當目標設備可達時才會生成記錄。

        Args:
            base: 基準記錄
            collected_at: 採集時間
            device_mapping: 設備對應清單
            is_old: 是否為 OLD 階段
            reachable_devices: 可達設備的 hostname 集合

        Returns:
            ClientRecord 或 None（表示 MAC 消失/未偵測）
        """
        # 複製基本屬性
        speed = base.speed
        duplex = base.duplex
        link_status = base.link_status
        ping_reachable = base.ping_reachable
        interface_name = base.interface_name
        vlan_id = base.vlan_id
        switch_hostname = base.switch_hostname

        # 決定正確的交換機位置
        # 如果是 NEW 階段，應該在對應的 NEW 設備上
        if not is_old and base.switch_hostname:
            # 檢查當前是否在 OLD 設備上
            if base.switch_hostname in device_mapping:
                # 應該遷移到對應的 NEW 設備
                mapping = device_mapping[base.switch_hostname]
                correct_switch = mapping.get('new_hostname', base.switch_hostname)
                switch_hostname = correct_switch

        # **關鍵檢查**：目標設備是否可達
        # 如果設備不可達，就採集不到這個 MAC，返回 None
        if reachable_devices is not None and switch_hostname not in reachable_devices:
            return None

        # 小機率：MAC 消失（未偵測）- 即使設備可達也有機率採集不到
        if random.random() < self.NOT_DETECTED_PROB:
            return None

        # 小機率：出現在錯誤的交換機
        if random.random() < self.WRONG_SWITCH_PROB:
            all_switches = device_mapping.get('_new_hostnames', [])
            if all_switches and len(all_switches) > 1:
                # 隨機選一個「錯誤」的交換機
                wrong_switches = [s for s in all_switches if s != switch_hostname]
                if wrong_switches:
                    switch_hostname = random.choice(wrong_switches)

        # 小機率：錯誤的 port（但在對的交換機）
        if random.random() < self.WRONG_PORT_PROB:
            wrong_port = random.randint(1, 48)
            interface_name = f"GE1/0/{wrong_port}"

        # 一般變化
        if random.random() < self.SPEED_CHANGE_PROB:
            speed = random.choice(self.SPEEDS)

        if random.random() < self.DUPLEX_CHANGE_PROB:
            duplex = random.choice(self.DUPLEXES)

        if random.random() < self.LINK_DOWN_PROB:
            link_status = "down" if link_status == "up" else "up"

        if random.random() < self.PING_FAIL_PROB:
            ping_reachable = not ping_reachable if ping_reachable is not None else False

        if random.random() < self.VLAN_CHANGE_PROB:
            if vlan_id:
                vlan_id = vlan_id + random.choice([-1, 1, 100, -100])
                vlan_id = max(1, min(4094, vlan_id))

        return ClientRecord(
            maintenance_id=base.maintenance_id,
            collected_at=collected_at,
            mac_address=base.mac_address,
            ip_address=base.ip_address,
            switch_hostname=switch_hostname,
            interface_name=interface_name,
            vlan_id=vlan_id,
            speed=speed,
            duplex=duplex,
            link_status=link_status,
            ping_reachable=ping_reachable,
        )

    def _create_new_record(
        self,
        mac_entry: MaintenanceMacList,
        maintenance_id: str,
        is_old: bool,
        collected_at: datetime,
        device_mapping: dict[str, dict],
        reachable_devices: set[str] | None = None,
    ) -> ClientRecord | None:
        """從 MAC 清單條目創建新記錄。

        根據 MAC 地址確定性地分配到特定設備和 port。
        模擬真實情境：MAC 有固定的原始位置，歲修後遷移到對應的新設備。
        **重要**：只有當目標設備可達時才會生成記錄。

        Args:
            mac_entry: MAC 清單條目
            maintenance_id: 歲修 ID
            is_old: 是否為 OLD 階段
            collected_at: 採集時間
            device_mapping: 設備對應清單
            reachable_devices: 可達設備的 hostname 集合

        Returns:
            ClientRecord 或 None（表示 MAC 消失/未偵測）
        """
        mac_address = mac_entry.mac_address or ""

        # 根據 MAC 的 hash 確定性地選擇「原始」OLD 設備
        old_hostnames = device_mapping.get('_old_hostnames', [])
        new_hostnames = device_mapping.get('_new_hostnames', [])

        if not old_hostnames:
            # 沒有設備清單，使用 fallback
            switch_num = self._mac_to_deterministic_index(mac_address, 24) + 11
            category = self._tenant_to_category(mac_entry.tenant_group)
            switch_hostname = f"SW-NEW-{switch_num:03d}-{category}"
        else:
            # 確定性選擇 OLD 設備
            old_index = self._mac_to_deterministic_index(mac_address, len(old_hostnames))
            original_old_hostname = old_hostnames[old_index]

            if is_old:
                # OLD 階段：MAC 在原始 OLD 設備上
                switch_hostname = original_old_hostname
            else:
                # NEW 階段：MAC 應在對應的 NEW 設備上
                if original_old_hostname in device_mapping:
                    mapping = device_mapping[original_old_hostname]
                    switch_hostname = mapping.get('new_hostname', original_old_hostname)
                elif new_hostnames:
                    # Fallback: 如果沒有對應，使用 hash 選擇 NEW 設備
                    new_index = self._mac_to_deterministic_index(mac_address, len(new_hostnames))
                    switch_hostname = new_hostnames[new_index]
                else:
                    switch_hostname = original_old_hostname

        # **關鍵檢查**：目標設備是否可達
        # 如果設備不可達，就採集不到這個 MAC，返回 None
        if reachable_devices is not None and switch_hostname not in reachable_devices:
            return None

        # 小機率：MAC 消失（未偵測）- 即使設備可達也有機率採集不到
        if random.random() < self.NOT_DETECTED_PROB:
            return None

        # 確定性選擇 port
        port_num = self._mac_to_deterministic_port(mac_address)
        interface_name = f"GE1/0/{port_num}"

        # 小機率：出現在錯誤的交換機
        if random.random() < self.WRONG_SWITCH_PROB:
            all_switches = new_hostnames if not is_old else old_hostnames
            if all_switches and len(all_switches) > 1:
                wrong_switches = [s for s in all_switches if s != switch_hostname]
                if wrong_switches:
                    switch_hostname = random.choice(wrong_switches)

        # 小機率：錯誤的 port
        if random.random() < self.WRONG_PORT_PROB:
            wrong_port = random.randint(1, 48)
            interface_name = f"GE1/0/{wrong_port}"

        return ClientRecord(
            maintenance_id=maintenance_id,
            collected_at=collected_at,
            mac_address=mac_entry.mac_address,
            ip_address=mac_entry.ip_address,
            switch_hostname=switch_hostname,
            interface_name=interface_name,
            vlan_id=self._tenant_to_vlan(mac_entry.tenant_group),
            speed=random.choice(["1G", "1000M"]),
            duplex="full",
            link_status="up",
            ping_reachable=True,
        )

    def _create_new_record_realistic(
        self,
        mac_entry: MaintenanceMacList,
        maintenance_id: str,
        has_converged: bool,
        collected_at: datetime,
        device_mapping: dict[str, dict],
        reachable_devices: set[str],
        can_ping: bool = True,
    ) -> ClientRecord | None:
        """從 MAC 清單條目創建新記錄（更真實的模擬）。

        模擬真實情境：
        - has_converged 決定 MAC 物理上在 OLD 還是 NEW 設備
        - has_converged=True: MAC 已遷移到 NEW 設備
        - has_converged=False: MAC 仍在 OLD 設備上
        - 檢查該設備是否在 reachable_devices 中（可被查詢到）
        - can_ping 決定 ping_reachable 是否有值

        Args:
            mac_entry: MAC 清單條目
            maintenance_id: 歲修 ID
            has_converged: MAC 是否已收斂到 NEW 設備
            collected_at: 採集時間
            device_mapping: 設備對應清單
            reachable_devices: 所有可達設備的集合
            can_ping: 是否可執行 ping

        Returns:
            ClientRecord 或 None（表示 MAC 消失/設備不可達）
        """
        mac_address = mac_entry.mac_address or ""

        # 根據 MAC 的 hash 確定性地選擇「原始」OLD 設備
        old_hostnames = device_mapping.get('_old_hostnames', [])
        new_hostnames = device_mapping.get('_new_hostnames', [])

        if not old_hostnames:
            # 沒有設備清單，使用 fallback
            switch_num = self._mac_to_deterministic_index(mac_address, 24) + 11
            category = self._tenant_to_category(mac_entry.tenant_group)
            switch_hostname = f"SW-NEW-{switch_num:03d}-{category}"
        else:
            # 確定性選擇 OLD 設備（這是 MAC 的「原始」位置）
            old_index = self._mac_to_deterministic_index(mac_address, len(old_hostnames))
            original_old_hostname = old_hostnames[old_index]

            if not has_converged:
                # MAC 物理上在 OLD 設備
                switch_hostname = original_old_hostname
            else:
                # MAC 物理上在 NEW 設備（根據設備對應）
                if original_old_hostname in device_mapping:
                    mapping = device_mapping[original_old_hostname]
                    switch_hostname = mapping.get('new_hostname', original_old_hostname)
                elif new_hostnames:
                    new_index = self._mac_to_deterministic_index(mac_address, len(new_hostnames))
                    switch_hostname = new_hostnames[new_index]
                else:
                    switch_hostname = original_old_hostname

        # **關鍵檢查**：目標設備是否可達
        # 如果設備不可達，就採集不到這個 MAC，返回 None
        if switch_hostname not in reachable_devices:
            return None

        # 小機率：MAC 消失（未偵測）
        if random.random() < self.NOT_DETECTED_PROB:
            return None

        # 確定性選擇 port
        port_num = self._mac_to_deterministic_port(mac_address)
        interface_name = f"GE1/0/{port_num}"

        # 小機率：出現在錯誤的交換機（從可達設備中選）
        if random.random() < self.WRONG_SWITCH_PROB:
            wrong_switches = [s for s in reachable_devices if s != switch_hostname]
            if wrong_switches:
                switch_hostname = random.choice(list(wrong_switches))

        # 小機率：錯誤的 port
        if random.random() < self.WRONG_PORT_PROB:
            wrong_port = random.randint(1, 48)
            interface_name = f"GE1/0/{wrong_port}"

        # ping_reachable 取決於是否可執行 ping：
        # - can_ping=True → ping 可執行 → True（含小機率 False）
        # - can_ping=False → ping 未執行 → None
        if can_ping:
            ping_reachable: bool | None = random.random() >= self.PING_FAIL_PROB
        else:
            ping_reachable = None

        return ClientRecord(
            maintenance_id=maintenance_id,
            collected_at=collected_at,
            mac_address=mac_entry.mac_address,
            ip_address=mac_entry.ip_address,
            switch_hostname=switch_hostname,
            interface_name=interface_name,
            vlan_id=self._tenant_to_vlan(mac_entry.tenant_group),
            speed=random.choice(["1G", "1000M"]),
            duplex="full",
            link_status="up",
            ping_reachable=ping_reachable,
        )

    def _create_varied_record_realistic(
        self,
        base: ClientRecord,
        collected_at: datetime,
        device_mapping: dict[str, dict],
        has_converged: bool,
        reachable_devices: set[str],
        can_ping: bool = True,
    ) -> ClientRecord | None:
        """基於現有記錄創建變化版本（更真實的模擬）。

        Args:
            base: 基準記錄
            collected_at: 採集時間
            device_mapping: 設備對應清單
            has_converged: MAC 是否已收斂到 NEW 設備
            reachable_devices: 所有可達設備的集合
            can_ping: 是否可執行 ping

        Returns:
            ClientRecord 或 None（表示 MAC 消失/設備不可達）
        """
        # 決定 MAC 當前應該在哪個設備上
        mac_address = base.mac_address or ""
        old_hostnames = device_mapping.get('_old_hostnames', [])
        new_hostnames = device_mapping.get('_new_hostnames', [])

        if old_hostnames:
            old_index = self._mac_to_deterministic_index(mac_address, len(old_hostnames))
            original_old_hostname = old_hostnames[old_index]

            if not has_converged:
                switch_hostname = original_old_hostname
            else:
                if original_old_hostname in device_mapping:
                    mapping = device_mapping[original_old_hostname]
                    switch_hostname = mapping.get('new_hostname', original_old_hostname)
                else:
                    switch_hostname = base.switch_hostname
        else:
            switch_hostname = base.switch_hostname

        # 檢查設備可達性
        if switch_hostname not in reachable_devices:
            return None

        # 小機率：MAC 消失
        if random.random() < self.NOT_DETECTED_PROB:
            return None

        # 複製其他屬性
        speed = base.speed
        duplex = base.duplex
        link_status = base.link_status
        interface_name = base.interface_name
        vlan_id = base.vlan_id

        # ping_reachable 取決於是否可執行 ping：
        # - can_ping=False → 強制 None（ping 未執行）
        # - can_ping=True → 從 base 繼承，含小機率翻轉
        if not can_ping:
            ping_reachable: bool | None = None
        else:
            ping_reachable = base.ping_reachable
            if random.random() < self.PING_FAIL_PROB:
                ping_reachable = not ping_reachable if ping_reachable is not None else False

        # 小機率變化
        if random.random() < self.WRONG_SWITCH_PROB:
            wrong_switches = [s for s in reachable_devices if s != switch_hostname]
            if wrong_switches:
                switch_hostname = random.choice(list(wrong_switches))

        if random.random() < self.WRONG_PORT_PROB:
            interface_name = f"GE1/0/{random.randint(1, 48)}"

        if random.random() < self.SPEED_CHANGE_PROB:
            speed = random.choice(self.SPEEDS)

        if random.random() < self.DUPLEX_CHANGE_PROB:
            duplex = random.choice(self.DUPLEXES)

        if random.random() < self.LINK_DOWN_PROB:
            link_status = "down" if link_status == "up" else "up"

        return ClientRecord(
            maintenance_id=base.maintenance_id,
            collected_at=collected_at,
            mac_address=base.mac_address,
            ip_address=base.ip_address,
            switch_hostname=switch_hostname,
            interface_name=interface_name,
            vlan_id=vlan_id,
            speed=speed,
            duplex=duplex,
            link_status=link_status,
            ping_reachable=ping_reachable,
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
