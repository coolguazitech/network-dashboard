"""
Client comparison service.

比較客戶端在不同時間點的變化。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClientRecord, ClientComparison
from app.core.timezone import now_utc

# 快照標記的特殊 MAC 地址（用於在沒有實際資料時記錄時間點）
SNAPSHOT_MARKER_MAC = "__MARKER__"


class ClientComparisonService:
    """客戶端比較服務。

    比較同一個 MAC 地址在不同時間點的變化情況，包括：
    - 拓樸角色（access/trunk/uplink）
    - 連接的交換機和埠口
    - 連接速率、雙工模式
    - Ping 可達性和延遲
    """
    
    def __init__(self):
        self._reference_clients_cache = None
    
    async def generate_comparisons(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> list[ClientComparison]:
        """
        生成客戶端比較結果。

        基於 MaintenanceMacList 中的 MAC 清單進行比較，確保：
        1. 只比較歲修設定中的 MAC
        2. 清單中的 MAC 若在 NEW 階段未找到，標記為 undetected (critical)
        3. 資料數量與歲修設定一致
        """
        from app.db.models import MaintenanceDeviceList, MaintenanceMacList
        from app.core.enums import ClientDetectionStatus

        # 1. 從 MaintenanceMacList 載入 MAC 清單及偵測狀態
        mac_stmt = select(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        mac_result = await session.execute(mac_stmt)
        mac_records = mac_result.scalars().all()

        # 建立 MAC 到偵測狀態的對應
        mac_list = [m.mac_address.upper() for m in mac_records]
        mac_detection_status: dict[str, ClientDetectionStatus] = {
            m.mac_address.upper(): m.detection_status for m in mac_records
        }

        if not mac_list:
            # 如果沒有 MAC 清單，回退到原有邏輯（從 ClientRecord 取）
            return await self._generate_comparisons_legacy(
                maintenance_id, session,
            )

        # 2. 查詢 OLD 階段的記錄，按 MAC 地址分組，只保留最新的
        old_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
            )
            .order_by(ClientRecord.mac_address, ClientRecord.collected_at.desc())
        )
        old_result = await session.execute(old_stmt)
        old_records = old_result.scalars().all()

        # 按 MAC 地址分組（大寫），只保留最新記錄（排除快照標記）
        old_by_mac: dict[str, ClientRecord] = {}
        for record in old_records:
            mac_upper = record.mac_address.upper()
            if mac_upper == SNAPSHOT_MARKER_MAC:
                continue  # 跳過快照標記
            if mac_upper not in old_by_mac:
                old_by_mac[mac_upper] = record

        # 3. 查詢 NEW 階段的記錄，按 MAC 地址分組，只保留最新的
        new_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
            )
            .order_by(ClientRecord.mac_address, ClientRecord.collected_at.desc())
        )
        new_result = await session.execute(new_stmt)
        new_records = new_result.scalars().all()

        # 按 MAC 地址分組（大寫），只保留最新記錄（排除快照標記）
        new_by_mac: dict[str, ClientRecord] = {}
        for record in new_records:
            mac_upper = record.mac_address.upper()
            if mac_upper == SNAPSHOT_MARKER_MAC:
                continue  # 跳過快照標記
            if mac_upper not in new_by_mac:
                new_by_mac[mac_upper] = record

        # 4. 載入設備對應
        dev_stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        dev_result = await session.execute(dev_stmt)
        device_mappings_list = dev_result.scalars().all()
        device_mappings: dict[str, str] = {}
        for dm in device_mappings_list:
            device_mappings[dm.old_hostname.lower()] = dm.new_hostname

        # 5. 基於 MAC 清單生成比較結果（確保數量一致）
        comparisons = []

        for mac in mac_list:
            old_record = old_by_mac.get(mac)
            new_record = new_by_mac.get(mac)

            # 建立比較記錄
            comparison = ClientComparison(
                maintenance_id=maintenance_id,
                collected_at=now_utc(),
                mac_address=mac,
            )

            # 添加 OLD（舊設備）數據
            if old_record:
                comparison.old_ip_address = old_record.ip_address
                comparison.old_switch_hostname = old_record.switch_hostname
                comparison.old_interface_name = old_record.interface_name
                comparison.old_vlan_id = old_record.vlan_id
                comparison.old_speed = old_record.speed
                comparison.old_duplex = old_record.duplex
                comparison.old_link_status = old_record.link_status
                comparison.old_ping_reachable = old_record.ping_reachable

            # 添加 NEW（新設備）數據
            # 直接使用 ClientRecord 判斷是否有數據
            # 如果 switch_hostname 為 None，代表該 MAC 未被偵測到（None 記錄）
            if new_record and new_record.switch_hostname is not None:
                comparison.new_ip_address = new_record.ip_address
                comparison.new_switch_hostname = new_record.switch_hostname
                comparison.new_interface_name = new_record.interface_name
                comparison.new_vlan_id = new_record.vlan_id
                comparison.new_speed = new_record.speed
                comparison.new_duplex = new_record.duplex
                comparison.new_link_status = new_record.link_status
                comparison.new_ping_reachable = new_record.ping_reachable

            # 使用 _compare_records 處理單邊未偵測情況
            comparison = self._compare_records(comparison, device_mappings)
            comparisons.append(comparison)

        return comparisons

    async def _generate_comparisons_legacy(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> list[ClientComparison]:
        """
        Legacy 比較生成方法（無 MaintenanceMacList 時使用）。

        從 ClientRecord 動態獲取所有 MAC 來生成比較。
        這是為了向後兼容沒有設定 MAC 清單的歲修。
        """
        from app.db.models import MaintenanceDeviceList

        # 查詢 OLD 階段的記錄
        old_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
            )
            .order_by(
                ClientRecord.mac_address,
                ClientRecord.collected_at.desc(),
            )
        )
        old_result = await session.execute(old_stmt)
        old_records = old_result.scalars().all()

        old_by_mac: dict[str, ClientRecord] = {}
        for record in old_records:
            mac_upper = record.mac_address.upper()
            if mac_upper == SNAPSHOT_MARKER_MAC:
                continue  # 跳過快照標記
            if mac_upper not in old_by_mac:
                old_by_mac[mac_upper] = record

        # 查詢 NEW 階段的記錄
        new_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
            )
            .order_by(
                ClientRecord.mac_address,
                ClientRecord.collected_at.desc(),
            )
        )
        new_result = await session.execute(new_stmt)
        new_records = new_result.scalars().all()

        new_by_mac: dict[str, ClientRecord] = {}
        for record in new_records:
            mac_upper = record.mac_address.upper()
            if mac_upper == SNAPSHOT_MARKER_MAC:
                continue  # 跳過快照標記
            if mac_upper not in new_by_mac:
                new_by_mac[mac_upper] = record

        # 載入設備對應
        dev_stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        dev_result = await session.execute(dev_stmt)
        device_mappings_list = dev_result.scalars().all()
        device_mappings: dict[str, str] = {}
        for dm in device_mappings_list:
            device_mappings[dm.old_hostname.lower()] = dm.new_hostname

        # 生成比較結果
        comparisons = []
        all_macs = set(old_by_mac.keys()) | set(new_by_mac.keys())

        for mac in all_macs:
            old_record = old_by_mac.get(mac)
            new_record = new_by_mac.get(mac)

            comparison = ClientComparison(
                maintenance_id=maintenance_id,
                collected_at=now_utc(),
                mac_address=mac,
            )

            if old_record:
                comparison.old_ip_address = old_record.ip_address
                comparison.old_switch_hostname = old_record.switch_hostname
                comparison.old_interface_name = old_record.interface_name
                comparison.old_vlan_id = old_record.vlan_id
                comparison.old_speed = old_record.speed
                comparison.old_duplex = old_record.duplex
                comparison.old_link_status = old_record.link_status
                comparison.old_ping_reachable = old_record.ping_reachable

            if new_record:
                comparison.new_ip_address = new_record.ip_address
                comparison.new_switch_hostname = new_record.switch_hostname
                comparison.new_interface_name = new_record.interface_name
                comparison.new_vlan_id = new_record.vlan_id
                comparison.new_speed = new_record.speed
                comparison.new_duplex = new_record.duplex
                comparison.new_link_status = new_record.link_status
                comparison.new_ping_reachable = new_record.ping_reachable

            comparison = self._compare_records(comparison, device_mappings)
            comparisons.append(comparison)

        return comparisons

    def _normalize_speed(self, speed: str | None) -> int | None:
        """將速度值標準化為 Mbps 數值，用於比較。

        支援的格式：
        - "10M", "100M", "1000M" → 對應的 Mbps 數值
        - "1G", "10G", "25G", "40G", "100G" → 轉換為 Mbps
        - "auto" → 特殊處理（不轉換）

        這樣 "1G" 和 "1000M" 會被視為相同的值。
        """
        if speed is None:
            return None

        speed_str = str(speed).strip().upper()

        if not speed_str:
            return None

        # 處理 "auto" 或其他非數值格式
        if speed_str == "AUTO":
            return -1  # 特殊值表示 auto

        # 嘗試解析 G（Gbps）格式
        if speed_str.endswith("G"):
            try:
                num = int(speed_str[:-1])
                return num * 1000  # 轉換為 Mbps
            except ValueError:
                pass

        # 嘗試解析 M（Mbps）格式
        if speed_str.endswith("M"):
            try:
                return int(speed_str[:-1])
            except ValueError:
                pass

        # 嘗試直接解析為數字（假設為 Mbps）
        try:
            return int(speed_str)
        except ValueError:
            pass

        # 無法解析，返回 None
        return None

    def _normalize_duplex(self, duplex: str | None) -> str | None:
        """將雙工值標準化為小寫，用於比較。

        支援的格式（不區分大小寫）：
        - "full", "Full", "FULL" → "full"
        - "half", "Half", "HALF" → "half"
        - "auto", "Auto", "AUTO" → "auto"
        """
        if duplex is None:
            return None
        return duplex.strip().lower() or None

    def _normalize_link_status(self, status: str | None) -> str | None:
        """將連接狀態標準化為小寫，用於比較。

        支援的格式（不區分大小寫）：
        - "up", "Up", "UP" → "up"
        - "down", "Down", "DOWN" → "down"
        """
        if status is None:
            return None
        return status.strip().lower() or None

    def _find_differences(self, comparison: ClientComparison) -> dict[str, Any]:
        """找出比較記錄中的差異。"""
        differences: dict[str, Any] = {}

        # 定義要比較的欄位對（old vs new）
        fields_to_compare = [
            ("old_switch_hostname", "new_switch_hostname", "switch_hostname"),
            ("old_interface_name", "new_interface_name", "interface_name"),
            ("old_vlan_id", "new_vlan_id", "vlan_id"),
            ("old_speed", "new_speed", "speed"),
            ("old_duplex", "new_duplex", "duplex"),
            ("old_link_status", "new_link_status", "link_status"),
            ("old_ping_reachable", "new_ping_reachable", "ping_reachable"),
            ("old_ip_address", "new_ip_address", "ip_address"),
        ]

        for old_field, new_field, field_name in fields_to_compare:
            old_value = getattr(comparison, old_field, None)
            new_value = getattr(comparison, new_field, None)

            # 對於 speed 欄位，使用標準化比較（1G == 1000M）
            if field_name == "speed":
                old_normalized = self._normalize_speed(old_value)
                new_normalized = self._normalize_speed(new_value)

                # 只有都有值且標準化後不同才算變化
                if old_normalized is not None and new_normalized is not None:
                    if old_normalized != new_normalized:
                        differences[field_name] = {
                            "old": old_value,
                            "new": new_value,
                        }
                continue

            # 對於 duplex 欄位，使用標準化比較（full == FULL）
            if field_name == "duplex":
                old_normalized = self._normalize_duplex(old_value)
                new_normalized = self._normalize_duplex(new_value)

                if old_normalized is not None and new_normalized is not None:
                    if old_normalized != new_normalized:
                        differences[field_name] = {
                            "old": old_value,
                            "new": new_value,
                        }
                continue

            # 對於 link_status 欄位，使用標準化比較（up == UP）
            if field_name == "link_status":
                old_normalized = self._normalize_link_status(old_value)
                new_normalized = self._normalize_link_status(new_value)

                if old_normalized is not None and new_normalized is not None:
                    if old_normalized != new_normalized:
                        differences[field_name] = {
                            "old": old_value,
                            "new": new_value,
                        }
                continue

            # 檢查是否有實際變化（忽略 None 值的比較）
            if old_value != new_value:
                # 對於布林值，只有都不為 None 時才比較
                if field_name in ("ping_reachable",):
                    if old_value is not None and new_value is not None and old_value != new_value:
                        differences[field_name] = {
                            "old": old_value,
                            "new": new_value,
                        }
                # 其他字符串字段，只有都不為 None 時才比較
                elif old_value is not None and new_value is not None:
                    differences[field_name] = {
                        "old": old_value,
                        "new": new_value,
                    }

        return differences
    
    def _generate_notes(
        self,
        comparison: ClientComparison,
        differences: dict[str, Any],
    ) -> str:
        """生成比較結果的註釋。"""
        notes = []

        for field_name, change_info in differences.items():
            old_val = change_info.get("old")
            new_val = change_info.get("new")
            notes.append(f"{field_name}: {old_val} → {new_val}")

        return " | ".join(notes) if notes else "未檢測到變化"
    
    async def save_comparisons(
        self,
        comparisons: list[ClientComparison],
        session: AsyncSession,
    ) -> None:
        """保存比較結果到資料庫。"""
        # 先刪除舊的比較結果（如果需要）
        if comparisons:
            maintenance_id = comparisons[0].maintenance_id
            stmt = select(ClientComparison).where(
                ClientComparison.maintenance_id == maintenance_id
            )
            result = await session.execute(stmt)
            old_comparisons = result.scalars().all()
            for old in old_comparisons:
                await session.delete(old)
        
        # 添加新的比較結果
        for comparison in comparisons:
            session.add(comparison)
        
        await session.commit()
    
    async def get_comparisons(
        self,
        maintenance_id: str,
        session: AsyncSession,
        search_text: str | None = None,
        changed_only: bool = False,
        before_time: str | None = None,
    ) -> list[ClientComparison]:
        """
        查詢比較結果。

        支持按 MAC 地址、IP 地址和是否變化進行篩選。
        如果提供 before_time，則動態生成比較結果而非查詢資料庫。
        """
        from sqlalchemy import or_

        # 如果提供了 before_time，動態生成比較結果
        if before_time:
            from datetime import datetime

            before_dt = datetime.fromisoformat(before_time)

            # 獲取最新階段時間
            from sqlalchemy import func
            latest_stmt = (
                select(func.max(ClientRecord.collected_at))
                .where(
                    ClientRecord.maintenance_id == maintenance_id,
                )
            )
            latest_result = await session.execute(latest_stmt)
            latest_time = latest_result.scalar()

            # 生成比較結果
            comparisons = await self._generate_comparisons_at_time(
                maintenance_id=maintenance_id,
                before_time=before_dt,
                after_time=latest_time,
                session=session,
            )

            # 套用篩選
            if search_text:
                search_lower = search_text.lower()
                comparisons = [
                    c for c in comparisons
                    if (c.mac_address and search_lower in c.mac_address.lower())
                    or (c.old_ip_address and search_lower in c.old_ip_address.lower())
                    or (c.new_ip_address and search_lower in c.new_ip_address.lower())
                ]

            if changed_only:
                comparisons = [c for c in comparisons if c.is_changed]

            return comparisons

        # 否則查詢資料庫中保存的比較結果
        stmt = select(ClientComparison).where(
            ClientComparison.maintenance_id == maintenance_id
        )

        if search_text:
            # 搜尋 MAC 地址或 IP 地址（OLD 或 NEW 階段）
            search_pattern = f"%{search_text}%"
            stmt = stmt.where(
                or_(
                    ClientComparison.mac_address.ilike(search_pattern),
                    ClientComparison.old_ip_address.ilike(search_pattern),
                    ClientComparison.new_ip_address.ilike(search_pattern),
                )
            )

        if changed_only:
            stmt = stmt.where(ClientComparison.is_changed == True)

        stmt = stmt.order_by(ClientComparison.collected_at.desc())

        result = await session.execute(stmt)
        return result.scalars().all()
    
    async def get_comparison_summary(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """獲取比較結果的摘要統計。"""
        comparisons = await self.get_comparisons(
            maintenance_id=maintenance_id,
            session=session,
        )

        total = len(comparisons)
        unchanged = sum(1 for c in comparisons if not c.is_changed)
        changed = sum(1 for c in comparisons if c.is_changed)
        undetected = sum(
            1 for c in comparisons if c.severity == "undetected"
        )

        return {
            "total": total,
            "unchanged": unchanged,
            "changed": changed,
            "undetected": undetected,
            "unchanged_rate": (unchanged / total * 100) if total > 0 else 0,
            "changed_rate": (changed / total * 100) if total > 0 else 0,
        }

    async def _generate_comparisons_at_time(
        self,
        maintenance_id: str,
        before_time: datetime,
        after_time: datetime | None,
        session: AsyncSession,
    ) -> list[ClientComparison]:
        """在指定時間點生成比較結果（不保存到資料庫）。

        使用 MaintenanceMacList 作為 MAC 清單基準，確保新加入的 MAC
        即使尚未有偵測記錄也會出現在比較結果中。
        """
        from app.db.models import MaintenanceDeviceList, MaintenanceMacList

        # 載入設備對應（從新的 MaintenanceDeviceList 表格）
        dev_stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        dev_result = await session.execute(dev_stmt)
        device_mappings_list = dev_result.scalars().all()

        # 建立設備對應字典 {old_hostname: new_hostname}（大小寫不敏感）
        device_mappings: dict[str, str] = {}
        for dm in device_mappings_list:
            # 使用小寫 key 以確保比較時大小寫不敏感
            device_mappings[dm.old_hostname.lower()] = dm.new_hostname

        # 載入 MaintenanceMacList 作為 MAC 清單基準
        mac_list_stmt = select(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        mac_list_result = await session.execute(mac_list_stmt)
        mac_records = mac_list_result.scalars().all()

        mac_list = {m.mac_address.upper() for m in mac_records}

        # 查詢在 before_time 時間點的記錄
        before_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.collected_at <= before_time,
            )
            .order_by(
                ClientRecord.mac_address,
                ClientRecord.collected_at.desc(),
            )
        )
        before_result = await session.execute(before_stmt)
        before_records = before_result.scalars().all()

        # 按 MAC 地址分組，只保留最新記錄（排除快照標記）
        before_by_mac = {}
        for record in before_records:
            mac_upper = record.mac_address.upper() if record.mac_address else ""
            if not mac_upper or mac_upper == SNAPSHOT_MARKER_MAC:
                continue  # 跳過空值和快照標記
            if mac_upper not in before_by_mac:
                before_by_mac[mac_upper] = record

        # 查詢在 after_time 時間點的記錄
        if after_time:
            after_stmt = (
                select(ClientRecord)
                .where(
                    ClientRecord.maintenance_id == maintenance_id,
                    ClientRecord.collected_at <= after_time,
                )
                .order_by(
                    ClientRecord.mac_address,
                    ClientRecord.collected_at.desc(),
                )
            )
        else:
            after_stmt = (
                select(ClientRecord)
                .where(
                    ClientRecord.maintenance_id == maintenance_id,
                )
                .order_by(
                    ClientRecord.mac_address,
                    ClientRecord.collected_at.desc(),
                )
            )
        after_result = await session.execute(after_stmt)
        after_records = after_result.scalars().all()

        # 按 MAC 地址分組，只保留最新記錄（排除快照標記）
        after_by_mac = {}
        for record in after_records:
            mac_upper = record.mac_address.upper() if record.mac_address else ""
            if not mac_upper or mac_upper == SNAPSHOT_MARKER_MAC:
                continue  # 跳過空值和快照標記
            if mac_upper not in after_by_mac:
                after_by_mac[mac_upper] = record

        # 生成比較結果
        # 優先使用 MaintenanceMacList，確保刪除的 MAC 不再顯示
        comparisons = []
        if mac_list:
            all_macs = mac_list
        else:
            all_macs = set(before_by_mac.keys()) | set(after_by_mac.keys())

        for mac in all_macs:
            before_record = before_by_mac.get(mac)
            after_record = after_by_mac.get(mac)
            
            comparison = ClientComparison(
                maintenance_id=maintenance_id,
                collected_at=now_utc(),
                mac_address=mac,
            )
            
            # 添加 BEFORE 資料
            if before_record:
                comparison.old_ip_address = before_record.ip_address
                comparison.old_switch_hostname = before_record.switch_hostname
                comparison.old_interface_name = before_record.interface_name
                comparison.old_vlan_id = before_record.vlan_id
                comparison.old_speed = before_record.speed
                comparison.old_duplex = before_record.duplex
                comparison.old_link_status = before_record.link_status
                comparison.old_ping_reachable = before_record.ping_reachable

            # 添加 AFTER 資料
            # 直接使用 ClientRecord 判斷是否有數據
            # 如果 switch_hostname 為 None，代表該 MAC 未被偵測到（None 記錄）
            if after_record and after_record.switch_hostname is not None:
                comparison.new_ip_address = after_record.ip_address
                comparison.new_switch_hostname = after_record.switch_hostname
                comparison.new_interface_name = after_record.interface_name
                comparison.new_vlan_id = after_record.vlan_id
                comparison.new_speed = after_record.speed
                comparison.new_duplex = after_record.duplex
                comparison.new_link_status = after_record.link_status
                comparison.new_ping_reachable = after_record.ping_reachable

            # 比較差異（傳入設備對應）
            comparison = self._compare_records(comparison, device_mappings)
            comparisons.append(comparison)

        return comparisons

    async def _generate_checkpoint_diff(
        self,
        maintenance_id: str,
        checkpoint_time: datetime,
        current_time: datetime | None,
        session: AsyncSession,
    ) -> list[ClientComparison]:
        """比較 NEW 階段內的 Checkpoint vs Current 快照。

        這是新的 Checkpoint 比較邏輯：
        - Before (Checkpoint): NEW 階段在 checkpoint_time 時間點的快照
        - Current: NEW 階段在 current_time（或最新）時間點的快照

        兩者都來自 NEW 階段，用於追蹤歲修過程中設備狀態的變化。
        """
        from app.db.models import MaintenanceDeviceList, MaintenanceMacList

        # 載入設備對應
        dev_stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        dev_result = await session.execute(dev_stmt)
        device_mappings_list = dev_result.scalars().all()
        device_mappings: dict[str, str] = {}
        for dm in device_mappings_list:
            device_mappings[dm.old_hostname.lower()] = dm.new_hostname

        # 載入 MAC 清單
        mac_list_stmt = select(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        mac_list_result = await session.execute(mac_list_stmt)
        mac_records = mac_list_result.scalars().all()

        mac_list = {m.mac_address.upper() for m in mac_records}

        # 查詢 Checkpoint 時間點的記錄
        checkpoint_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.collected_at <= checkpoint_time,
            )
            .order_by(
                ClientRecord.mac_address,
                ClientRecord.collected_at.desc(),
            )
        )
        checkpoint_result = await session.execute(checkpoint_stmt)
        checkpoint_records = checkpoint_result.scalars().all()

        # 按 MAC 分組，保留最接近 checkpoint 時間的記錄（排除快照標記）
        checkpoint_by_mac = {}
        for record in checkpoint_records:
            mac_upper = record.mac_address.upper() if record.mac_address else ""
            if not mac_upper or mac_upper == SNAPSHOT_MARKER_MAC:
                continue  # 跳過空值和快照標記
            if mac_upper not in checkpoint_by_mac:
                checkpoint_by_mac[mac_upper] = record

        # 查詢 Current（最新）時間點的記錄
        if current_time:
            current_stmt = (
                select(ClientRecord)
                .where(
                    ClientRecord.maintenance_id == maintenance_id,
                    ClientRecord.collected_at <= current_time,
                )
                .order_by(
                    ClientRecord.mac_address,
                    ClientRecord.collected_at.desc(),
                )
            )
        else:
            current_stmt = (
                select(ClientRecord)
                .where(
                    ClientRecord.maintenance_id == maintenance_id,
                )
                .order_by(
                    ClientRecord.mac_address,
                    ClientRecord.collected_at.desc(),
                )
            )
        current_result = await session.execute(current_stmt)
        current_records = current_result.scalars().all()

        # 按 MAC 分組，保留最新記錄（排除快照標記）
        current_by_mac = {}
        for record in current_records:
            mac_upper = record.mac_address.upper() if record.mac_address else ""
            if not mac_upper or mac_upper == SNAPSHOT_MARKER_MAC:
                continue  # 跳過空值和快照標記
            if mac_upper not in current_by_mac:
                current_by_mac[mac_upper] = record

        # 生成比較結果
        # 優先使用 MaintenanceMacList 作為基準，確保刪除的 MAC 不再顯示
        # 如果沒有 MaintenanceMacList，才使用 ClientRecord 的聯集
        comparisons = []
        if mac_list:
            all_macs = mac_list
        else:
            all_macs = set(checkpoint_by_mac.keys()) | set(current_by_mac.keys())

        for mac in all_macs:
            checkpoint_record = checkpoint_by_mac.get(mac)
            current_record = current_by_mac.get(mac)

            comparison = ClientComparison(
                maintenance_id=maintenance_id,
                collected_at=now_utc(),
                mac_address=mac,
            )

            # 添加 Checkpoint (Before) 資料
            if checkpoint_record:
                comparison.old_ip_address = checkpoint_record.ip_address
                comparison.old_switch_hostname = checkpoint_record.switch_hostname
                comparison.old_interface_name = checkpoint_record.interface_name
                comparison.old_vlan_id = checkpoint_record.vlan_id
                comparison.old_speed = checkpoint_record.speed
                comparison.old_duplex = checkpoint_record.duplex
                comparison.old_link_status = checkpoint_record.link_status
                comparison.old_ping_reachable = checkpoint_record.ping_reachable

            # 添加 Current 資料
            # 直接使用 ClientRecord 判斷是否有數據
            # 如果 switch_hostname 為 None，代表該 MAC 未被偵測到（None 記錄）
            if current_record and current_record.switch_hostname is not None:
                comparison.new_ip_address = current_record.ip_address
                comparison.new_switch_hostname = current_record.switch_hostname
                comparison.new_interface_name = current_record.interface_name
                comparison.new_vlan_id = current_record.vlan_id
                comparison.new_speed = current_record.speed
                comparison.new_duplex = current_record.duplex
                comparison.new_link_status = current_record.link_status
                comparison.new_ping_reachable = current_record.ping_reachable

            # 比較差異
            comparison = self._compare_records(comparison, device_mappings)
            comparisons.append(comparison)

        return comparisons

    async def _generate_checkpoint_diffs_batch(
        self,
        maintenance_id: str,
        checkpoint_times: list[datetime],
        current_time: datetime,
        session: AsyncSession,
    ) -> dict[datetime, list[ClientComparison]]:
        """批次比較多個 checkpoint vs current。

        相比逐一呼叫 _generate_checkpoint_diff，此方法只執行 4 次 DB 查詢
        （device_mappings + mac_list + current_records + all_checkpoint_records），
        不受 checkpoint 數量影響。
        """
        import logging
        logger = logging.getLogger(__name__)

        from app.db.models import MaintenanceDeviceList, MaintenanceMacList

        if not checkpoint_times:
            return {}

        # 1. 載入 device_mappings (1 query)
        dev_stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        dev_result = await session.execute(dev_stmt)
        device_mappings: dict[str, str] = {}
        for dm in dev_result.scalars().all():
            device_mappings[dm.old_hostname.lower()] = dm.new_hostname

        # 2. 載入 MAC 清單 (1 query)
        mac_list_stmt = select(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        mac_list_result = await session.execute(mac_list_stmt)
        mac_records = mac_list_result.scalars().all()

        mac_list = {m.mac_address.upper() for m in mac_records}

        # 3. 載入 current_records → build current_by_mac (1 query)
        current_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.collected_at <= current_time,
            )
            .order_by(
                ClientRecord.mac_address,
                ClientRecord.collected_at.desc(),
            )
        )
        current_result = await session.execute(current_stmt)
        current_by_mac: dict[str, ClientRecord] = {}
        for record in current_result.scalars().all():
            mac_upper = record.mac_address.upper() if record.mac_address else ""
            if not mac_upper or mac_upper == SNAPSHOT_MARKER_MAC:
                continue
            if mac_upper not in current_by_mac:
                current_by_mac[mac_upper] = record

        # 4. 載入所有 checkpoint 記錄 (1 query)
        #    取 collected_at <= max(checkpoint_times)，在 Python 中按 checkpoint 分組
        max_cp = max(checkpoint_times)
        all_cp_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.collected_at <= max_cp,
            )
            .order_by(
                ClientRecord.mac_address,
                ClientRecord.collected_at.desc(),
            )
        )
        all_cp_result = await session.execute(all_cp_stmt)
        all_cp_records = all_cp_result.scalars().all()

        # 按 MAC 分組，轉為升序排列並建立 timestamps 索引供 bisect 使用
        # SQL 回傳 desc，reverse 後得到 asc（舊→新）
        from bisect import bisect_right
        from collections import defaultdict
        _records_by_mac_desc: dict[str, list[ClientRecord]] = defaultdict(list)
        for record in all_cp_records:
            mac_upper = record.mac_address.upper() if record.mac_address else ""
            if not mac_upper or mac_upper == SNAPSHOT_MARKER_MAC:
                continue
            _records_by_mac_desc[mac_upper].append(record)

        # 預處理：每個 MAC 的記錄轉為升序 + 提取 timestamps 陣列
        records_by_mac: dict[str, list[ClientRecord]] = {}
        timestamps_by_mac: dict[str, list[datetime]] = {}
        for mac, recs in _records_by_mac_desc.items():
            asc = list(reversed(recs))
            records_by_mac[mac] = asc
            timestamps_by_mac[mac] = [r.collected_at for r in asc]

        # 5. 對每個 checkpoint 生成比較結果
        results: dict[datetime, list[ClientComparison]] = {}
        all_macs = mac_list if mac_list else (
            set(records_by_mac.keys()) | set(current_by_mac.keys())
        )

        for cp_time in checkpoint_times:
            # 為此 checkpoint 建立 checkpoint_by_mac（bisect 二分搜尋 O(log R)）
            checkpoint_by_mac: dict[str, ClientRecord] = {}
            for mac in records_by_mac:
                ts = timestamps_by_mac[mac]
                idx = bisect_right(ts, cp_time)
                if idx > 0:
                    checkpoint_by_mac[mac] = records_by_mac[mac][idx - 1]

            # 生成 comparisons
            comparisons = []
            for mac in all_macs:
                checkpoint_record = checkpoint_by_mac.get(mac)
                current_record = current_by_mac.get(mac)

                comparison = ClientComparison(
                    maintenance_id=maintenance_id,
                    collected_at=now_utc(),
                    mac_address=mac,
                )

                if checkpoint_record:
                    comparison.old_ip_address = checkpoint_record.ip_address
                    comparison.old_switch_hostname = checkpoint_record.switch_hostname
                    comparison.old_interface_name = checkpoint_record.interface_name
                    comparison.old_vlan_id = checkpoint_record.vlan_id
                    comparison.old_speed = checkpoint_record.speed
                    comparison.old_duplex = checkpoint_record.duplex
                    comparison.old_link_status = checkpoint_record.link_status
                    comparison.old_ping_reachable = checkpoint_record.ping_reachable

                # 直接使用 ClientRecord 判斷是否有數據
                # 如果 switch_hostname 為 None，代表該 MAC 未被偵測到（None 記錄）
                if current_record and current_record.switch_hostname is not None:
                    comparison.new_ip_address = current_record.ip_address
                    comparison.new_switch_hostname = current_record.switch_hostname
                    comparison.new_interface_name = current_record.interface_name
                    comparison.new_vlan_id = current_record.vlan_id
                    comparison.new_speed = current_record.speed
                    comparison.new_duplex = current_record.duplex
                    comparison.new_link_status = current_record.link_status
                    comparison.new_ping_reachable = current_record.ping_reachable

                comparison = self._compare_records(comparison, device_mappings)
                comparisons.append(comparison)

            results[cp_time] = comparisons

        logger.info(
            "Batch checkpoint diff for %s: %d checkpoints, %d MACs",
            maintenance_id,
            len(checkpoint_times),
            len(all_macs),
        )

        return results

    def _compare_records(
        self,
        comparison: ClientComparison,
        device_mappings: dict[str, str] | None = None,
    ) -> ClientComparison:
        """給定一筆比較記錄，填充差異與備註。

        處理單邊未偵測的情況：
        - 兩邊都未偵測 → is_changed=False（undetected 標記）
        - OLD有值 → NEW未偵測 → is_changed=True（設備消失）
        - OLD未偵測 → NEW有值 → is_changed=True（新出現設備）
        - 兩邊都有值 → 比較差異

        Args:
            comparison: 比較記錄
            device_mappings: 設備對應 {old_hostname: new_hostname}
        """
        # 檢查是否單邊未偵測
        old_detected = self._has_any_data(comparison, 'old')
        new_detected = self._has_any_data(comparison, 'new')

        # 情況1：兩邊都未偵測
        if not old_detected and not new_detected:
            comparison.is_changed = False
            comparison.severity = "undetected"
            comparison.differences = {}
            comparison.notes = "兩個時間點都未偵測到"
            return comparison

        # 情況2：OLD有值，NEW未偵測（設備消失）
        if old_detected and not new_detected:
            comparison.is_changed = True
            comparison.differences = {
                "_status": {"old": "已偵測", "new": "未偵測"}
            }
            comparison.notes = "NEW 階段未偵測到該設備"
            return comparison

        # 情況3：OLD未偵測，NEW有值（新出現）
        if not old_detected and new_detected:
            comparison.is_changed = True
            comparison.differences = {
                "_status": {"old": "未偵測", "new": "已偵測"}
            }
            comparison.notes = "OLD 階段未偵測到該設備"
            return comparison

        # 情況4：兩邊都有值，正常比較差異
        differences = self._find_differences(comparison)
        comparison.differences = differences

        if differences:
            comparison.is_changed = True
            comparison.notes = self._generate_notes(comparison, differences)
        else:
            comparison.is_changed = False
            comparison.notes = "未檢測到變化"

        return comparison
    
    def _has_any_data(self, comparison: ClientComparison, prefix: str) -> bool:
        """檢查指定前綴（old/new）是否有任何有效數據。"""
        fields = [
            f"{prefix}_switch_hostname",
            f"{prefix}_interface_name",
            f"{prefix}_ip_address",
            f"{prefix}_vlan_id",
            f"{prefix}_speed",
            f"{prefix}_duplex",
            f"{prefix}_link_status",
        ]
        for field in fields:
            value = getattr(comparison, field, None)
            if value is not None and value != "":
                return True
        return False
