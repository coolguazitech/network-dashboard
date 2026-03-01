"""
Database ORM models.

All table/column definitions are aligned with the production MariaDB schema.
Tables marked "local only" exist in our codebase but not yet in production.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import CaseStatus, ClientDetectionStatus, MealDeliveryStatus, TenantGroup, UserRole
from app.db.base import Base


# ══════════════════════════════════════════════════════════════════
# 使用者
# ══════════════════════════════════════════════════════════════════


class User(Base):
    """使用者帳號。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole),
        default=UserRole.GUEST,
    )
    maintenance_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"


# ══════════════════════════════════════════════════════════════════
# 歲修管理
# ══════════════════════════════════════════════════════════════════


class MaintenanceConfig(Base):
    """
    歲修設定。

    Scheduler 查詢 is_active=True 的歲修，對其設備執行採集。
    """

    __tablename__ = "maintenance_configs"

    id = Column(Integer, primary_key=True, index=True)
    maintenance_id = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(200), nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    anchor_time = Column(DateTime, nullable=True, index=True)
    is_active = Column(Boolean, default=False, nullable=False)
    config_data = Column(JSON, nullable=True)

    # 累計活躍計時器（local only — 尚未同步至生產）
    active_seconds_accumulated = Column(Integer, default=0, nullable=False)
    last_activated_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    updated_at = Column(DateTime, server_default=text('CURRENT_TIMESTAMP'), onupdate=text('CURRENT_TIMESTAMP'))


# 設備廠商選項
DEVICE_VENDOR_OPTIONS = ["HPE", "Cisco-IOS", "Cisco-NXOS"]


class MaintenanceDeviceList(Base):
    """歲修設備對應清單。"""

    __tablename__ = "maintenance_device_list"
    __table_args__ = (
        UniqueConstraint(
            'maintenance_id', 'old_hostname', name='uk_maintenance_old_hostname'
        ),
        UniqueConstraint(
            'maintenance_id', 'new_hostname', name='uk_maintenance_new_hostname'
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    maintenance_id = Column(String(100), index=True, nullable=False)

    # 舊設備資訊（可為 NULL，表示新設備無舊設備對應）
    old_hostname = Column(String(255), index=True, nullable=True)
    old_ip_address = Column(String(45), nullable=True)
    old_vendor = Column(String(50), nullable=True)

    # 新設備資訊（可為 NULL，表示舊設備無新設備對應）
    new_hostname = Column(String(255), index=True, nullable=True)
    new_ip_address = Column(String(45), nullable=True)
    new_vendor = Column(String(50), nullable=True)

    # 是否實體換機
    is_replaced = Column(Boolean, nullable=False, default=False, server_default=text('0'))
    # 新舊設備是否使用相同 port
    use_same_port = Column(Boolean, nullable=True)

    description = Column(String(500), nullable=True)

    tenant_group = Column(
        Enum(TenantGroup),
        nullable=False,
        default=TenantGroup.F18,
    )

    # 設備 Ping 可達性（由 device_ping 回寫）
    old_is_reachable = Column(Boolean, nullable=True)
    old_last_check_at = Column(DateTime, nullable=True)
    new_is_reachable = Column(Boolean, nullable=True)
    new_last_check_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    updated_at = Column(
        DateTime, server_default=text('CURRENT_TIMESTAMP'), onupdate=text('CURRENT_TIMESTAMP')
    )

    def __repr__(self) -> str:
        return f"<MaintenanceDeviceList {self.old_hostname or '(none)'} -> {self.new_hostname or '(none)'}>"


# ══════════════════════════════════════════════════════════════════
# 採集資料 (CollectionBatch + Typed Records)
# ══════════════════════════════════════════════════════════════════


class CollectionBatch(Base):
    """採集批次表。"""

    __tablename__ = "collection_batches"
    __table_args__ = (
        Index(
            "ix_collection_batches_lookup",
            "collection_type", "maintenance_id", "switch_hostname",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    collection_type: Mapped[str] = mapped_column(String(100), index=True)
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True,
    )

    def __repr__(self) -> str:
        return f"<CollectionBatch {self.collection_type}@{self.switch_hostname}>"


class LatestCollectionBatch(Base):
    """
    最新採集狀態指標（基準 + 變化點策略）。

    local only — 尚未同步至生產。
    """

    __tablename__ = "latest_collection_batches"
    __table_args__ = (
        UniqueConstraint(
            "maintenance_id", "collection_type", "switch_hostname",
            name="uk_latest_batch",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collection_type: Mapped[str] = mapped_column(String(100))
    switch_hostname: Mapped[str] = mapped_column(String(255))
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"),
        index=True,
    )
    data_hash: Mapped[str] = mapped_column(String(16))
    collected_at: Mapped[datetime] = mapped_column(DateTime)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime)

    def __repr__(self) -> str:
        return (
            f"<LatestCollectionBatch {self.collection_type}"
            f"@{self.switch_hostname}>"
        )


# ── Typed Record Models ──────────────────────────────────────────


class TransceiverRecord(Base):
    """光模組診斷數據（對應 transceiver_records）。"""

    __tablename__ = "transceiver_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"), index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    interface_name: Mapped[str] = mapped_column(String(100))
    tx_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    rx_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    voltage: Mapped[float | None] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<TransceiverRecord {self.switch_hostname}:{self.interface_name}>"


class PortChannelRecord(Base):
    """Port-Channel / LAG 記錄（對應 port_channel_records）。"""

    __tablename__ = "port_channel_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"), index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    interface_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50))
    members: Mapped[list | None] = mapped_column(JSON, nullable=True)
    member_status: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<PortChannelRecord {self.switch_hostname}:{self.interface_name}>"


