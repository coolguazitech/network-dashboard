"""
Pydantic schemas for Switch and Interface API models.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.core.enums import VendorType


class InterfaceBase(BaseModel):
    """Interface 基本欄位。"""
    name: str = Field(..., description="介面名稱", examples=["Ethernet1/1"])
    interface_type: Optional[str] = Field(None, description="介面類型")
    description: Optional[str] = Field(None, description="介面描述")


class InterfaceResponse(InterfaceBase):
    """Interface API 回應模型。"""
    id: int
    switch_id: int
    admin_status: Optional[str] = None
    oper_status: Optional[str] = None
    speed: Optional[int] = Field(None, description="速度 (Mbps)")
    has_transceiver: bool = False
    transceiver_type: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class SwitchBase(BaseModel):
    """Switch 基本欄位。"""
    hostname: str = Field(
        ...,
        description="Switch 主機名稱",
        examples=["switch-01"]
    )
    ip_address: str = Field(
        ...,
        description="IP 地址",
        examples=["192.168.1.1"]
    )
    vendor: VendorType = Field(
        ...,
        description="廠牌類型"
    )
    model: Optional[str] = Field(
        None,
        description="設備型號",
        examples=["Nexus 9300"]
    )
    location: Optional[str] = Field(
        None,
        description="設備位置",
        examples=["機房A-R01"]
    )
    description: Optional[str] = Field(
        None,
        description="設備描述"
    )


class SwitchCreate(SwitchBase):
    """Switch 建立請求模型。"""
    api_endpoint: Optional[str] = Field(
        None,
        description="API 端點 URL"
    )
    api_credentials_key: Optional[str] = Field(
        None,
        description="認證資訊金鑰名稱"
    )
    extra_config: Optional[dict] = Field(
        None,
        description="額外設定"
    )


class SwitchUpdate(BaseModel):
    """Switch 更新請求模型。所有欄位皆為可選。"""
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    vendor: Optional[VendorType] = None
    model: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    api_endpoint: Optional[str] = None
    api_credentials_key: Optional[str] = None
    extra_config: Optional[dict] = None


class SwitchResponse(SwitchBase):
    """Switch API 回應模型。"""
    id: int
    is_active: bool = True
    last_seen: Optional[datetime] = None
    api_endpoint: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    # 關聯資料
    interface_count: int = Field(
        default=0,
        description="介面數量"
    )
    
    class Config:
        from_attributes = True


class SwitchDetailResponse(SwitchResponse):
    """Switch 詳細資訊回應（包含介面列表）。"""
    interfaces: list[InterfaceResponse] = Field(
        default_factory=list,
        description="介面列表"
    )


class SwitchListResponse(BaseModel):
    """Switch 列表回應。"""
    total: int = Field(..., description="總數量")
    items: list[SwitchResponse] = Field(..., description="Switch 列表")
    page: int = Field(default=1, description="當前頁碼")
    page_size: int = Field(default=20, description="每頁數量")


class SwitchNeighbor(BaseModel):
    """Switch 鄰居關係。"""
    local_hostname: str
    local_interface: str
    remote_hostname: str
    remote_interface: str
    link_type: Optional[str] = None


class TopologyResponse(BaseModel):
    """網路拓撲回應。"""
    switches: list[SwitchResponse]
    neighbors: list[SwitchNeighbor]
