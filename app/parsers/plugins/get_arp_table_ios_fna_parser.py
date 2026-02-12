"""
Parser for 'get_arp_table_ios_fna' API.

Auto-generated skeleton by scripts/generate_parsers.py.
Fill in the parse() method logic.

API Source: get_arp_table_fna
Endpoint: http://localhost:8001/switch/network/get_arp_table/10.1.1.2
Target: Mock-IOS-Switch
"""
from __future__ import annotations


from app.core.enums import DeviceType

from app.parsers.protocols import BaseParser, ArpData

from app.parsers.registry import parser_registry


class GetArpTableIosFnaParser(BaseParser[ArpData]):
    """
    Parser for get_arp_table_ios_fna API response.


    Target data model (ArpData):
    ```python
    class ArpData(ParsedData):
    
        ip_address: str
        mac_address: str
    
        @field_validator("ip_address", mode="before")
        @classmethod
        def validate_ip(cls, v: str) -> str:
            return _validate_ipv4(v)
    
        @field_validator("mac_address", mode="before")
        @classmethod
        def normalize_mac(cls, v: str) -> str:
            return _normalize_mac(v)
    ```


    Raw output example from Mock-IOS-Switch:
    ```
    IP Address        MAC Address            Interface
    192.168.1.1       aa:bb:cc:dd:ee:01      GE1/0/1
    192.168.1.2       aa:bb:cc:dd:ee:02      GE1/0/2
    192.168.1.3       aa:bb:cc:dd:ee:03      GE1/0/3
    ```
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_arp_table_ios_fna"

    def parse(self, raw_output: str) -> list[ArpData]:
        results: list[ArpData] = []

        # TODO: Implement parsing logic

        return results


# Register parser
parser_registry.register(GetArpTableIosFnaParser())