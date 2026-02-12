"""
Parser for 'get_uplink_ios_fna' API.

Auto-generated skeleton by scripts/generate_parsers.py.
Fill in the parse() method logic.

API Source: get_uplink_fna
Endpoint: http://localhost:8001/switch/network/get_neighbors/10.1.1.2
Target: Mock-IOS-Switch
"""
from __future__ import annotations


from app.core.enums import DeviceType

from app.parsers.protocols import BaseParser, NeighborData

from app.parsers.registry import parser_registry


class GetUplinkIosFnaParser(BaseParser[NeighborData]):
    """
    Parser for get_uplink_ios_fna API response.


    Target data model (NeighborData):
    ```python
    class NeighborData(ParsedData):
    
        local_interface: str
        remote_hostname: str
        remote_interface: str
        remote_platform: str | None = None
    ```


    Raw output example from Mock-IOS-Switch:
    ```
    Local Interface    Remote Host        Remote Interface    Platform
    GE1/0/25           CORE-SW-01         GE0/0/1             Cisco IOS
    GE1/0/26           CORE-SW-02         GE0/0/1             Cisco IOS
    ```
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_uplink_ios_fna"

    def parse(self, raw_output: str) -> list[NeighborData]:
        results: list[NeighborData] = []

        # TODO: Implement parsing logic

        return results


# Register parser
parser_registry.register(GetUplinkIosFnaParser())