class NeighborRecord(Base):
    """CDP/LLDP 鄰居記錄（對應 neighbor_records）。"""

    __tablename__ = "neighbor_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"), index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    local_interface: Mapped[str] = mapped_column(String(100))
    remote_hostname: Mapped[str] = mapped_column(String(255))
    remote_interface: Mapped[str] = mapped_column(String(100))

    def __repr__(self) -> str:
        return f"<NeighborRecord {self.switch_hostname}:{self.local_interface}>"


class InterfaceErrorRecord(Base):
    """介面錯誤計數（對應 interface_error_records）。"""

    __tablename__ = "interface_error_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"), index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    interface_name: Mapped[str] = mapped_column(String(100))
    crc_errors: Mapped[int] = mapped_column(Integer, default=0)
    input_errors: Mapped[int] = mapped_column(Integer, default=0)
    output_errors: Mapped[int] = mapped_column(Integer, default=0)
    collisions: Mapped[int] = mapped_column(Integer, default=0)
    giants: Mapped[int] = mapped_column(Integer, default=0)
    runts: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<InterfaceErrorRecord {self.switch_hostname}:{self.interface_name}>"


class StaticAclRecord(Base):
    """Static ACL 綁定（local only）。"""

    __tablename__ = "static_acl_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"), index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    interface_name: Mapped[str] = mapped_column(String(100))
    acl_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:
        return f"<StaticAclRecord {self.switch_hostname}:{self.interface_name}>"


class DynamicAclRecord(Base):
    """Dynamic ACL 綁定（local only）。"""

    __tablename__ = "dynamic_acl_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"), index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    interface_name: Mapped[str] = mapped_column(String(100))
    acl_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:
        return f"<DynamicAclRecord {self.switch_hostname}:{self.interface_name}>"



class MacTableRecord(Base):
    """MAC 位址表（local only）。"""

    __tablename__ = "mac_table_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"), index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    mac_address: Mapped[str] = mapped_column(String(17))
    interface_name: Mapped[str] = mapped_column(String(100))
    vlan_id: Mapped[int] = mapped_column(Integer)

    def __repr__(self) -> str:
        return f"<MacTableRecord {self.switch_hostname}:{self.mac_address}>"


class FanRecord(Base):
    """風扇狀態。"""

    __tablename__ = "fan_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"), index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    fan_id: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50))

    def __repr__(self) -> str:
        return f"<FanRecord {self.switch_hostname}:{self.fan_id}>"


