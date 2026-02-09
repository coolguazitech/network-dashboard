"""
Change Detection Cache.

在資料流上游（fetch → parse → 存 DB 之前）用 SHA-256 hash 比對
上一次的採集結果，如果沒有變化就跳過 DB 寫入。

兩種快取：
- IndicatorChangeCache: 8 個指標類型，per-device per-indicator
- ClientChangeCache: 客戶端資料，per-maintenance

快取實例掛在 Service 類別上（Service 都是 singleton），
服務重啟後快取清空 → 第一輪一定寫入 DB。
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


def compute_indicator_hash(parsed_items: list[BaseModel]) -> str:
    """對 parsed_items 排序後 JSON 序列化取 SHA-256。"""
    data = sorted(item.model_dump_json() for item in parsed_items)
    return hashlib.sha256("".join(data).encode()).hexdigest()


def compute_client_hash(records: list[Any]) -> str:
    """對 ClientRecord 關鍵欄位取 hash。

    Args:
        records: list of ClientRecord (ORM objects, not yet flushed)
    """
    key_fields = []
    for r in sorted(
        records,
        key=lambda x: (x.mac_address or "", x.switch_hostname or ""),
    ):
        key_fields.append(
            f"{r.mac_address}|{r.switch_hostname}|{r.interface_name}|"
            f"{r.vlan_id}|{r.speed}|{r.duplex}|{r.link_status}|"
            f"{r.ping_reachable}|{r.acl_passes}"
        )
    return hashlib.sha256("\n".join(key_fields).encode()).hexdigest()


class IndicatorChangeCache:
    """
    Per-device, per-indicator hash 快取。

    key = (maintenance_id, collection_type, hostname)
    value = SHA-256 hash of parsed_items
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, str, str], str] = {}

    def has_changed(
        self,
        maintenance_id: str,
        collection_type: str,
        hostname: str,
        parsed_items: list[BaseModel],
    ) -> bool:
        """比對 hash，回傳 True 表示資料有變化（或首次見到）。"""
        key = (maintenance_id, collection_type, hostname)
        new_hash = compute_indicator_hash(parsed_items)
        old_hash = self._store.get(key)
        if old_hash == new_hash:
            return False
        self._store[key] = new_hash
        return True

    def clear(self) -> None:
        self._store.clear()


class ClientChangeCache:
    """
    Per-maintenance hash 快取。

    key = maintenance_id
    value = SHA-256 hash of all ClientRecord key fields
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def has_changed(
        self,
        maintenance_id: str,
        records: list[Any],
    ) -> bool:
        """比對 hash，回傳 True 表示資料有變化（或首次見到）。"""
        new_hash = compute_client_hash(records)
        old_hash = self._store.get(maintenance_id)
        if old_hash == new_hash:
            return False
        self._store[maintenance_id] = new_hash
        return True

    def clear(self) -> None:
        self._store.clear()
