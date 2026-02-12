"""
Parser for 'get_dynamic_vlan_nxos_fna' API.

Auto-generated skeleton by scripts/generate_parsers.py.
Fill in the parse() method logic.

API Source: get_dynamic_vlan_fna
Endpoint: http://localhost:8001/switch/network/get_dynamic_vlan/10.1.1.3
Target: Mock-NXOS-Switch
"""
from __future__ import annotations


from app.core.enums import DeviceType

from app.parsers.protocols import BaseParser, InterfaceVlanData

from app.parsers.registry import parser_registry


class GetDynamicVlanNxosFnaParser(BaseParser[InterfaceVlanData]):
    """
    Parser for get_dynamic_vlan_nxos_fna API response.


    Target data model (InterfaceVlanData):
    ```python
    class InterfaceVlanData(ParsedData):
    
        interface_name: str
        vlan_id: int = Field(ge=1, le=4094)
    ```


    Raw output example from Mock-NXOS-Switch:
    ```
    Interface    VLAN
    GE1/0/1      10
    GE1/0/2      30
    GE1/0/3      10
    XGE1/0/25    100
    ```
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_dynamic_vlan_nxos_fna"

    def parse(self, raw_output: str) -> list[InterfaceVlanData]:
        results: list[InterfaceVlanData] = []

        # TODO: Implement parsing logic

        return results


# Register parser
parser_registry.register(GetDynamicVlanNxosFnaParser())