class PowerRecord(Base):
    """電源供應器狀態。"""

    __tablename__ = "power_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"), index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    ps_id: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50))

    def __repr__(self) -> str:
        return f"<PowerRecord {self.switch_hostname}:{self.ps_id}>"


class VersionRecord(Base):
    """韌體版本。"""

    __tablename__ = "version_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"), index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    version: Mapped[str] = mapped_column(String(255))

    def __repr__(self) -> str:
        return f"<VersionRecord {self.switch_hostname}:{self.version}>"


class PingRecord(Base):
    """Ping 可達性記錄。"""

    __tablename__ = "ping_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"), index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    target: Mapped[str] = mapped_column(String(255))
    is_reachable: Mapped[bool] = mapped_column(Boolean)

    def __repr__(self) -> str:
        return f"<PingRecord {self.switch_hostname}:{self.target}>"


class InterfaceStatusRecord(Base):
    """介面狀態記錄（速率/雙工/連線狀態）。"""

    __tablename__ = "interface_status_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"), index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    interface_name: Mapped[str] = mapped_column(String(100))
    link_status: Mapped[str] = mapped_column(String(20))
    speed: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duplex: Mapped[str | None] = mapped_column(String(20), nullable=True)

    def __repr__(self) -> str:
        return f"<InterfaceStatusRecord {self.switch_hostname}:{self.interface_name}>"


# ══════════════════════════════════════════════════════════════════
# 期望值（Expectations）
# ══════════════════════════════════════════════════════════════════


