"""
Database ORM models.

Defines all database tables and relationships.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    Column,
    Integer,
    Float,
    Boolean,
)

from app.core.enums import (
    MaintenancePhase,
    PlatformType,
    SiteType,
    VendorType,
)
from app.db.base import Base


class Switch(Base):
    """Switch device model."""

    __tablename__ = "switches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    hostname: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    ip_address: Mapped[str] = mapped_column(String(45), index=True)
    vendor: Mapped[VendorType] = mapped_column(Enum(VendorType))
    platform: Mapped[PlatformType] = mapped_column(Enum(PlatformType))
    site: Mapped[SiteType] = mapped_column(Enum(SiteType))
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    extra_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Switch {self.hostname}>"


class UplinkExpectation(Base):
    """
    Expected uplink connections for verification.

    Stores user-defined expected uplink topology.
    """

    __tablename__ = "uplink_expectations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    hostname: Mapped[str] = mapped_column(String(255), index=True)
    local_interface: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Local interface",
    )
    expected_neighbor: Mapped[str] = mapped_column(
        String(255),
        comment="Expected neighbor hostname",
    )
    expected_interface: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Expected neighbor interface (optional)",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="備註",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<UplinkExpectation {self.hostname}:{self.local_interface}>"


class VersionExpectation(Base):
    """
    Expected software versions for verification.

    Stores user-defined expected firmware/software versions.
    Multiple versions can be specified using semicolon separator.
    """

    __tablename__ = "version_expectations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    hostname: Mapped[str] = mapped_column(String(255), index=True)
    expected_versions: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Expected versions, semicolon-separated (e.g. 16.10.1;16.10.2)",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="備註",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<VersionExpectation {self.hostname}>"


class ArpSource(Base):
    """
    ARP 來源設備。

    指定從哪些 Router/Gateway 獲取 ARP Table，用於對應 MAC → IP。
    """

    __tablename__ = "arp_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    hostname: Mapped[str] = mapped_column(String(255), index=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    priority: Mapped[int] = mapped_column(
        Integer,
        default=100,
        comment="Priority order (lower = higher priority)",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="備註",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<ArpSource {self.hostname}>"


class PortChannelExpectation(Base):
    """
    Port-Channel 期望設定。

    設定指定設備的 Port-Channel 應包含哪些成員介面。
    檢查邏輯：驗證 Port-Channel 是否包含所有指定的實體介面。
    """

    __tablename__ = "port_channel_expectations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    hostname: Mapped[str] = mapped_column(String(255), index=True)
    port_channel: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Port-Channel name (e.g. Po1, Port-channel1)",
    )
    member_interfaces: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Expected member interfaces, semicolon-separated (e.g. Gi1/0/1;Gi1/0/2)",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="備註",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<PortChannelExpectation {self.hostname}:{self.port_channel}>"


class CollectionBatch(Base):
    """
    採集批次表（取代 CollectionRecord）。

    每次 DataCollectionService 對一台設備採集一種指標，產生一個 batch。
    保留 raw_data（除錯用），並作為 typed rows 的 parent。
    """

    __tablename__ = "collection_batches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    collection_type: Mapped[str] = mapped_column(String(100), index=True)
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    phase: Mapped[MaintenancePhase] = mapped_column(
        Enum(MaintenancePhase),
        default=MaintenancePhase.NEW,
    )
    maintenance_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
    )
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        index=True,
    )

    def __repr__(self) -> str:
        return f"<CollectionBatch {self.collection_type}@{self.switch_hostname}>"


# ── Typed Record Models ──────────────────────────────────────────


class TransceiverRecord(Base):
    """光模塊採集記錄（typed table）。"""

    __tablename__ = "transceiver_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"),
        index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    phase: Mapped[MaintenancePhase] = mapped_column(Enum(MaintenancePhase))
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    interface_name: Mapped[str] = mapped_column(String(100))
    tx_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    rx_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    voltage: Mapped[float | None] = mapped_column(Float, nullable=True)
    current: Mapped[float | None] = mapped_column(Float, nullable=True)
    serial_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    part_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    def __repr__(self) -> str:
        return f"<TransceiverRecord {self.switch_hostname}:{self.interface_name}>"


class VersionRecord(Base):
    """韌體版本採集記錄（typed table）。"""

    __tablename__ = "version_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"),
        index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    phase: Mapped[MaintenancePhase] = mapped_column(Enum(MaintenancePhase))
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    version: Mapped[str] = mapped_column(String(255))
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    uptime: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<VersionRecord {self.switch_hostname}:{self.version}>"


class NeighborRecord(Base):
    """LLDP 鄰居採集記錄（typed table，uplink indicator 用）。"""

    __tablename__ = "neighbor_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"),
        index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    phase: Mapped[MaintenancePhase] = mapped_column(Enum(MaintenancePhase))
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    local_interface: Mapped[str] = mapped_column(String(100))
    remote_hostname: Mapped[str] = mapped_column(String(255))
    remote_interface: Mapped[str] = mapped_column(String(100))
    remote_platform: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    def __repr__(self) -> str:
        return f"<NeighborRecord {self.switch_hostname}:{self.local_interface}>"


class PortChannelRecord(Base):
    """Port-Channel 採集記錄（typed table）。"""

    __tablename__ = "port_channel_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"),
        index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    phase: Mapped[MaintenancePhase] = mapped_column(Enum(MaintenancePhase))
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    interface_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50))
    protocol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    members: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    member_status: Mapped[dict[str, str] | None] = mapped_column(
        JSON, nullable=True
    )

    def __repr__(self) -> str:
        return f"<PortChannelRecord {self.switch_hostname}:{self.interface_name}>"


class PowerRecord(Base):
    """電源狀態採集記錄（typed table）。"""

    __tablename__ = "power_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"),
        index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    phase: Mapped[MaintenancePhase] = mapped_column(Enum(MaintenancePhase))
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    ps_id: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50))
    input_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    output_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    capacity_watts: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    actual_output_watts: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    def __repr__(self) -> str:
        return f"<PowerRecord {self.switch_hostname}:{self.ps_id}>"


class FanRecord(Base):
    """風扇狀態採集記錄（typed table）。"""

    __tablename__ = "fan_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"),
        index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    phase: Mapped[MaintenancePhase] = mapped_column(Enum(MaintenancePhase))
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    fan_id: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50))
    speed_rpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    speed_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<FanRecord {self.switch_hostname}:{self.fan_id}>"


class InterfaceErrorRecord(Base):
    """介面錯誤計數採集記錄（typed table）。"""

    __tablename__ = "interface_error_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"),
        index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    phase: Mapped[MaintenancePhase] = mapped_column(Enum(MaintenancePhase))
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


class PingRecord(Base):
    """Ping 可達性採集記錄（typed table）。"""

    __tablename__ = "ping_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("collection_batches.id", ondelete="CASCADE"),
        index=True,
    )
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    phase: Mapped[MaintenancePhase] = mapped_column(Enum(MaintenancePhase))
    maintenance_id: Mapped[str] = mapped_column(String(100), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    target: Mapped[str] = mapped_column(String(255))
    is_reachable: Mapped[bool] = mapped_column(Boolean)
    success_rate: Mapped[float] = mapped_column(Float)
    avg_rtt_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<PingRecord {self.switch_hostname}:{self.target}>"


class IndicatorResult(Base):
    """
    Evaluated indicator results.

    Stores calculated pass rates and scores.
    """

    __tablename__ = "indicator_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    indicator_type: Mapped[str] = mapped_column(String(100), index=True)
    phase: Mapped[MaintenancePhase] = mapped_column(
        Enum(MaintenancePhase),
        default=MaintenancePhase.NEW,
    )
    maintenance_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    pass_rates: Mapped[dict[str, float]] = mapped_column(
        JSON,
        comment="Pass rates for each metric",
    )
    total_count: Mapped[int] = mapped_column(default=0)
    pass_count: Mapped[int] = mapped_column(default=0)
    fail_count: Mapped[int] = mapped_column(default=0)
    details: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        index=True,
    )

    def __repr__(self) -> str:
        return f"<IndicatorResult {self.indicator_type}>"

class ClientRecord(Base):
    """客戶端追蹤記錄。"""
    __tablename__ = "client_records"

    id = Column(Integer, primary_key=True, index=True)
    
    # 基本信息
    maintenance_id = Column(String(50), index=True)
    phase = Column(Enum(MaintenancePhase), index=True)
    collected_at = Column(DateTime, default=datetime.utcnow)
    
    # 客戶端信息
    mac_address = Column(String(17), index=True)  # AA:BB:CC:DD:EE:FF
    ip_address = Column(String(15), index=True, nullable=True)   # IPv4
    
    # 網絡連接信息
    switch_hostname = Column(String(100), index=True)
    interface_name = Column(String(50))
    vlan_id = Column(Integer, nullable=True)
    
    # 性能指標
    speed = Column(String(20), nullable=True)     # 1G, 10G, etc.
    duplex = Column(String(20), nullable=True)    # full, half
    link_status = Column(String(20), nullable=True)  # up, down
    
    # 健康檢查
    ping_reachable = Column(Boolean, nullable=True)
    
    # ACL 檢查
    acl_rules_applied = Column(JSON, nullable=True)
    acl_passes = Column(Boolean, nullable=True)
    
    # 收集的原始數據
    raw_data = Column(Text, nullable=True)
    parsed_data = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class ClientComparison(Base):
    """
    客戶端歲修前後的比較結果。
    
    記錄同一個 MAC 地址在歲修前（old）與歲修後（new）設備的變化情況。
    """
    __tablename__ = "client_comparisons"

    id = Column(Integer, primary_key=True, index=True)
    
    # 基本信息
    maintenance_id = Column(String(50), index=True)
    collected_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # 客戶端識別
    mac_address = Column(String(17), index=True)  # AA:BB:CC:DD:EE:FF
    
    # OLD 階段數據快照（歲修前/舊設備）
    old_ip_address = Column(String(15), nullable=True)
    old_switch_hostname = Column(String(100), nullable=True)
    old_interface_name = Column(String(50), nullable=True)
    old_vlan_id = Column(Integer, nullable=True)
    old_speed = Column(String(20), nullable=True)
    old_duplex = Column(String(20), nullable=True)
    old_link_status = Column(String(20), nullable=True)
    old_ping_reachable = Column(Boolean, nullable=True)
    old_acl_passes = Column(Boolean, nullable=True)
    
    # NEW 階段數據快照（歲修後/新設備）
    new_ip_address = Column(String(15), nullable=True)
    new_switch_hostname = Column(String(100), nullable=True)
    new_interface_name = Column(String(50), nullable=True)
    new_vlan_id = Column(Integer, nullable=True)
    new_speed = Column(String(20), nullable=True)
    new_duplex = Column(String(20), nullable=True)
    new_link_status = Column(String(20), nullable=True)
    new_ping_reachable = Column(Boolean, nullable=True)
    new_acl_passes = Column(Boolean, nullable=True)
    
    # 比較結果
    differences = Column(JSON, nullable=True)  # 記錄哪些欄位有變化
    is_changed = Column(Boolean, default=False)  # 是否有變化
    severity = Column(String(50), nullable=True)  # critical, warning, info
    
    # 額外信息
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Checkpoint(Base):
    """
    Checkpoint model for marking important time points during maintenance.
    
    允許用戶標記歲修過程中的重要時間點並生成快照摘要。
    """
    
    __tablename__ = "checkpoints"
    
    id = Column(Integer, primary_key=True, index=True)
    maintenance_id = Column(String(100), index=True, nullable=False)
    name = Column(String(200), nullable=False)
    checkpoint_time = Column(DateTime, nullable=False, index=True)
    description = Column(Text, nullable=True)
    summary_data = Column(JSON, nullable=True)  # 存儲該時間點的統計摘要
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReferenceClient(Base):
    """
    Reference Client model for always-on test machines.
    
    不斷電機台：歲修期間不會關機的測試設備，
    用於驗證網路連通性，理論上歲修前後應該保持一致。
    """
    
    __tablename__ = "reference_clients"
    
    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String(17), unique=True, index=True, nullable=False)
    description = Column(String(200), nullable=True)
    location = Column(String(200), nullable=True)
    reason = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MaintenanceConfig(Base):
    """
    Maintenance configuration model.
    
    存儲歲修配置，包括 anchor_time（錨點時間）等重要設定。
    """
    
    __tablename__ = "maintenance_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    maintenance_id = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(200), nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    anchor_time = Column(DateTime, nullable=True, index=True)  # 歲修開始錨點時間
    config_data = Column(JSON, nullable=True)  # 其他配置數據
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ClientCategory(Base):
    """
    客戶端機台種類定義。
    
    用戶自定義的機台分類，最多支援 5 個種類。
    每個歲修都有自己獨立的分類體系。
    """
    
    __tablename__ = "client_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    maintenance_id = Column(String(100), index=True, nullable=True)  # 歲修專屬
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    color = Column(String(20), nullable=True)  # 用於前端顯示的顏色代碼
    sort_order = Column(Integer, default=0)  # 排序順序
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    members: Mapped[list["ClientCategoryMember"]] = relationship(
        "ClientCategoryMember",
        back_populates="category",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ClientCategory {self.name} ({self.maintenance_id})>"


class ClientCategoryMember(Base):
    """
    機台種類成員關聯。
    
    記錄哪些 MAC 地址屬於哪個種類。
    一個 MAC 可以屬於多個種類（多對多關係）。
    """
    
    __tablename__ = "client_category_members"
    __table_args__ = (
        # 組合唯一約束：同一分類中不能重複添加同一 MAC
        {'mysql_charset': 'utf8mb4'},
    )
    
    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(
        Integer,
        ForeignKey("client_categories.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # 移除 unique=True，允許同一 MAC 出現在多個分類
    mac_address = Column(String(17), index=True, nullable=False)
    description = Column(String(200), nullable=True)  # 機台備註
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    category: Mapped["ClientCategory"] = relationship(
        "ClientCategory",
        back_populates="members",
    )

    def __repr__(self) -> str:
        return f"<ClientCategoryMember {self.mac_address}>"


class MaintenanceMacList(Base):
    """
    歲修 MAC 清單。
    
    存放該歲修涉及的全部設備 MAC 地址。
    負責人先匯入全部 MAC，之後可選擇性地分到特定分類關注。
    「未分類」= 在此清單但不屬於任何 ClientCategoryMember 的 MAC。
    """

    __tablename__ = "maintenance_mac_list"

    id: Mapped[int] = mapped_column(primary_key=True)
    maintenance_id: Mapped[str] = mapped_column(String(50), index=True)
    mac_address: Mapped[str] = mapped_column(String(17))
    description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint(
            "maintenance_id", "mac_address", name="uk_maintenance_mac"
        ),
    )


# 設備廠商選項
DEVICE_VENDOR_OPTIONS = ["HPE", "Cisco-IOS", "Cisco-NXOS"]


class MaintenanceDeviceList(Base):
    """
    歲修設備對應清單。
    
    每筆資料包含一組新舊設備的對應關係。
    若設備不更換，則新舊設備填同一台。
    """
    
    __tablename__ = "maintenance_device_list"
    __table_args__ = (
        UniqueConstraint(
            'maintenance_id', 'old_hostname', name='uk_maintenance_old_hostname'
        ),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    maintenance_id = Column(String(100), index=True, nullable=False)
    
    # 舊設備資訊（必填）
    old_hostname = Column(String(255), index=True, nullable=False)
    old_ip_address = Column(String(45), nullable=False)
    old_vendor = Column(String(50), nullable=False)  # HPE, Cisco-IOS, Cisco-NXOS
    
    # 新設備資訊（必填）
    new_hostname = Column(String(255), index=True, nullable=False)
    new_ip_address = Column(String(45), nullable=False)
    new_vendor = Column(String(50), nullable=False)  # HPE, Cisco-IOS, Cisco-NXOS
    
    # 對應設定
    use_same_port = Column(Boolean, default=True)  # 是否同埠對應
    
    # 可達性狀態（檢查新設備）
    is_reachable = Column(Boolean, nullable=True)  # NULL=未檢查
    last_check_at = Column(DateTime, nullable=True)
    
    # 備註（選填）
    description = Column(String(500), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<MaintenanceDeviceList {self.old_hostname} -> {self.new_hostname}>"


class SeverityOverride(Base):
    """
    手動覆蓋嚴重程度記錄。
    
    允許用戶手動覆蓋某個 MAC 的嚴重程度判定，
    以便在自動判斷不準確時進行人工調整。
    """
    
    __tablename__ = "client_severity_overrides"
    __table_args__ = (
        UniqueConstraint('maintenance_id', 'mac_address', name='uq_override_maintenance_mac'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    maintenance_id = Column(String(50), index=True, nullable=False)
    mac_address = Column(String(20), index=True, nullable=False)
    override_severity = Column(String(20), nullable=False)  # 'critical', 'warning', 'info'
    original_severity = Column(String(20), nullable=True)   # 保存原本的自動判斷值
    note = Column(Text, nullable=True)  # 用戶備註
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<SeverityOverride {self.mac_address}: {self.override_severity}>"
