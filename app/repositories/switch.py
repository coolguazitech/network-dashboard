"""
Switch Repository.

Data access layer for Switch model.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.enums import PlatformType, SiteType, VendorType
from app.db.models import Interface, Switch
from app.repositories.base import BaseRepository


class SwitchRepository(BaseRepository[Switch]):
    """Repository for Switch operations."""

    model = Switch

    async def get_by_hostname(self, hostname: str) -> Switch | None:
        """
        Get switch by hostname.

        Args:
            hostname: Switch hostname

        Returns:
            Switch instance or None
        """
        stmt = select(Switch).where(Switch.hostname == hostname)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_ip(self, ip_address: str) -> Switch | None:
        """
        Get switch by IP address.

        Args:
            ip_address: Switch IP address

        Returns:
            Switch instance or None
        """
        stmt = select(Switch).where(Switch.ip_address == ip_address)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_switches(
        self,
        site: SiteType | None = None,
        vendor: VendorType | None = None,
    ) -> list[Switch]:
        """
        Get all active switches with optional filters.

        Args:
            site: Filter by site (optional)
            vendor: Filter by vendor (optional)

        Returns:
            List of active switches
        """
        stmt = select(Switch).where(Switch.is_active == True)  # noqa: E712

        if site:
            stmt = stmt.where(Switch.site == site)
        if vendor:
            stmt = stmt.where(Switch.vendor == vendor)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_interfaces(self, switch_id: int) -> Switch | None:
        """
        Get switch with its interfaces loaded.

        Args:
            switch_id: Switch ID

        Returns:
            Switch with interfaces or None
        """
        stmt = (
            select(Switch)
            .options(selectinload(Switch.interfaces))
            .where(Switch.id == switch_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_vendor_platform(
        self,
        vendor: VendorType,
        platform: PlatformType,
    ) -> list[Switch]:
        """
        Get switches by vendor and platform.

        Args:
            vendor: Vendor type
            platform: Platform type

        Returns:
            List of matching switches
        """
        stmt = (
            select(Switch)
            .where(Switch.vendor == vendor)
            .where(Switch.platform == platform)
            .where(Switch.is_active == True)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class InterfaceRepository(BaseRepository[Interface]):
    """Repository for Interface operations."""

    model = Interface

    async def get_by_switch_id(self, switch_id: int) -> list[Interface]:
        """
        Get all interfaces for a switch.

        Args:
            switch_id: Switch ID

        Returns:
            List of interfaces
        """
        stmt = select(Interface).where(Interface.switch_id == switch_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(
        self,
        switch_id: int,
        name: str,
    ) -> Interface | None:
        """
        Get interface by switch ID and name.

        Args:
            switch_id: Switch ID
            name: Interface name

        Returns:
            Interface or None
        """
        stmt = (
            select(Interface)
            .where(Interface.switch_id == switch_id)
            .where(Interface.name == name)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
