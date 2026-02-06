"""
Core type definitions.

Dataclasses and types used across the application.
"""
from dataclasses import dataclass

from app.core.enums import PlatformType, SiteType, VendorType


@dataclass
class SwitchInfo:
    """
    Switch device information (value object).

    Used to pass device info between services.
    This is NOT an ORM model - it's a simple data container.
    """

    hostname: str
    ip_address: str
    vendor: VendorType
    platform: PlatformType = PlatformType.HPE_COMWARE
    site: SiteType = SiteType.DEFAULT
    model: str | None = None
    description: str | None = None

    def __repr__(self) -> str:
        return f"<SwitchInfo {self.hostname}>"
