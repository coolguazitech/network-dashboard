"""
Parser for 'get_mac_table_hpe_dna' API.

Auto-generated skeleton by scripts/generate_parsers.py.
Fill in the parse() method logic.

API Source: get_mac_table_hpe_dna
Endpoint: http://localhost:8001/api/v1/hpe/mac-table?hosts=10.1.1.1
Target: Mock-HPE-Switch
"""
from __future__ import annotations


from app.core.enums import DeviceType

from app.parsers.protocols import BaseParser, MacTableData

from app.parsers.registry import parser_registry


class GetMacTableHpeDnaParser(BaseParser[MacTableData]):
    """
    Parser for get_mac_table_hpe_dna API response.


    Target data model (MacTableData):
    ```python
    class MacTableData(ParsedData):
    
        mac_address: str = Field(description="正規化為 AA:BB:CC:DD:EE:FF")
        interface_name: str
        vlan_id: int = Field(ge=1, le=4094)
    
        @field_validator("mac_address", mode="before")
        @classmethod
        def normalize_mac(cls, v: str) -> str:
            return _normalize_mac(v)
    ```


    Raw output example from Mock-HPE-Switch:
    ```
    MAC Address          VLAN    Interface
    aa:bb:cc:dd:ee:01    10      GE1/0/1
    aa:bb:cc:dd:ee:02    20      GE1/0/2
    aa:bb:cc:dd:ee:03    10      GE1/0/3
    ```
    """

    device_type = DeviceType.HPE
    command = "get_mac_table_hpe_dna"

    def parse(self, raw_output: str) -> list[MacTableData]:
        results: list[MacTableData] = []

        # TODO: Implement parsing logic

        return results


# Register parser
parser_registry.register(GetMacTableHpeDnaParser())