"""
Parser for 'get_static_vlan_hpe_fna' API.

Auto-generated skeleton by scripts/generate_parsers.py.
Fill in the parse() method logic.

API Source: get_static_vlan_fna
Endpoint: http://localhost:8001/switch/network/get_static_vlan/10.1.1.1
Target: Mock-HPE-Switch
"""
from __future__ import annotations


from app.core.enums import DeviceType

from app.parsers.protocols import BaseParser, InterfaceVlanData

from app.parsers.registry import parser_registry


class GetStaticVlanHpeFnaParser(BaseParser[InterfaceVlanData]):
    """
    Parser for get_static_vlan_hpe_fna API response.


    Target data model (InterfaceVlanData):
    ```python
    class InterfaceVlanData(ParsedData):
    
        interface_name: str
        vlan_id: int = Field(ge=1, le=4094)
    ```


    Raw output example from Mock-HPE-Switch:
    ```
    Interface    VLAN
    GE1/0/1      10
    GE1/0/2      20
    GE1/0/3      10
    XGE1/0/25    100
    ```
    """

    device_type = DeviceType.HPE
    command = "get_static_vlan_hpe_fna"

    def parse(self, raw_output: str) -> list[InterfaceVlanData]:
        results: list[InterfaceVlanData] = []

        # TODO: Implement parsing logic

        return results


# Register parser
parser_registry.register(GetStaticVlanHpeFnaParser())