class VersionExpectation(Base):
    """版本期望值。"""

    __tablename__ = "version_expectations"
    __table_args__ = (
        UniqueConstraint(
            "maintenance_id", "hostname",
            name="uk_version_expectation",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    hostname: Mapped[str] = mapped_column(String(255), index=True)
    expected_versions: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


class UplinkExpectation(Base):
    """Uplink 拓樸期望值。"""

    __tablename__ = "uplink_expectations"
    __table_args__ = (
        UniqueConstraint(
            "maintenance_id", "hostname", "local_interface",
            name="uk_uplink_expectation",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    hostname: Mapped[str] = mapped_column(String(255), index=True)
    local_interface: Mapped[str] = mapped_column(String(100))
    expected_neighbor: Mapped[str] = mapped_column(String(255))
    expected_interface: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


class PortChannelExpectation(Base):
    """Port-Channel 期望值。"""

    __tablename__ = "port_channel_expectations"
    __table_args__ = (
        UniqueConstraint(
            "maintenance_id", "hostname", "port_channel",
            name="uk_port_channel_expectation",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    hostname: Mapped[str] = mapped_column(String(255), index=True)
    port_channel: Mapped[str] = mapped_column(String(100))
    member_interfaces: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


# ══════════════════════════════════════════════════════════════════
# 錯誤追蹤 + 審計日誌
# ══════════════════════════════════════════════════════════════════


class CollectionError(Base):
    """採集錯誤記錄（current-state 表）。"""

    __tablename__ = "collection_errors"
    __table_args__ = (
        UniqueConstraint(
            "maintenance_id", "collection_type", "switch_hostname",
            name="uk_collection_error",
        ),
    )

    id = Column(Integer, primary_key=True)
    maintenance_id = Column(String(100), index=True, nullable=False)
    collection_type = Column(String(100), nullable=False)
    switch_hostname = Column(String(255), nullable=False)
    error_message = Column(Text, nullable=False)
    occurred_at = Column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

    def __repr__(self) -> str:
        return f"<CollectionError {self.collection_type}@{self.switch_hostname}>"


class SystemLog(Base):
    """系統日誌（audit log）。"""

    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True)
    level = Column(String(20), index=True, nullable=False)
    source = Column(String(50), index=True, nullable=False)
    module = Column(String(200), nullable=True)
    summary = Column(String(500), nullable=False)
    detail = Column(Text, nullable=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String(100), nullable=True)
    maintenance_id = Column(String(100), nullable=True, index=True)
    request_path = Column(String(500), nullable=True)
    request_method = Column(String(10), nullable=True)
    status_code = Column(Integer, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, server_default=text('CURRENT_TIMESTAMP'), index=True)

    def __repr__(self) -> str:
        return f"<SystemLog [{self.level}] {self.source}: {self.summary[:30]}>"


# ══════════════════════════════════════════════════════════════════
# 閾值設定
# ══════════════════════════════════════════════════════════════════


class ThresholdConfig(Base):
    """Per-maintenance 閾值覆寫。"""

    __tablename__ = "threshold_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True,
    )

    transceiver_tx_power_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    transceiver_tx_power_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    transceiver_rx_power_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    transceiver_rx_power_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    transceiver_temperature_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    transceiver_temperature_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    transceiver_voltage_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    transceiver_voltage_max: Mapped[float | None] = mapped_column(Float, nullable=True)


    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<ThresholdConfig {self.maintenance_id}>"


# ══════════════════════════════════════════════════════════════════
# 指標結果
# ══════════════════════════════════════════════════════════════════


class IndicatorResult(Base):
    """指標評估結果（歷史記錄）。"""

    __tablename__ = "indicator_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    indicator_type: Mapped[str] = mapped_column(String(100), index=True)
    maintenance_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True,
    )
    pass_rates: Mapped[str] = mapped_column(JSON)
    total_count: Mapped[int] = mapped_column(Integer)
    pass_count: Mapped[int] = mapped_column(Integer)
    fail_count: Mapped[int] = mapped_column(Integer)
    details: Mapped[str | None] = mapped_column(JSON, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True,
    )

    def __repr__(self) -> str:
        return f"<IndicatorResult {self.indicator_type} {self.pass_count}/{self.total_count}>"


# ══════════════════════════════════════════════════════════════════
# 業務模型
# ══════════════════════════════════════════════════════════════════



class Checkpoint(Base):
    """歲修檢查點。"""

    __tablename__ = "checkpoints"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(200))
    checkpoint_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_data: Mapped[str | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(),
    )


class ClientCategory(Base):
    """客戶分類。"""

    __tablename__ = "client_categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


class ClientCategoryMember(Base):
    """客戶分類成員。"""

    __tablename__ = "client_category_members"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("client_categories.id"), index=True,
    )
    mac_address: Mapped[str] = mapped_column(String(17), index=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(),
    )


class ClientComparison(Base):
    """客戶比較記錄。"""

    __tablename__ = "client_comparisons"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True,
    )
    collected_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True, server_default=func.now(),
    )
    mac_address: Mapped[str | None] = mapped_column(String(17), nullable=True, index=True)

    # 舊設備端
    old_ip_address: Mapped[str | None] = mapped_column(String(15), nullable=True)
    old_switch_hostname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    old_interface_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    old_vlan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_speed: Mapped[str | None] = mapped_column(String(20), nullable=True)
    old_duplex: Mapped[str | None] = mapped_column(String(20), nullable=True)
    old_link_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    old_ping_reachable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # 新設備端
    new_ip_address: Mapped[str | None] = mapped_column(String(15), nullable=True)
    new_switch_hostname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_interface_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_vlan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_speed: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_duplex: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_link_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_ping_reachable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    differences: Mapped[str | None] = mapped_column(JSON, nullable=True)
    is_changed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


class ClientRecord(Base):
    """客戶記錄。"""

    __tablename__ = "client_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True,
    )
    collected_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, server_default=func.now(),
    )
    mac_address: Mapped[str | None] = mapped_column(String(17), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(15), nullable=True, index=True)
    switch_hostname: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True,
    )
    interface_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vlan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    speed: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duplex: Mapped[str | None] = mapped_column(String(20), nullable=True)
    link_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ping_reachable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    acl_rules_applied: Mapped[str | None] = mapped_column(JSON, nullable=True)
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_data: Mapped[str | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(),
    )


