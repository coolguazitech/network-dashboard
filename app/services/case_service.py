"""
Case Service.

案件管理核心邏輯：同步、查詢、變化偵測等。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, select, func, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CaseStatus, UserRole
from app.db.models import (
    Case, CaseNote, ClientRecord, MaintenanceMacList, User,
)
from app.services.system_log import write_log

logger = logging.getLogger(__name__)

# 追蹤的客戶端屬性（用於變化標籤，按優先級排序）
# 0=ping, 1=VLAN, 2=ACL, 3=連線狀態, 4=速率/雙工, 5=介面
TRACKED_ATTRIBUTES = [
    "ping_reachable", "vlan_id", "acl_rules_applied",
    "link_status", "speed", "duplex", "interface_name",
]

# 屬性中文名稱
ATTRIBUTE_LABELS: dict[str, str] = {
    "speed": "速率",
    "duplex": "雙工",
    "link_status": "連線狀態",
    "ping_reachable": "Ping",
    "interface_name": "介面",
    "vlan_id": "VLAN",
    "acl_rules_applied": "ACL",
}


def _get_transition_ts(records: list, attr: str) -> datetime | None:
    """
    找出某屬性最近一次 None → 非 None 的轉換時間點。

    回傳最後一個 None 之後，第一筆非 None 記錄的 collected_at。
    若歷史無 None 或最末仍為 None，回傳 None。
    """
    last_none_idx = -1
    for i, r in enumerate(records):
        if getattr(r, attr, None) is None:
            last_none_idx = i
    if last_none_idx < 0:
        return None  # 歷史無 None
    if last_none_idx + 1 < len(records):
        return records[last_none_idx + 1].collected_at
    return None  # 最末仍為 None（尚未轉換）


def _detect_change(
    values: list[Any],
    last_collected_at: datetime | None = None,
) -> bool:
    """
    判斷屬性是否有變化。

    規則：
    1. 無快照 → 無變化
    2. 多個不同非空值 → 有變化
    3. 唯一非空值且最近為空 → 無變化（設備維護中/離線屬預期）
    4. 唯一非空值且最近非空，歷史有空值（- → 某狀態）：
       a. 轉換距今 > 15 分鐘 → 無變化（已穩定）
       b. 轉換距今 ≤ 15 分鐘 → 有變化（剛上線/剛變化）
    5. 唯一非空值且歷史無空值 → 無變化（一直穩定）

    Args:
        values: 屬性值序列（按時間排序）。
        last_collected_at: None→值 轉換的時間點（由 _get_transition_ts 計算）。
    """
    if not values:
        return False

    non_null = [v for v in values if v is not None]
    if not non_null:
        return False  # 全部為空

    unique_non_null = set(str(v) for v in non_null)

    if len(unique_non_null) > 1:
        return True  # 規則 2：多個不同值

    # 只有一個唯一非空值
    if values[-1] is None:
        return False  # 規則 3：最近為空 → 設備離線屬預期（正常）

    # 最近是非空值，檢查歷史是否有空值
    if None in values:
        # 歷史有 None（- → 某狀態），需看時間判定
        if last_collected_at is not None:
            now = datetime.now(timezone.utc)
            ts = last_collected_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if (now - ts) > timedelta(minutes=15):
                return False  # 規則 4a：已穩定超過 15 分鐘
        return True  # 規則 4b：剛變化或無時間資訊 → 異常

    return False  # 規則 5：歷史無空值，一直穩定


class CaseService:
    """案件管理服務。"""

    async def sync_cases(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> dict[str, int]:
        """
        同步案件與 MaintenanceMacList。

        為每個 MAC 建立缺失的 Case 列；
        預設指派人來自 default_assignee，若無則使用第一個 ROOT 使用者。

        Returns:
            {"created": N, "total": M}
        """
        # 取得所有 Client
        client_stmt = select(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id,
        )
        client_result = await session.execute(client_stmt)
        client_list = client_result.scalars().all()

        # 取得現有 Case 的 client_id 集合
        case_stmt = select(Case.client_id).where(
            Case.maintenance_id == maintenance_id,
        )
        case_result = await session.execute(case_stmt)
        existing_client_ids = {row[0] for row in case_result.fetchall()}

        # 取得預設 ROOT 使用者
        root_stmt = select(User.display_name).where(
            User.role == UserRole.ROOT,
            User.is_active == True,  # noqa: E712
        ).limit(1)
        root_result = await session.execute(root_stmt)
        default_root = root_result.scalar()

        created = 0
        for client in client_list:
            if client.id in existing_client_ids:
                continue

            assignee = client.default_assignee or default_root
            status = CaseStatus.ASSIGNED if assignee else CaseStatus.UNASSIGNED

            case = Case(
                maintenance_id=maintenance_id,
                client_id=client.id,
                mac_address=client.mac_address.upper(),
                status=status,
                assignee=assignee,
                change_flags={},
            )
            session.add(case)
            created += 1

        if created > 0:
            await session.commit()
            logger.info(
                "同步案件: 新增 %d 筆 maintenance_id=%s",
                created, maintenance_id,
            )
            await write_log(
                level="INFO",
                source="scheduler",
                summary=f"自動同步案件: 新增 {created} 筆",
                module="case_sync",
                maintenance_id=maintenance_id,
            )

        return {"created": created, "total": len(client_list)}

    async def get_cases(
        self,
        maintenance_id: str,
        session: AsyncSession,
        assignee: str | None = None,
        status: str | None = None,
        ping_reachable: bool | None = None,
        search: str | None = None,
        include_resolved: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """
        取得案件列表（含篩選、分頁），按 ping 不可達優先排序。

        合併 MaintenanceMacList 的 ip_address、description、tenant_group。
        預設隱藏已解決案件，除非明確篩選或 include_resolved=True。
        回傳包含預先計算的 change_tags（來自 Case.change_flags）。
        """
        # 查詢案件 + MAC 資訊
        stmt = (
            select(
                Case,
                MaintenanceMacList.ip_address,
                MaintenanceMacList.description,
                MaintenanceMacList.tenant_group,
            )
            .outerjoin(
                MaintenanceMacList,
                Case.client_id == MaintenanceMacList.id,
            )
            .where(Case.maintenance_id == maintenance_id)
        )

        # 篩選
        if assignee:
            stmt = stmt.where(Case.assignee == assignee)
        if status:
            try:
                status_enum = CaseStatus(status)
                stmt = stmt.where(Case.status == status_enum)
            except ValueError:
                pass
        elif not include_resolved:
            # 預設不顯示已解決和不處理案件（除非明確篩選該狀態）
            stmt = stmt.where(Case.status.notin_([
                CaseStatus.RESOLVED, CaseStatus.IGNORED,
            ]))
        if ping_reachable is not None:
            if ping_reachable:
                stmt = stmt.where(Case.last_ping_reachable == True)  # noqa: E712
            else:
                stmt = stmt.where(
                    or_(
                        Case.last_ping_reachable == False,  # noqa: E712
                        Case.last_ping_reachable == None,  # noqa: E711
                    )
                )

        # 搜尋
        if search:
            keywords = search.strip().split()
            search_conditions = []
            for field in [Case.mac_address, MaintenanceMacList.ip_address, MaintenanceMacList.description]:
                field_match = and_(*[field.ilike(f"%{kw}%") for kw in keywords])
                search_conditions.append(field_match)
            stmt = stmt.where(or_(*search_conditions))

        # 計算篩選後總數
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        # 排序：所有分類統一規則
        # 1) 有屬性變化的排前面
        # 2) 變化數量多的排前面
        # 3) 逐級比較變化屬性（ping → VLAN → ACL → 連線狀態 → 速率 → 雙工 → 介面）
        # 4) ping 不可達優先
        # 5) 按 MAC 排序
        from sqlalchemy import literal_column
        _cf = literal_column("COALESCE(CAST(change_flags AS CHAR),'')")
        has_change = case((_cf.like('%true%'), 0), else_=1)

        # 變化數量（用字串長度差異法）
        _cf_len = func.char_length(_cf)
        _cf_no_true = func.char_length(func.replace(_cf, 'true', ''))
        change_count_desc = (_cf_len - _cf_no_true) / 4

        # 逐級比較：每個屬性獨立排序，有變化=0 排前面，無變化=1
        _chg_ping = literal_column(
            "IF(JSON_VALUE(change_flags,'$.ping_reachable')=1,0,1)")
        _chg_vlan = literal_column(
            "IF(JSON_VALUE(change_flags,'$.vlan_id')=1,0,1)")
        _chg_acl = literal_column(
            "IF(JSON_VALUE(change_flags,'$.acl_rules_applied')=1,0,1)")
        _chg_link = literal_column(
            "IF(JSON_VALUE(change_flags,'$.link_status')=1,0,1)")
        _chg_speed = literal_column(
            "IF(JSON_VALUE(change_flags,'$.speed')=1,0,1)")
        _chg_duplex = literal_column(
            "IF(JSON_VALUE(change_flags,'$.duplex')=1,0,1)")
        _chg_iface = literal_column(
            "IF(JSON_VALUE(change_flags,'$.interface_name')=1,0,1)")

        ping_priority = case(
            (Case.last_ping_reachable == None, 0),   # noqa: E711
            (Case.last_ping_reachable == False, 1),   # noqa: E712
            else_=2,
        )

        stmt = stmt.order_by(
            has_change,                # 有變化排前面
            change_count_desc.desc(),  # 變化數量多排前面
            _chg_ping,                 # 0: ping
            _chg_vlan,                 # 1: VLAN
            _chg_acl,                  # 2: ACL
            _chg_link,                 # 3: 連線狀態
            _chg_speed,                # 4: 速率
            _chg_duplex,               # 4: 雙工
            _chg_iface,                # 5: 介面
            ping_priority,             # ping 不可達優先
            Case.mac_address,
        )

        # 分頁
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        result = await session.execute(stmt)
        rows = result.all()

        # 使用預算的 change_flags（由排程 update_change_flags 維護），
        # 不再即時查 client_records，省掉一次大查詢 + N×7 次 _detect_change。
        cases = []
        for case_obj, ip_address, description, tenant_group in rows:
            flags = case_obj.change_flags or {}
            change_tags = [
                {
                    "attribute": attr,
                    "label": ATTRIBUTE_LABELS.get(attr, attr),
                    "has_change": bool(flags.get(attr, False)),
                }
                for attr in TRACKED_ATTRIBUTES
            ]

            cases.append({
                "id": case_obj.id,
                "client_id": case_obj.client_id,
                "maintenance_id": case_obj.maintenance_id,
                "mac_address": case_obj.mac_address,
                "ip_address": ip_address,
                "description": description,
                "tenant_group": tenant_group.value if tenant_group else None,
                "status": case_obj.status.value,
                "assignee": case_obj.assignee,
                "summary": case_obj.summary,
                "last_ping_reachable": case_obj.last_ping_reachable,
                "change_tags": change_tags,
                "created_at": case_obj.created_at.isoformat() if case_obj.created_at else None,
                "updated_at": case_obj.updated_at.isoformat() if case_obj.updated_at else None,
            })

        total_pages = (total + page_size - 1) // page_size if total > 0 else 1

        return {
            "cases": cases,
            "count": len(cases),
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def get_case_stats(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> dict[str, int]:
        """
        取得案件統計。

        active = 排除已解決的案件數（頁面預設顯示的數量）。
        """
        base = select(func.count(Case.id)).where(
            Case.maintenance_id == maintenance_id,
        )
        total = (await session.execute(base)).scalar() or 0

        stats: dict[str, int] = {"total": total}
        for s in CaseStatus:
            cnt = (await session.execute(
                base.where(Case.status == s)
            )).scalar() or 0
            stats[s.value.lower()] = cnt

        # ping 不可達（排除已解決和不處理）
        ping_unreachable = (await session.execute(
            select(func.count(Case.id)).where(
                Case.maintenance_id == maintenance_id,
                Case.status.notin_([CaseStatus.RESOLVED, CaseStatus.IGNORED]),
                or_(
                    Case.last_ping_reachable == False,  # noqa: E712
                    Case.last_ping_reachable == None,  # noqa: E711
                ),
            )
        )).scalar() or 0
        stats["ping_unreachable"] = ping_unreachable

        # active = 排除已解決和不處理
        stats["active"] = total - (stats.get("resolved", 0)) - (stats.get("ignored", 0))

        return stats

    async def compute_change_tags(
        self,
        maintenance_id: str,
        client_id: int,
        session: AsyncSession,
    ) -> list[dict[str, Any]]:
        """
        計算 Client 的屬性變化標籤。

        查詢所有 ClientRecord，對每個追蹤屬性套用變化偵測演算法。
        """
        stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.client_id == client_id,
            )
            .order_by(ClientRecord.collected_at)
        )
        result = await session.execute(stmt)
        records = result.scalars().all()

        tags = []
        for attr in TRACKED_ATTRIBUTES:
            values = [getattr(r, attr, None) for r in records]
            has_change = _detect_change(
                values,
                last_collected_at=_get_transition_ts(records, attr),
            )
            tags.append({
                "attribute": attr,
                "label": ATTRIBUTE_LABELS.get(attr, attr),
                "has_change": has_change,
            })

        return tags

    async def get_change_timeline(
        self,
        maintenance_id: str,
        client_id: int,
        attribute: str,
        session: AsyncSession,
    ) -> list[dict[str, Any]]:
        """取得某屬性的完整變化時間線。"""
        if attribute not in TRACKED_ATTRIBUTES:
            return []

        stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.client_id == client_id,
            )
            .order_by(ClientRecord.collected_at.desc())
        )
        result = await session.execute(stmt)
        records = result.scalars().all()

        timeline = []
        for r in records:
            value = getattr(r, attribute, None)
            timeline.append({
                "value": value,
                "collected_at": r.collected_at.isoformat() if r.collected_at else None,
                "switch_hostname": r.switch_hostname,
            })

        return timeline

    async def get_case_detail(
        self,
        case_id: int,
        maintenance_id: str,
        session: AsyncSession,
    ) -> dict[str, Any] | None:
        """取得案件詳情（含變化標籤和筆記）。"""
        stmt = (
            select(
                Case,
                MaintenanceMacList.ip_address,
                MaintenanceMacList.description,
                MaintenanceMacList.tenant_group,
            )
            .outerjoin(
                MaintenanceMacList,
                Case.client_id == MaintenanceMacList.id,
            )
            .where(
                Case.id == case_id,
                Case.maintenance_id == maintenance_id,
            )
        )
        result = await session.execute(stmt)
        row = result.first()

        if not row:
            return None

        case_obj, ip_address, description, tenant_group = row

        # 變化標籤
        change_tags = await self.compute_change_tags(
            maintenance_id, case_obj.client_id, session,
        )

        # 筆記
        notes_stmt = (
            select(CaseNote)
            .where(CaseNote.case_id == case_id)
            .order_by(CaseNote.created_at.desc())
        )
        notes_result = await session.execute(notes_stmt)
        notes = [
            {
                "id": n.id,
                "author": n.author,
                "content": n.content,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes_result.scalars().all()
        ]

        # 採集異常
        from app.db.models import CollectionError

        err_stmt = select(CollectionError).where(
            CollectionError.maintenance_id == maintenance_id,
        )
        err_result = await session.execute(err_stmt)
        collection_errors = err_result.scalars().all()

        # 最新 ClientRecord 快照
        latest_cr_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.client_id == case_obj.client_id,
            )
            .order_by(ClientRecord.collected_at.desc())
            .limit(1)
        )
        latest_cr = (await session.execute(latest_cr_stmt)).scalar()

        return {
            "id": case_obj.id,
            "client_id": case_obj.client_id,
            "maintenance_id": case_obj.maintenance_id,
            "mac_address": case_obj.mac_address,
            "ip_address": ip_address,
            "description": description,
            "tenant_group": tenant_group.value if tenant_group else None,
            "status": case_obj.status.value,
            "assignee": case_obj.assignee,
            "summary": case_obj.summary,
            "last_ping_reachable": case_obj.last_ping_reachable,
            "change_tags": change_tags,
            "notes": notes,
            "latest_snapshot": {
                "speed": latest_cr.speed if latest_cr else None,
                "duplex": latest_cr.duplex if latest_cr else None,
                "link_status": latest_cr.link_status if latest_cr else None,
                "interface_name": latest_cr.interface_name if latest_cr else None,
                "vlan_id": latest_cr.vlan_id if latest_cr else None,
                "switch_hostname": latest_cr.switch_hostname if latest_cr else None,
                "ping_reachable": latest_cr.ping_reachable if latest_cr else None,
                "acl_rules_applied": latest_cr.acl_rules_applied if latest_cr else None,
                "collected_at": latest_cr.collected_at.isoformat() if latest_cr and latest_cr.collected_at else None,
            } if latest_cr else None,
            "collection_errors": [
                {
                    "collection_type": e.collection_type,
                    "switch_hostname": e.switch_hostname,
                    "error_message": e.error_message,
                    "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
                }
                for e in collection_errors
            ],
            "created_at": case_obj.created_at.isoformat() if case_obj.created_at else None,
            "updated_at": case_obj.updated_at.isoformat() if case_obj.updated_at else None,
        }

    async def update_case(
        self,
        case_id: int,
        maintenance_id: str,
        user_display_name: str,
        user_role: str,
        session: AsyncSession,
        summary: str | None = None,
        status: str | None = None,
        assignee: str | None = None,
    ) -> dict[str, Any] | None:
        """
        更新案件。

        權限規則（每筆案件的寫入權限只屬於一個人）：
        - 已指派案件：只有被指派人可以操作（含狀態、摘要、轉交）
        - 未指派案件：ROOT/PM 可以指派
        """
        stmt = select(Case).where(
            Case.id == case_id,
            Case.maintenance_id == maintenance_id,
        )
        result = await session.execute(stmt)
        case = result.scalar_one_or_none()

        if not case:
            return None

        is_root = user_role == UserRole.ROOT.value
        is_pm = user_role == UserRole.PM.value
        is_assignee = case.assignee == user_display_name

        # 狀態/摘要只有被指派人可改
        if (summary is not None or status is not None) and not is_assignee:
            return {"error": "只有被指派人可以修改案件內容"}

        # 指派人變更：已有指派人時只有被指派人可轉交，無指派人時 ROOT/PM 可指派
        if assignee is not None:
            if case.assignee:
                if not is_assignee:
                    return {"error": "只有當前被指派人可以轉交案件"}
                if case.status == CaseStatus.RESOLVED:
                    return {"error": "已結案的案件無法轉交，請先重啟案件"}
            else:
                if not is_root and not is_pm:
                    return {"error": "只有管理員或 PM 可以指派案件"}

        if summary is not None:
            case.summary = summary.strip() if summary else None

        if status is not None:
            try:
                new_status = CaseStatus(status)
            except ValueError:
                return {"error": f"無效的狀態值: {status}"}
            # Ping 不可達時不允許手動標記為已結案
            if new_status == CaseStatus.RESOLVED and case.last_ping_reachable is not True:
                return {"error": "Ping 不可達時無法標記為已結案"}
            case.status = new_status

        if assignee is not None:
            # 驗證新的被指派人存在且啟用
            if assignee:
                user_stmt = select(User).where(
                    User.display_name == assignee,
                    User.is_active == True,  # noqa: E712
                )
                user_result = await session.execute(user_stmt)
                target_user = user_result.scalar_one_or_none()
                if not target_user:
                    return {"error": f"找不到使用者: {assignee}"}
                case.assignee = assignee
                if case.status == CaseStatus.UNASSIGNED:
                    case.status = CaseStatus.ASSIGNED
            else:
                case.assignee = None
                case.status = CaseStatus.UNASSIGNED

        await session.commit()
        await session.refresh(case)

        return {
            "id": case.id,
            "status": case.status.value,
            "assignee": case.assignee,
            "summary": case.summary,
            "updated_at": case.updated_at.isoformat() if case.updated_at else None,
        }

    async def add_note(
        self,
        case_id: int,
        maintenance_id: str,
        author: str,
        user_role: str,
        content: str,
        session: AsyncSession,
    ) -> dict[str, Any] | None:
        """新增筆記（任何登入使用者皆可新增，作為討論區）。"""
        stmt = select(Case).where(
            Case.id == case_id,
            Case.maintenance_id == maintenance_id,
        )
        result = await session.execute(stmt)
        case = result.scalar_one_or_none()

        if not case:
            return None

        note = CaseNote(
            case_id=case_id,
            author=author,
            content=content.strip(),
        )
        session.add(note)
        await session.commit()
        await session.refresh(note)

        return {
            "id": note.id,
            "author": note.author,
            "content": note.content,
            "created_at": note.created_at.isoformat() if note.created_at else None,
        }

    async def update_note(
        self,
        note_id: int,
        case_id: int,
        user_display_name: str,
        user_role: str,
        content: str,
        session: AsyncSession,
    ) -> dict[str, Any] | None:
        """修改筆記（只有原作者可修改）。"""
        stmt = select(CaseNote).where(
            CaseNote.id == note_id,
            CaseNote.case_id == case_id,
        )
        result = await session.execute(stmt)
        note = result.scalar_one_or_none()

        if not note:
            return None

        if note.author != user_display_name:
            return {"error": "只有原作者可以修改筆記"}

        note.content = content.strip()
        await session.commit()
        await session.refresh(note)

        return {
            "id": note.id,
            "author": note.author,
            "content": note.content,
            "created_at": note.created_at.isoformat() if note.created_at else None,
        }

    async def delete_note(
        self,
        note_id: int,
        case_id: int,
        user_display_name: str,
        user_role: str,
        session: AsyncSession,
    ) -> dict[str, Any] | None:
        """刪除筆記（只有原作者可刪除）。"""
        stmt = select(CaseNote).where(
            CaseNote.id == note_id,
            CaseNote.case_id == case_id,
        )
        result = await session.execute(stmt)
        note = result.scalar_one_or_none()

        if not note:
            return None

        if note.author != user_display_name:
            return {"error": "只有原作者可以刪除筆記"}

        await session.delete(note)
        await session.commit()

        return {"deleted": True}

    async def update_ping_status(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> None:
        """
        從最新 ClientRecord 更新所有 Case 的 last_ping_reachable 和 ping_reachable_since。

        - ping_reachable_since: 紀錄 ping 首次轉為可達的時間，用於 anti-flapping。
          - 不可達 → 可達：設為 now()
          - 可達 → 可達：保持原值不變
          - 可達 → 不可達：清除為 NULL
        """
        now = datetime.now(timezone.utc)

        # 取得每個 client_id 最新的 ClientRecord
        latest_subq = (
            select(
                ClientRecord.client_id,
                ClientRecord.ping_reachable,
                func.row_number().over(
                    partition_by=ClientRecord.client_id,
                    order_by=ClientRecord.collected_at.desc(),
                ).label("rn"),
            )
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.client_id.isnot(None),
            )
            .subquery()
        )

        latest_stmt = (
            select(latest_subq.c.client_id, latest_subq.c.ping_reachable)
            .where(latest_subq.c.rn == 1)
        )
        result = await session.execute(latest_stmt)
        latest_pings = result.fetchall()

        # 取得現有 Case 的 ping 狀態
        case_stmt = select(
            Case.client_id, Case.last_ping_reachable, Case.ping_reachable_since,
        ).where(Case.maintenance_id == maintenance_id)
        case_result = await session.execute(case_stmt)
        case_states = {
            row[0]: (row[1], row[2])
            for row in case_result.fetchall()
        }

        for client_id, ping_reachable in latest_pings:
            old_reachable, old_since = case_states.get(client_id, (None, None))

            # 計算 ping_reachable_since
            if ping_reachable is True:
                if old_reachable is True and old_since is not None:
                    # 持續可達：保持原始時間
                    new_since = old_since
                else:
                    # 新轉為可達：記錄起始時間
                    new_since = now
            else:
                # 不可達或未知：清除計時器
                new_since = None

            await session.execute(
                update(Case)
                .where(
                    Case.maintenance_id == maintenance_id,
                    Case.client_id == client_id,
                )
                .values(
                    last_ping_reachable=ping_reachable,
                    ping_reachable_since=new_since,
                )
            )

        await session.commit()

    async def auto_resolve_reachable(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> int:
        """
        自動結案：Ping 可達 → 直接標記為已結案。

        若隨後 Ping 又不可達，auto_reopen_unreachable 會將案件重開為 ASSIGNED，
        使用者接受後變為 IN_PROGRESS，IN_PROGRESS 和 DISCUSSING 不受自動結案影響。

        不影響正在處理中（IN_PROGRESS）或待討論（DISCUSSING）的案件。
        """
        stmt = (
            update(Case)
            .where(
                Case.maintenance_id == maintenance_id,
                Case.last_ping_reachable == True,  # noqa: E712
                Case.status.notin_([
                    CaseStatus.RESOLVED,
                    CaseStatus.IN_PROGRESS,
                    CaseStatus.DISCUSSING,
                    CaseStatus.IGNORED,
                ]),
            )
            .values(status=CaseStatus.RESOLVED)
        )
        result = await session.execute(stmt)
        await session.commit()

        resolved = result.rowcount
        if resolved > 0:
            logger.info(
                "Auto-resolved %d reachable cases for %s",
                resolved, maintenance_id,
            )
            await write_log(
                level="INFO",
                source="scheduler",
                summary=f"自動結案 {resolved} 筆（Ping 可達）",
                module="auto_resolve",
                maintenance_id=maintenance_id,
            )
        return resolved

    async def auto_reopen_unreachable(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> int:
        """
        自動重開：已結案案件若 Ping 變為不可達 → 回到已指派狀態。

        被指派人需要重新「接受」案件才能繼續處理。
        """
        stmt = (
            update(Case)
            .where(
                Case.maintenance_id == maintenance_id,
                Case.status == CaseStatus.RESOLVED,
                or_(
                    Case.last_ping_reachable == False,  # noqa: E712
                    Case.last_ping_reachable == None,  # noqa: E711
                ),
            )
            .values(status=CaseStatus.ASSIGNED)
        )
        result = await session.execute(stmt)
        await session.commit()

        reopened = result.rowcount
        if reopened > 0:
            logger.info(
                "Auto-reopened %d unreachable resolved cases for %s",
                reopened, maintenance_id,
            )
            await write_log(
                level="WARNING",
                source="scheduler",
                summary=f"自動重開 {reopened} 筆（Ping 變為不可達）",
                module="auto_reopen",
                maintenance_id=maintenance_id,
            )
        return reopened

    async def update_change_flags(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> int:
        """
        批量更新所有 Case 的 change_flags（預先計算屬性變化）。

        對每個 Case 的 MAC，查詢 ClientRecord 並偵測各屬性變化，
        結果存入 Case.change_flags JSON 欄位。
        """
        # 取得所有 Case 的 client_id
        case_stmt = select(Case.id, Case.client_id).where(
            Case.maintenance_id == maintenance_id,
        )
        case_result = await session.execute(case_stmt)
        case_rows = case_result.fetchall()

        if not case_rows:
            return 0

        # 一次查詢所有 ClientRecord（避免 N+1，排除系統標記）
        all_records_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.client_id.isnot(None),
            )
            .order_by(ClientRecord.client_id, ClientRecord.collected_at)
        )
        records_result = await session.execute(all_records_stmt)
        all_records = records_result.scalars().all()

        # 按 client_id 分組
        from collections import defaultdict
        records_by_client: dict[int, list] = defaultdict(list)
        for r in all_records:
            if r.client_id:
                records_by_client[r.client_id].append(r)

        updated = 0
        for case_id, client_id in case_rows:
            records = records_by_client.get(client_id, [])
            flags = {}
            for attr in TRACKED_ATTRIBUTES:
                values = [getattr(r, attr, None) for r in records]
                flags[attr] = _detect_change(
                    values,
                    last_collected_at=_get_transition_ts(records, attr),
                )

            await session.execute(
                update(Case)
                .where(Case.id == case_id)
                .values(change_flags=flags)
            )
            updated += 1

        await session.commit()

        if updated > 0:
            logger.info(
                "Updated change_flags for %d cases in %s",
                updated, maintenance_id,
            )
        return updated
