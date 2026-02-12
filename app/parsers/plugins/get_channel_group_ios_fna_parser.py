"""
Parser for 'get_channel_group_ios_fna' API.

Auto-generated skeleton by scripts/generate_parsers.py.
Fill in the parse() method logic.

API Source: get_channel_group_fna
Endpoint: http://localhost:8001/switch/network/get_channel_group/10.1.1.2
Target: Mock-IOS-Switch
"""
from __future__ import annotations


from app.core.enums import DeviceType

from app.parsers.protocols import BaseParser, PortChannelData

from app.parsers.registry import parser_registry


class GetChannelGroupIosFnaParser(BaseParser[PortChannelData]):
    """
    Parser for get_channel_group_ios_fna API response.


    Target data model (PortChannelData):
    ```python
    class PortChannelData(ParsedData):
    
        interface_name: str
        status: str = Field(description="正規化為 LinkStatus 枚舉值")
        protocol: str | None = Field(None, description="正規化為 AggregationProtocol 枚舉值")
        members: list[str]
        member_status: dict[str, str] | None = None
    
        @field_validator("status", mode="before")
        @classmethod
        def normalize_status(cls, v: Any) -> str:
            return _normalize_link_status(v)
    
        @field_validator("protocol", mode="before")
        @classmethod
        def normalize_protocol(cls, v: Any) -> str | None:
            if v is None:
                return None
            if isinstance(v, str):
                v = v.strip().lower()
            try:
                return AggregationProtocol(v).value
            except ValueError:
                return AggregationProtocol.NONE.value
    
        @field_validator("member_status", mode="before")
        @classmethod
        def normalize_member_status(cls, v: Any) -> dict[str, str] | None:
            if v is None:
                return None
            return {k: _normalize_link_status(s) for k, s in v.items()}
    ```


    Raw output example from Mock-IOS-Switch:
    ```
    Port-Channel    Status    Protocol    Members
    Po1             up        LACP        GE1/0/1, GE1/0/2
    Po2             up        LACP        GE1/0/3, GE1/0/4
    ```
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_channel_group_ios_fna"

    def parse(self, raw_output: str) -> list[PortChannelData]:
        results: list[PortChannelData] = []

        # TODO: Implement parsing logic

        return results


# Register parser
parser_registry.register(GetChannelGroupIosFnaParser())