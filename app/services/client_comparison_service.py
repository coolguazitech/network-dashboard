"""
Client comparison service.

比較客戶端在 OLD/NEW 階段的變化。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClientRecord, ClientComparison
from app.core.enums import MaintenancePhase

# 快照標記的特殊 MAC 地址（用於在沒有實際資料時記錄時間點）
SNAPSHOT_MARKER_MAC = "__MARKER__"


class ClientComparisonService:
    """客戶端比較服務。
    
    比較同一個 MAC 地址在 OLD/NEW 階段的變化情況，包括：
    - 拓樸角色（access/trunk/uplink）
    - 連接的交換機和埠口
    - 連接速率、雙工模式
    - ACL 規則
    - Ping 可達性和延遲
    """
    
    def __init__(self):
        """初始化並載入配置。"""
        self._load_config()
        self._reference_clients_cache = None
    
    def _load_config(self):
        """從 YAML 配置文件載入嚴重程度定義。"""
        config_path = Path(__file__).parent.parent.parent / "config" / "client_comparison.yaml"
        
        # 預設值（如果配置文件不存在）
        default_config = {
            "critical_fields": [
                "switch_hostname",
                "interface_name",
                "link_status",
                "ping_reachable",
                "acl_passes",
            ],
            "warning_fields": [
                "speed",
                "duplex",
                "vlan_id",
            ],
            "ping_latency_threshold_ms": 10.0,
        }
        
        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    self.CRITICAL_FIELDS = set(config.get("critical_fields", default_config["critical_fields"]))
                    self.WARNING_FIELDS = set(config.get("warning_fields", default_config["warning_fields"]))
                    self.PING_LATENCY_THRESHOLD = config.get("ping_latency_threshold_ms", default_config["ping_latency_threshold_ms"])
            else:
                # 使用預設值
                self.CRITICAL_FIELDS = set(default_config["critical_fields"])
                self.WARNING_FIELDS = set(default_config["warning_fields"])
                self.PING_LATENCY_THRESHOLD = default_config["ping_latency_threshold_ms"]
        except Exception as e:
            print(f"Warning: Failed to load client comparison config: {e}")
            # 發生錯誤時使用預設值
            self.CRITICAL_FIELDS = set(default_config["critical_fields"])
            self.WARNING_FIELDS = set(default_config["warning_fields"])
            self.PING_LATENCY_THRESHOLD = default_config["ping_latency_threshold_ms"]
    
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
                ClientRecord.phase == MaintenancePhase.OLD,
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
                ClientRecord.phase == MaintenancePhase.NEW,
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

        # 4. 載入設備對應（用於 severity 計算）
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
                collected_at=datetime.utcnow(),
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
                comparison.old_acl_passes = old_record.acl_passes

            # 添加 NEW（新設備）數據
            # 只有當 client 目前可偵測時才填入 NEW 資料
            # 若偵測狀態為 NOT_DETECTED，Current 顯示為空（表示目前無法取得資料）
            detection_status = mac_detection_status.get(mac)
            is_currently_detectable = detection_status == ClientDetectionStatus.DETECTED

            if new_record and is_currently_detectable:
                comparison.new_ip_address = new_record.ip_address
                comparison.new_switch_hostname = new_record.switch_hostname
                comparison.new_interface_name = new_record.interface_name
                comparison.new_vlan_id = new_record.vlan_id
                comparison.new_speed = new_record.speed
                comparison.new_duplex = new_record.duplex
                comparison.new_link_status = new_record.link_status
                comparison.new_ping_reachable = new_record.ping_reachable
                comparison.new_acl_passes = new_record.acl_passes

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
                ClientRecord.phase == MaintenancePhase.OLD,
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
                ClientRecord.phase == MaintenancePhase.NEW,
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
                collected_at=datetime.utcnow(),
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
                comparison.old_acl_passes = old_record.acl_passes

            if new_record:
                comparison.new_ip_address = new_record.ip_address
                comparison.new_switch_hostname = new_record.switch_hostname
                comparison.new_interface_name = new_record.interface_name
                comparison.new_vlan_id = new_record.vlan_id
                comparison.new_speed = new_record.speed
                comparison.new_duplex = new_record.duplex
                comparison.new_link_status = new_record.link_status
                comparison.new_ping_reachable = new_record.ping_reachable
                comparison.new_acl_passes = new_record.acl_passes

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
            ("old_acl_passes", "new_acl_passes", "acl_passes"),
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

            # 檢查是否有實際變化（忽略 None 值的比較）
            if old_value != new_value:
                # 對於布林值，只有都不為 None 時才比較
                if field_name in ("ping_reachable", "acl_passes"):
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
    
    def _calculate_severity(
        self,
        differences: dict[str, Any],
        device_mappings: dict[str, str] | None = None,
    ) -> str:
        """基於差異類型計算嚴重程度。

        邏輯：
        1. 狀態惡化（True→False）→ critical
        2. 狀態改善（False→True）→ warning（好事但仍需注意）
        3. 設備變化 + 符合對應 → info（正常）
        4. 設備變化 + 不符合對應 → warning（警告）
        5. port 有變化 → warning（警告）
        6. 其他 warning 欄位（speed, duplex, vlan）→ warning
        """
        diff_keys = set(differences.keys())
        device_mappings = device_mappings or {}

        # 1. 檢查布林狀態欄位（ping_reachable, link_status, acl_passes）
        # 惡化（True→False）= critical，改善（False→True）= warning
        status_fields = {"ping_reachable", "acl_passes"}
        has_degradation = False
        has_improvement = False

        for field in status_fields:
            if field in differences:
                change = differences[field]
                old_val = change.get("old")
                new_val = change.get("new")
                # True → False 是惡化（重大問題）
                if old_val is True and new_val is False:
                    has_degradation = True
                # False → True 是改善（警告/注意）
                elif old_val is False and new_val is True:
                    has_improvement = True

        # link_status 特殊處理（up → down = 惡化，down → up = 改善）
        if "link_status" in differences:
            change = differences["link_status"]
            old_val = str(change.get("old", "")).lower()
            new_val = str(change.get("new", "")).lower()
            if old_val == "up" and new_val == "down":
                has_degradation = True
            elif old_val == "down" and new_val == "up":
                has_improvement = True

        if has_degradation:
            return "critical"
        if has_improvement:
            return "warning"
        
        switch_change = differences.get("switch_hostname")
        interface_change = differences.get("interface_name")
        
        # 2. 檢查設備變化
        if switch_change:
            old_switch = switch_change.get("old", "")
            new_switch = switch_change.get("new", "")
            # 使用小寫 key 來查詢設備對應（因為字典 key 是小寫）
            expected_new = device_mappings.get(old_switch.lower() if old_switch else "")
            
            # 設備變化 + 符合對應 → 正常（比較時忽略大小寫）
            if expected_new and expected_new.lower() == (new_switch.lower() if new_switch else ""):
                # 檢查其他 warning 欄位
                other_diffs = diff_keys - {"switch_hostname", "interface_name"}
                if other_diffs & self.WARNING_FIELDS:
                    return "warning"
                return "info"
            
            # 設備變化 + 不符合對應 → 警告
            return "warning"
        
        # 3. 設備沒變但 port 變化 → 警告
        if interface_change:
            return "warning"
        
        # 4. 其他 warning 欄位（speed, duplex, vlan）
        if diff_keys & self.WARNING_FIELDS:
            return "warning"
        
        return "info"
    
    def _generate_notes(
        self,
        comparison: ClientComparison,
        differences: dict[str, Any],
    ) -> str:
        """生成比較結果的註釋。"""
        notes = []
        
        for field_name, change_info in differences.items():
            if field_name in self.CRITICAL_FIELDS:
                prefix = "⚠️ CRITICAL: "
            elif field_name in self.WARNING_FIELDS:
                prefix = "⚠️ WARNING: "
            else:
                prefix = "ℹ️ INFO: "
            
            old_val = change_info.get("old")
            new_val = change_info.get("new")
            
            notes.append(f"{prefix}{field_name}: {old_val} → {new_val}")
        
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
        severity: str | None = None,
        changed_only: bool = False,
        before_time: str | None = None,
    ) -> list[ClientComparison]:
        """
        查詢比較結果。
        
        支持按 MAC 地址、IP 地址、嚴重程度和是否變化進行篩選。
        如果提供 before_time，則動態生成比較結果而非查詢資料庫。
        """
        from sqlalchemy import or_
        
        # 如果提供了 before_time，動態生成比較結果
        if before_time:
            from datetime import datetime

            before_dt = datetime.fromisoformat(before_time)

            # 獲取最新 NEW 階段時間
            from sqlalchemy import func
            latest_stmt = (
                select(func.max(ClientRecord.collected_at))
                .where(
                    ClientRecord.maintenance_id == maintenance_id,
                    ClientRecord.phase == MaintenancePhase.NEW,
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
            
            if severity:
                comparisons = [c for c in comparisons if c.severity == severity]
            
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
        
        if severity:
            stmt = stmt.where(ClientComparison.severity == severity)
        
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
        critical = sum(1 for c in comparisons if c.severity == "critical")
        warning = sum(1 for c in comparisons if c.severity == "warning")
        
        return {
            "total": total,
            "unchanged": unchanged,
            "changed": changed,
            "unchanged_rate": (unchanged / total * 100) if total > 0 else 0,
            "changed_rate": (changed / total * 100) if total > 0 else 0,
            "critical": critical,
            "warning": warning,
            "info": total - critical - warning - unchanged,
        }
    
    async def get_timepoints(
        self,
        maintenance_id: str,
        session: AsyncSession,
        max_days: int = 7,
    ) -> list[dict[str, Any]]:
        """獲取 NEW 階段的歷史時間點（限制在 max_days 天內）。

        只返回 NEW phase 的時間點，確保統計圖表只顯示
        有歲修後資料可比較的時間點。

        Args:
            maintenance_id: 歲修 ID
            session: DB session
            max_days: 最大天數限制（預設 7 天）
        """
        from sqlalchemy import func
        from datetime import timedelta, timezone

        # 計算截止時間（max_days 天前）
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)

        stmt = (
            select(
                func.distinct(ClientRecord.collected_at)
                .label('timepoint')
            )
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.NEW,
                ClientRecord.collected_at >= cutoff,  # 限制在 max_days 天內
            )
            .order_by('timepoint')
        )

        result = await session.execute(stmt)
        timepoints = result.scalars().all()

        return [
            {
                "timestamp": tp.isoformat(),
                "label": tp.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for tp in timepoints
        ]
    
    async def get_statistics(
        self,
        maintenance_id: str,
        session: AsyncSession,
        max_days: int = 7,
        hourly_sampling: bool = True,
    ) -> list[dict[str, Any]]:
        """獲取每個時間點的統計資料。

        用於時間軸圖表顯示趨勢。按使用者自訂分類統計異常數。
        如果沒有 ClientRecord，則使用 ClientComparison 生成靜態統計。

        已優化：預先載入所有資料，避免 N+1 查詢問題。

        Args:
            maintenance_id: 歲修 ID
            session: DB session
            max_days: 最大天數限制（預設 7 天，最多 168 個小時點）
            hourly_sampling: 是否每小時採樣（預設 True，每小時取最後一筆）
        """
        from sqlalchemy import func
        from datetime import timedelta, timezone
        from app.db.models import ClientCategory, ClientCategoryMember, MaintenanceDeviceList

        # 計算截止時間（max_days 天前）
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)

        # 檢查是否有 ClientRecord 資料（在時間範圍內）
        record_count_stmt = (
            select(func.count())
            .select_from(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.collected_at >= cutoff,
            )
        )
        record_count_result = await session.execute(record_count_stmt)
        record_count = record_count_result.scalar() or 0

        # 如果沒有 ClientRecord，使用 ClientComparison 生成靜態統計
        if record_count == 0:
            return await self._get_static_statistics(maintenance_id, session)

        # === 預先載入所有資料（一次性查詢，避免 N+1） ===

        # 0. 載入 MaintenanceMacList 作為 MAC 清單基準
        from app.db.models import MaintenanceMacList
        mac_list_stmt = select(MaintenanceMacList.mac_address).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        mac_list_result = await session.execute(mac_list_stmt)
        mac_list = {m.upper() for m in mac_list_result.scalars().all()}

        # 1. 載入設備對應
        dev_stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        dev_result = await session.execute(dev_stmt)
        device_mappings_list = dev_result.scalars().all()
        device_mappings: dict[str, str] = {}
        for dm in device_mappings_list:
            device_mappings[dm.old_hostname.lower()] = dm.new_hostname

        # 2. 載入所有 OLD 階段記錄（按 MAC 分組，只保留最新）
        old_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.OLD,
            )
            .order_by(ClientRecord.mac_address, ClientRecord.collected_at.desc())
        )
        old_result = await session.execute(old_stmt)
        old_records = old_result.scalars().all()

        old_by_mac: dict[str, ClientRecord] = {}
        for record in old_records:
            mac_upper = record.mac_address.upper() if record.mac_address else ""
            if not mac_upper or mac_upper == SNAPSHOT_MARKER_MAC:
                continue  # 跳過空值和快照標記
            if mac_upper not in old_by_mac:
                old_by_mac[mac_upper] = record

        # 3. 載入所有 NEW 階段記錄（按 MAC+時間排序，限制在 cutoff 之後）
        new_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.NEW,
                ClientRecord.collected_at >= cutoff,  # 限制在 max_days 天內
            )
            .order_by(ClientRecord.collected_at, ClientRecord.mac_address)
        )
        new_result = await session.execute(new_stmt)
        all_new_records = new_result.scalars().all()

        # 4. 獲取所有時間點（從已載入的 NEW 記錄）
        timepoints_set: set[datetime] = set()
        for record in all_new_records:
            if record.collected_at:
                timepoints_set.add(record.collected_at)
        all_timepoints_dt = sorted(timepoints_set)

        if not all_timepoints_dt:
            return await self._get_static_statistics(maintenance_id, session)

        # 採樣策略
        if hourly_sampling:
            # 每小時取最後一筆（最多 7*24=168 個時間點）
            hourly_buckets: dict[str, datetime] = {}
            for tp in all_timepoints_dt:
                bucket_key = tp.strftime("%Y-%m-%d-%H")  # 年-月-日-時
                hourly_buckets[bucket_key] = tp  # 保留該小時最後一筆
            sampled_timepoints = sorted(hourly_buckets.values())
        else:
            # 不採樣，使用所有時間點
            sampled_timepoints = all_timepoints_dt

        # 5. 獲取使用者自訂分類和成員（只取該歲修的分類或全域分類）
        cat_stmt = select(ClientCategory).where(
            ClientCategory.is_active == True,  # noqa: E712
            (ClientCategory.maintenance_id == maintenance_id)
            | (ClientCategory.maintenance_id.is_(None))
        )
        cat_result = await session.execute(cat_stmt)
        categories = cat_result.scalars().all()

        active_cat_ids = [c.id for c in categories]
        if active_cat_ids:
            member_stmt = (
                select(ClientCategoryMember)
                .where(ClientCategoryMember.category_id.in_(active_cat_ids))
            )
            member_result = await session.execute(member_stmt)
            members = member_result.scalars().all()
        else:
            members = []

        # 建立 MAC -> category_ids 對照
        mac_to_categories: dict[str, list[int]] = {}
        for m in members:
            normalized_mac = m.mac_address.upper() if m.mac_address else ""
            if normalized_mac:
                if normalized_mac not in mac_to_categories:
                    mac_to_categories[normalized_mac] = []
                mac_to_categories[normalized_mac].append(m.category_id)

        # 分類資訊
        category_info = {cat.id: {"name": cat.name, "color": cat.color} for cat in categories}

        # === 為每個時間點計算統計（使用預載入的資料） ===
        statistics = []

        for tp in sampled_timepoints:
            # 篩選該時間點的 NEW 記錄（collected_at <= tp）
            # 按 MAC 分組，只保留最新的
            new_by_mac: dict[str, ClientRecord] = {}
            for record in all_new_records:
                if record.collected_at and record.collected_at <= tp:
                    mac_upper = record.mac_address.upper() if record.mac_address else ""
                    if mac_upper and mac_upper != SNAPSHOT_MARKER_MAC:
                        # 因為已按時間排序，後面的會覆蓋前面的（保留最新）
                        new_by_mac[mac_upper] = record

            # 生成比較結果（在記憶體中處理）
            # 優先使用 MaintenanceMacList，確保刪除的 MAC 不再顯示
            if mac_list:
                all_macs = mac_list
            else:
                all_macs = set(old_by_mac.keys()) | set(new_by_mac.keys())
            comparisons = []

            for mac in all_macs:
                old_record = old_by_mac.get(mac)
                new_record = new_by_mac.get(mac)

                comparison = ClientComparison(
                    maintenance_id=maintenance_id,
                    collected_at=tp,
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
                    comparison.old_acl_passes = old_record.acl_passes

                if new_record:
                    comparison.new_ip_address = new_record.ip_address
                    comparison.new_switch_hostname = new_record.switch_hostname
                    comparison.new_interface_name = new_record.interface_name
                    comparison.new_vlan_id = new_record.vlan_id
                    comparison.new_speed = new_record.speed
                    comparison.new_duplex = new_record.duplex
                    comparison.new_link_status = new_record.link_status
                    comparison.new_ping_reachable = new_record.ping_reachable
                    comparison.new_acl_passes = new_record.acl_passes

                comparison = self._compare_records(comparison, device_mappings)
                comparisons.append(comparison)

            # 計算統計
            # 異常包括：有變化的 + 未偵測的（severity="undetected"）
            total = len(comparisons)
            has_issues = sum(
                1 for c in comparisons
                if c.is_changed or c.severity == "undetected"
            )
            critical = sum(1 for c in comparisons if c.severity == "critical")
            warning = sum(1 for c in comparisons if c.severity == "warning")
            undetected = sum(1 for c in comparisons if c.severity == "undetected")

            # 按使用者分類統計
            by_user_category: dict[str, dict[str, Any]] = {}

            for cat_id, cat_data in category_info.items():
                by_user_category[str(cat_id)] = {
                    "name": cat_data["name"],
                    "color": cat_data["color"],
                    "total": 0,
                    "has_issues": 0,
                    "undetected": 0,
                }
            by_user_category["null"] = {
                "name": "未分類",
                "color": "#6B7280",
                "total": 0,
                "has_issues": 0,
                "undetected": 0,
            }

            detected_macs = {c.mac_address.upper() for c in comparisons if c.mac_address}

            for comp in comparisons:
                normalized_mac = comp.mac_address.upper() if comp.mac_address else ""
                cat_ids = mac_to_categories.get(normalized_mac, [])
                if not cat_ids:
                    cat_ids = [None]
                for cat_id in cat_ids:
                    cat_key = str(cat_id) if cat_id else "null"
                    if cat_key not in by_user_category:
                        cat_key = "null"
                    by_user_category[cat_key]["total"] += 1
                    # 異常包括：有變化的 + 未偵測的
                    if comp.is_changed or comp.severity == "undetected":
                        by_user_category[cat_key]["has_issues"] += 1
                    if comp.severity == "undetected":
                        by_user_category[cat_key]["undetected"] += 1

            for mac, cat_ids in mac_to_categories.items():
                if mac not in detected_macs:
                    for cat_id in cat_ids:
                        cat_key = str(cat_id) if cat_id else "null"
                        if cat_key in by_user_category:
                            by_user_category[cat_key]["total"] += 1
                            by_user_category[cat_key]["undetected"] += 1
                            by_user_category[cat_key]["has_issues"] += 1

            for cat_key in by_user_category:
                cat_data = by_user_category[cat_key]
                cat_data["normal"] = cat_data["total"] - cat_data["has_issues"]

            statistics.append({
                "timestamp": tp.isoformat(),
                "label": tp.strftime("%Y-%m-%d %H:%M:%S"),
                "total": total,
                "has_issues": has_issues,
                "critical": critical,
                "warning": warning,
                "by_user_category": by_user_category,
            })

        return statistics
    
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
        mac_list_stmt = select(MaintenanceMacList.mac_address).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        mac_list_result = await session.execute(mac_list_stmt)
        mac_list = {m.upper() for m in mac_list_result.scalars().all()}

        # 查詢 OLD 階段記錄（歲修前基線）
        before_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.OLD,
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

        # 查詢 NEW 階段記錄（歲修後）
        # 僅查詢 NEW phase，避免 OLD 記錄洩漏到 after 端
        if after_time:
            after_stmt = (
                select(ClientRecord)
                .where(
                    ClientRecord.maintenance_id == maintenance_id,
                    ClientRecord.phase == MaintenancePhase.NEW,
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
                    ClientRecord.phase == MaintenancePhase.NEW,
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
                collected_at=datetime.utcnow(),
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
                comparison.old_acl_passes = before_record.acl_passes
            
            # 添加 AFTER 資料
            if after_record:
                comparison.new_ip_address = after_record.ip_address
                comparison.new_switch_hostname = after_record.switch_hostname
                comparison.new_interface_name = after_record.interface_name
                comparison.new_vlan_id = after_record.vlan_id
                comparison.new_speed = after_record.speed
                comparison.new_duplex = after_record.duplex
                comparison.new_link_status = after_record.link_status
                comparison.new_ping_reachable = after_record.ping_reachable
                comparison.new_acl_passes = after_record.acl_passes
            
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
        mac_list_stmt = select(MaintenanceMacList.mac_address).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        mac_list_result = await session.execute(mac_list_stmt)
        mac_list = {m.upper() for m in mac_list_result.scalars().all()}

        # 查詢 Checkpoint 時間點的 NEW 階段記錄
        checkpoint_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.NEW,
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

        # 查詢 Current（最新）時間點的 NEW 階段記錄
        if current_time:
            current_stmt = (
                select(ClientRecord)
                .where(
                    ClientRecord.maintenance_id == maintenance_id,
                    ClientRecord.phase == MaintenancePhase.NEW,
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
                    ClientRecord.phase == MaintenancePhase.NEW,
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
                collected_at=datetime.utcnow(),
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
                comparison.old_acl_passes = checkpoint_record.acl_passes

            # 添加 Current 資料
            if current_record:
                comparison.new_ip_address = current_record.ip_address
                comparison.new_switch_hostname = current_record.switch_hostname
                comparison.new_interface_name = current_record.interface_name
                comparison.new_vlan_id = current_record.vlan_id
                comparison.new_speed = current_record.speed
                comparison.new_duplex = current_record.duplex
                comparison.new_link_status = current_record.link_status
                comparison.new_ping_reachable = current_record.ping_reachable
                comparison.new_acl_passes = current_record.acl_passes

            # 比較差異
            comparison = self._compare_records(comparison, device_mappings)
            comparisons.append(comparison)

        return comparisons

    def _compare_records(
        self,
        comparison: ClientComparison,
        device_mappings: dict[str, str] | None = None,
    ) -> ClientComparison:
        """給定一筆比較記錄，填充差異、嚴重度與備註。
        
        處理單邊未偵測的情況：
        - OLD有值 → NEW未偵測 = critical（設備消失了！）
        - OLD未偵測 → NEW有值 = warning（新出現的設備）
        - 兩邊都未偵測 = undetected（灰色標記，不計入異常）
        
        Args:
            comparison: 比較記錄
            device_mappings: 設備對應 {old_hostname: new_hostname}
        """
        device_mappings = device_mappings or {}
        
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
        
        # 情況2：OLD有值，NEW未偵測 → 重大問題（設備消失）
        if old_detected and not new_detected:
            comparison.is_changed = True
            comparison.severity = "critical"
            comparison.differences = {
                "_status": {"old": "已偵測", "new": "未偵測"}
            }
            comparison.notes = "🔴 重大：NEW 階段未偵測到該設備"
            return comparison
        
        # 情況3：OLD未偵測，NEW有值 → 警告（新出現）
        if not old_detected and new_detected:
            comparison.is_changed = True
            comparison.severity = "warning"
            comparison.differences = {
                "_status": {"old": "未偵測", "new": "已偵測"}
            }
            comparison.notes = "🟡 警告：OLD 階段未偵測到該設備"
            return comparison
        
        # 情況4：兩邊都有值，正常比較差異
        differences = self._find_differences(comparison)
        comparison.differences = differences

        if differences:
            comparison.is_changed = True
            # 傳入設備對應來判斷嚴重度
            comparison.severity = self._calculate_severity(
                differences,
                device_mappings,
            )
            comparison.notes = self._generate_notes(comparison, differences)
        else:
            comparison.is_changed = False
            comparison.severity = "info"
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

    async def _get_static_statistics(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> list[dict[str, Any]]:
        """
        當沒有 ClientRecord 時，使用 ClientComparison 生成靜態統計。

        只生成一個時間點的統計資料（當前快照）。
        """
        from sqlalchemy import func
        from app.db.models import ClientCategory, ClientCategoryMember
        
        # 獲取所有比較結果
        comp_stmt = (
            select(ClientComparison)
            .where(ClientComparison.maintenance_id == maintenance_id)
        )
        comp_result = await session.execute(comp_stmt)
        comparisons = comp_result.scalars().all()
        
        if not comparisons:
            return []
        
        # 獲取最早時間點作為標籤
        min_time = min(
            (c.collected_at for c in comparisons if c.collected_at),
            default=datetime.utcnow()
        )
        max_time = max(
            (c.collected_at for c in comparisons if c.collected_at),
            default=datetime.utcnow()
        )
        
        # 獲取使用者自訂分類和成員（只取該歲修的分類或全域分類）
        cat_stmt = select(ClientCategory).where(
            ClientCategory.is_active == True,  # noqa: E712
            (ClientCategory.maintenance_id == maintenance_id)
            | (ClientCategory.maintenance_id.is_(None))
        )
        cat_result = await session.execute(cat_stmt)
        categories = cat_result.scalars().all()

        active_cat_ids = [c.id for c in categories]
        member_stmt = (
            select(ClientCategoryMember)
            .where(ClientCategoryMember.category_id.in_(active_cat_ids))
        )
        member_result = await session.execute(member_stmt)
        members = member_result.scalars().all()
        
        # 建立 MAC -> category_ids 對照
        mac_to_categories: dict[str, list[int]] = {}
        for m in members:
            normalized_mac = m.mac_address.upper() if m.mac_address else ""
            if normalized_mac:
                if normalized_mac not in mac_to_categories:
                    mac_to_categories[normalized_mac] = []
                mac_to_categories[normalized_mac].append(m.category_id)
        
        # 分類資訊
        category_info = {
            cat.id: {"name": cat.name, "color": cat.color}
            for cat in categories
        }
        
        # 初始化分類統計
        by_user_category: dict[str, dict[str, Any]] = {}
        for cat_id, cat_data in category_info.items():
            by_user_category[str(cat_id)] = {
                "name": cat_data["name"],
                "color": cat_data["color"],
                "total": 0,
                "has_issues": 0,
                "undetected": 0,
                "normal": 0,
            }
        by_user_category["null"] = {
            "name": "未分類",
            "color": "#6B7280",
            "total": 0,
            "has_issues": 0,
            "undetected": 0,
            "normal": 0,
        }
        
        # 統計每個比較結果
        total = len(comparisons)
        has_issues = 0
        critical = 0
        warning = 0
        
        for comp in comparisons:
            normalized_mac = comp.mac_address.upper() if comp.mac_address else ""
            cat_ids = mac_to_categories.get(normalized_mac, [])
            
            if not cat_ids:
                cat_ids = [None]
            
            for cat_id in cat_ids:
                cat_key = str(cat_id) if cat_id else "null"
                if cat_key not in by_user_category:
                    cat_key = "null"
                by_user_category[cat_key]["total"] += 1
                if comp.is_changed:
                    by_user_category[cat_key]["has_issues"] += 1
            
            if comp.is_changed:
                has_issues += 1
                if comp.severity == "critical":
                    critical += 1
                elif comp.severity == "warning":
                    warning += 1
        
        # 計算 normal
        for cat_key in by_user_category:
            cat_data = by_user_category[cat_key]
            cat_data["normal"] = cat_data["total"] - cat_data["has_issues"]
        
        # 回傳兩個時間點（起點和終點），讓圖表能顯示
        return [
            {
                "timestamp": min_time.isoformat(),
                "label": min_time.strftime("%Y-%m-%d %H:%M:%S"),
                "total": total,
                "has_issues": has_issues,
                "critical": critical,
                "warning": warning,
                "by_user_category": by_user_category,
            },
            {
                "timestamp": max_time.isoformat(),
                "label": max_time.strftime("%Y-%m-%d %H:%M:%S"),
                "total": total,
                "has_issues": has_issues,
                "critical": critical,
                "warning": warning,
                "by_user_category": by_user_category,
            },
        ]


async def cleanup_old_client_records(
    maintenance_id: str,
    retention_days: int,
    session: AsyncSession,
) -> int:
    """
    清理超過保留期限的 ClientRecord。

    Args:
        maintenance_id: 歲修 ID
        retention_days: 保留天數
        session: DB session

    Returns:
        刪除的記錄數量
    """
    from datetime import timedelta, timezone
    from sqlalchemy import delete

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    stmt = delete(ClientRecord).where(
        ClientRecord.maintenance_id == maintenance_id,
        ClientRecord.collected_at < cutoff,
    )
    result = await session.execute(stmt)
    await session.commit()

    return result.rowcount or 0
