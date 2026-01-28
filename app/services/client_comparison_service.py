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
        
        查詢同一個 MAC 地址在 OLD(舊設備) 和 NEW(新設備) 階段的記錄，比較差異。
        """
        # 查詢 OLD 階段的記錄，按 MAC 地址分組，只保留最新的
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
        
        # 按 MAC 地址分組，只保留最新記錄
        old_by_mac = {}
        for record in old_records:
            if record.mac_address not in old_by_mac:
                old_by_mac[record.mac_address] = record
        
        # 查詢 NEW 階段的記錄，按 MAC 地址分組，只保留最新的
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
        
        # 按 MAC 地址分組，只保留最新記錄
        new_by_mac = {}
        for record in new_records:
            if record.mac_address not in new_by_mac:
                new_by_mac[record.mac_address] = record
        
        # 載入設備對應（用於 severity 計算）
        from app.db.models import MaintenanceDeviceList
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

            # 使用 _compare_records 處理單邊未偵測情況
            comparison = self._compare_records(comparison, device_mappings)
            comparisons.append(comparison)

        return comparisons
    
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
        
        簡化邏輯：
        1. link_status/ping/acl 變化 → critical
        2. 設備變化 + 符合對應 → info（正常）
        3. 設備變化 + 不符合對應 → warning（警告）
        4. port 有變化 → warning（警告）
        5. 其他 warning 欄位（speed, duplex, vlan）→ warning
        """
        diff_keys = set(differences.keys())
        device_mappings = device_mappings or {}
        
        # 1. 真正的 critical 欄位（不管設備對應）
        real_critical = {"link_status", "ping_reachable", "acl_passes"}
        if diff_keys & real_critical:
            return "critical"
        
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
    ) -> list[dict[str, Any]]:
        """獲取 NEW 階段的歷史時間點。

        只返回 NEW phase 的時間點，確保統計圖表只顯示
        有歲修後資料可比較的時間點。
        """
        from sqlalchemy import func

        stmt = (
            select(
                func.distinct(ClientRecord.collected_at)
                .label('timepoint')
            )
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.NEW,
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
    ) -> list[dict[str, Any]]:
        """獲取每個時間點的統計資料。

        用於時間軸圖表顯示趨勢。按使用者自訂分類統計異常數。
        如果沒有 ClientRecord，則使用 ClientComparison 生成靜態統計。
        """
        from sqlalchemy import func
        from app.db.models import ClientCategory, ClientCategoryMember
        
        # 檢查是否有 ClientRecord 資料
        record_count_stmt = (
            select(func.count())
            .select_from(ClientRecord)
            .where(ClientRecord.maintenance_id == maintenance_id)
        )
        record_count_result = await session.execute(record_count_stmt)
        record_count = record_count_result.scalar() or 0
        
        # 如果沒有 ClientRecord，使用 ClientComparison 生成靜態統計
        if record_count == 0:
            return await self._get_static_statistics(maintenance_id, session)
        
        # 獲取所有時間點（從 ClientRecord）
        timepoints_data = await self.get_timepoints(maintenance_id, session)
        
        # 獲取使用者自訂分類和成員（只取活躍分類）
        cat_stmt = select(ClientCategory).where(ClientCategory.is_active == True)
        cat_result = await session.execute(cat_stmt)
        categories = cat_result.scalars().all()
        
        # 只查詢活躍分類的成員
        active_cat_ids = [c.id for c in categories]
        member_stmt = (
            select(ClientCategoryMember)
            .where(ClientCategoryMember.category_id.in_(active_cat_ids))
        )
        member_result = await session.execute(member_stmt)
        members = member_result.scalars().all()
        
        # 建立 MAC -> category_ids 對照（一對多：一個 MAC 可屬於多個分類）
        mac_to_categories: dict[str, list[int]] = {}
        for m in members:
            normalized_mac = m.mac_address.upper() if m.mac_address else ""
            if normalized_mac:
                if normalized_mac not in mac_to_categories:
                    mac_to_categories[normalized_mac] = []
                mac_to_categories[normalized_mac].append(m.category_id)
        
        # 分類資訊
        category_info = {cat.id: {"name": cat.name, "color": cat.color} for cat in categories}
        
        statistics = []

        def summarize(comps):
            total = len(comps)
            has_issues = sum(1 for c in comps if c.is_changed)
            critical = sum(1 for c in comps if c.severity == "critical")
            warning = sum(1 for c in comps if c.severity == "warning")
            return {
                "total": total,
                "has_issues": has_issues,
                "critical": critical,
                "warning": warning,
            }
        
        for tp_data in timepoints_data:
            from datetime import datetime
            tp = datetime.fromisoformat(tp_data["timestamp"])

            # 生成該時間點的比較結果（不保存）
            # after_time=tp：只取到該時間點為止的 NEW 記錄，
            # 這樣每個時間點反映的是當時的偵測狀態
            comparisons = await self._generate_comparisons_at_time(
                maintenance_id=maintenance_id,
                before_time=tp,
                after_time=tp,
                session=session,
            )
            
            # 總計統計
            all_summary = summarize(comparisons)
            
            # 按使用者分類統計
            by_user_category: dict[str, dict[str, Any]] = {}
            
            # 初始化分類統計
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
            
            # 建立已偵測到的 MAC 集合
            detected_macs = {
                c.mac_address.upper() for c in comparisons if c.mac_address
            }
            
            # 統計每個分類的異常數
            for comp in comparisons:
                normalized_mac = comp.mac_address.upper() if comp.mac_address else ""
                cat_ids = mac_to_categories.get(normalized_mac, [])
                
                # 如果沒有分類，歸入未分類
                if not cat_ids:
                    cat_ids = [None]
                
                # 統計到每個所屬分類
                for cat_id in cat_ids:
                    cat_key = str(cat_id) if cat_id else "null"
                    if cat_key not in by_user_category:
                        cat_key = "null"
                    by_user_category[cat_key]["total"] += 1
                    if comp.is_changed:
                        by_user_category[cat_key]["has_issues"] += 1
            
            # 統計分類成員中未偵測到的 MAC（未偵測也算異常！）
            for mac, cat_ids in mac_to_categories.items():
                if mac not in detected_macs:
                    for cat_id in cat_ids:
                        cat_key = str(cat_id) if cat_id else "null"
                        if cat_key in by_user_category:
                            by_user_category[cat_key]["total"] += 1
                            by_user_category[cat_key]["undetected"] += 1
                            by_user_category[cat_key]["has_issues"] += 1
            
            # 計算 normal（正常數 = 總數 - 異常數）
            for cat_key in by_user_category:
                cat_data = by_user_category[cat_key]
                cat_data["normal"] = cat_data["total"] - cat_data["has_issues"]
            
            statistics.append({
                "timestamp": tp_data["timestamp"],
                "label": tp_data["label"],
                "total": all_summary["total"],
                "has_issues": all_summary["has_issues"],
                "critical": all_summary["critical"],
                "warning": all_summary["warning"],
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
        """在指定時間點生成比較結果（不保存到資料庫）。"""
        from app.db.models import MaintenanceDeviceList
        
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

        # 按 MAC 地址分組，只保留最新記錄
        before_by_mac = {}
        for record in before_records:
            if record.mac_address not in before_by_mac:
                before_by_mac[record.mac_address] = record

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

        # 按 MAC 地址分組，只保留最新記錄
        after_by_mac = {}
        for record in after_records:
            if record.mac_address not in after_by_mac:
                after_by_mac[record.mac_address] = record
        
        # 生成比較結果
        comparisons = []
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
        
        # 獲取使用者自訂分類和成員
        cat_stmt = select(ClientCategory).where(ClientCategory.is_active == True)
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