class LatestClientRecord(Base):
    """
    Per-MAC 變化偵測指標（基準 + 變化點策略）。

    與 LatestCollectionBatch 相同模式，但以 (maintenance_id, mac_address) 為 key。
    每次 ClientCollectionService 組裝 ClientRecord 時，比對 data_hash：
    - hash 相同 → 只更新 last_checked_at，不寫新 ClientRecord
    - hash 不同 → 寫新 ClientRecord，更新 data_hash
    """

    __tablename__ = "latest_client_records"
    __table_args__ = (
        UniqueConstraint(
            "maintenance_id", "mac_address",
            name="uk_latest_client_record",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    mac_address: Mapped[str] = mapped_column(String(17))
    data_hash: Mapped[str] = mapped_column(String(16))
    collected_at: Mapped[datetime] = mapped_column(DateTime)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime)

    def __repr__(self) -> str:
        return f"<LatestClientRecord {self.maintenance_id}:{self.mac_address}>"


class SeverityOverride(Base):
    """客戶嚴重度覆寫。"""

    __tablename__ = "client_severity_overrides"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(String(50), index=True)
    mac_address: Mapped[str] = mapped_column(String(20), index=True)
    override_severity: Mapped[str] = mapped_column(String(20))
    original_severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


class ContactCategory(Base):
    """通訊錄分類。"""

    __tablename__ = "contact_categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


class Contact(Base):
    """通訊錄聯絡人。"""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("contact_categories.id"), nullable=True, index=True,
    )
    name: Mapped[str] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    extension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


class MaintenanceMacList(Base):
    """歲修 MAC 清單。"""

    __tablename__ = "maintenance_mac_list"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(String(50), index=True)
    mac_address: Mapped[str] = mapped_column(String(17))
    ip_address: Mapped[str] = mapped_column(String(45))
    tenant_group: Mapped[TenantGroup] = mapped_column(Enum(TenantGroup))
    detection_status: Mapped[ClientDetectionStatus] = mapped_column(
        Enum(ClientDetectionStatus),
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_assignee: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(),
    )


class Case(Base):
    """案件（每個 MAC 一個案件）。"""

    __tablename__ = "cases"
    __table_args__ = (
        UniqueConstraint(
            "maintenance_id", "mac_address",
            name="uk_case_maintenance_mac",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    mac_address: Mapped[str] = mapped_column(String(17), index=True)

    # 狀態與指派
    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus), default=CaseStatus.ASSIGNED,
    )
    assignee: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 案件摘要
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # 快取最新 ping 狀態（由 client collection 更新，用於快速排序）
    last_ping_reachable: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True,
    )

    # Ping 可達起始時間（用於 anti-flapping：持續可達 10 分鐘才自動結案）
    ping_reachable_since: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True,
    )

    # 預先計算的屬性變化旗標 {"speed": true, "duplex": false, ...}
    change_flags: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


class CaseNote(Base):
    """案件筆記（歷史保留，不覆寫）。"""

    __tablename__ = "case_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True,
    )
    author: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class MealZone(Base):
    """餐點配送區域。"""

    __tablename__ = "meal_zones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    zone_code: Mapped[str] = mapped_column(String(20))
    zone_name: Mapped[str] = mapped_column(String(50))
    status: Mapped[MealDeliveryStatus] = mapped_column(Enum(MealDeliveryStatus))
    expected_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    arrived_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    meal_count: Mapped[int] = mapped_column(Integer, server_default="0")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


class ReferenceClient(Base):
    """參考客戶端。"""

    __tablename__ = "reference_clients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    mac_address: Mapped[str] = mapped_column(String(17), index=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


# ══════════════════════════════════════════════════════════════════
# 交換機管理
# ══════════════════════════════════════════════════════════════════


class Switch(Base):
    """交換機設備資訊。"""

    __tablename__ = "switches"

    id = Column(Integer, primary_key=True)
    hostname = Column(String(255), unique=True, nullable=False, index=True)
    ip_address = Column(String(45), unique=True, nullable=False)
    vendor = Column(String(100), nullable=False)
    platform = Column(String(100), nullable=False)
    site = Column(String(200), nullable=True)
    model = Column(String(200), nullable=True)
    location = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    updated_at = Column(DateTime, server_default=text('CURRENT_TIMESTAMP'), onupdate=func.now())
