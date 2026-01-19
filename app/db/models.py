"""
Database ORM models.

Defines all database tables and relationships.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
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

    # Relationships
    interfaces: Mapped[list[Interface]] = relationship(
        "Interface",
        back_populates="switch",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Switch {self.hostname}>"


class Interface(Base):
    """Network interface model."""

    __tablename__ = "interfaces"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    switch_id: Mapped[int] = mapped_column(
        ForeignKey("switches.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )

    # Relationships
    switch: Mapped[Switch] = relationship("Switch", back_populates="interfaces")

    def __repr__(self) -> str:
        return f"<Interface {self.name}>"


class DeviceMapping(Base):
    """
    Device mapping for maintenance operations.

    Maps old devices to new devices during maintenance.
    """

    __tablename__ = "device_mappings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maintenance_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
        comment="Maintenance job identifier",
    )
    old_hostname: Mapped[str] = mapped_column(
        String(255),
        index=True,
        comment="Old device hostname",
    )
    new_hostname: Mapped[str] = mapped_column(
        String(255),
        index=True,
        comment="New device hostname",
    )
    mapping_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional mapping configuration",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<DeviceMapping {self.old_hostname} -> {self.new_hostname}>"


class UplinkExpectation(Base):
    """
    Expected uplink connections for verification.

    Stores user-defined expected uplink topology.
    """

    __tablename__ = "uplink_expectations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    local_interface: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Local interface (optional)",
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
    maintenance_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<UplinkExpectation {self.switch_hostname}>"


class CollectionRecord(Base):
    """
    Record of data collection runs.

    Tracks when data was collected and its status.
    """

    __tablename__ = "collection_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    indicator_type: Mapped[str] = mapped_column(String(100), index=True)
    switch_hostname: Mapped[str] = mapped_column(String(255), index=True)
    phase: Mapped[MaintenancePhase] = mapped_column(
        Enum(MaintenancePhase),
        default=MaintenancePhase.POST,
    )
    maintenance_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        index=True,
    )

    def __repr__(self) -> str:
        return f"<CollectionRecord {self.indicator_type}@{self.switch_hostname}>"


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
        default=MaintenancePhase.POST,
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
    hostname = Column(String(100), nullable=True)
    
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
    ping_latency_ms = Column(Float, nullable=True)
    
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
    
    記錄同一個 MAC 地址在歲修前後的變化情況。
    """
    __tablename__ = "client_comparisons"

    id = Column(Integer, primary_key=True, index=True)
    
    # 基本信息
    maintenance_id = Column(String(50), index=True)
    collected_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # 客戶端識別
    mac_address = Column(String(17), index=True)  # AA:BB:CC:DD:EE:FF
    
    # PRE 階段數據快照
    pre_ip_address = Column(String(15), nullable=True)
    pre_hostname = Column(String(100), nullable=True)
    pre_switch_hostname = Column(String(100), nullable=True)
    pre_interface_name = Column(String(50), nullable=True)
    pre_vlan_id = Column(Integer, nullable=True)
    pre_topology_role = Column(String(50), nullable=True)  # access, trunk, uplink, etc.
    pre_speed = Column(String(20), nullable=True)
    pre_duplex = Column(String(20), nullable=True)
    pre_link_status = Column(String(20), nullable=True)
    pre_ping_reachable = Column(Boolean, nullable=True)
    pre_ping_latency_ms = Column(Float, nullable=True)
    pre_acl_passes = Column(Boolean, nullable=True)
    
    # POST 階段數據快照
    post_ip_address = Column(String(15), nullable=True)
    post_hostname = Column(String(100), nullable=True)
    post_switch_hostname = Column(String(100), nullable=True)
    post_interface_name = Column(String(50), nullable=True)
    post_vlan_id = Column(Integer, nullable=True)
    post_topology_role = Column(String(50), nullable=True)
    post_speed = Column(String(20), nullable=True)
    post_duplex = Column(String(20), nullable=True)
    post_link_status = Column(String(20), nullable=True)
    post_ping_reachable = Column(Boolean, nullable=True)
    post_ping_latency_ms = Column(Float, nullable=True)
    post_acl_passes = Column(Boolean, nullable=True)
    
    # 比較結果
    differences = Column(JSON, nullable=True)  # 記錄哪些欄位有變化
    is_changed = Column(Boolean, default=False)  # 是否有變化
    severity = Column(String(50), nullable=True)  # critical, warning, info
    
    # 額外信息
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

