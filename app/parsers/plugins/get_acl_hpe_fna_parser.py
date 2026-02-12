"""
Parser for 'get_acl_hpe_fna' API.

Auto-generated skeleton by scripts/generate_parsers.py.
Fill in the parse() method logic.

API Source: get_acl_fna
Endpoint: http://localhost:8001/switch/network/get_acl/10.1.1.1
Target: Mock-HPE-Switch
"""
from __future__ import annotations


from app.core.enums import DeviceType

from app.parsers.protocols import BaseParser, AclData

from app.parsers.registry import parser_registry


class GetAclHpeFnaParser(BaseParser[AclData]):
    """
    Parser for get_acl_hpe_fna API response.


    Target data model (AclData):
    ```python
    class AclData(ParsedData):
    
        interface_name: str
        acl_number: str | None = None
    ```


    Raw output example from Mock-HPE-Switch:
    ```
    Interface    ACL Number
    GE1/0/1      100
    GE1/0/2      101
    GE1/0/3      --
    XGE1/0/25    200
    ```
    """

    device_type = DeviceType.HPE
    command = "get_acl_hpe_fna"

    def parse(self, raw_output: str) -> list[AclData]:
        results: list[AclData] = []

        # TODO: Implement parsing logic

        return results


# Register parser
parser_registry.register(GetAclHpeFnaParser())