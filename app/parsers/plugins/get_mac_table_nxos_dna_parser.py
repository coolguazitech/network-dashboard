"""
Parser for 'get_mac_table_nxos_dna' API.

Auto-generated skeleton by scripts/generate_parsers.py.
Fill in the parse() method logic.

API Source: get_mac_table_nxos_dna
Endpoint: http://localhost:8001/api/v1/nxos/mac-table?hosts=10.1.1.3
Target: Mock-NXOS-Switch
"""
from __future__ import annotations


from app.core.enums import DeviceType

from app.parsers.protocols import BaseParser, MacTableData

from app.parsers.registry import parser_registry


class GetMacTableNxosDnaParser(BaseParser[MacTableData]):
    """
    Parser for get_mac_table_nxos_dna API response.


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


    Raw output example from Mock-NXOS-Switch:
    ```
    Legend:
            * - primary entry, G - Gateway MAC, (R) - Routed MAC
    
       VLAN     MAC Address      Type      age     Secure   NTFY   Ports
    ---------+-----------------+--------+---------+------+----+------------------
    *   10     aabb.ccdd.ee01   dynamic  0         F      F    Eth1/1
    *   20     aabb.ccdd.ee02   dynamic  0         F      F    Eth1/2
    ```
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_mac_table_nxos_dna"

    def parse(self, raw_output: str) -> list[MacTableData]:
        results: list[MacTableData] = []

        # TODO: Implement parsing logic

        return results


# Register parser
parser_registry.register(GetMacTableNxosDnaParser())