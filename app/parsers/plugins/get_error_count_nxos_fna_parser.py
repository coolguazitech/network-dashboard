"""
Parser for 'get_error_count_nxos_fna' API.

Auto-generated skeleton by scripts/generate_parsers.py.
Fill in the parse() method logic.

API Source: get_error_count_fna
Endpoint: http://localhost:8001/switch/network/get_error_count/10.1.1.3
Target: Mock-NXOS-Switch
"""
from __future__ import annotations


from app.core.enums import DeviceType

from app.parsers.protocols import BaseParser, InterfaceErrorData

from app.parsers.registry import parser_registry


class GetErrorCountNxosFnaParser(BaseParser[InterfaceErrorData]):
    """
    Parser for get_error_count_nxos_fna API response.


    Target data model (InterfaceErrorData):
    ```python
    class InterfaceErrorData(ParsedData):
    
        interface_name: str
        crc_errors: int = Field(0, ge=0, description="純 CRC 錯誤數（不含 giants/runts 等）")
    ```


    Raw output example from Mock-NXOS-Switch:
    ```
    Interface            CRC Errors
    GE1/0/1                        0
    GE1/0/2                       15
    GE1/0/3                        0
    XGE1/0/25                      0
    ```
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_error_count_nxos_fna"

    def parse(self, raw_output: str) -> list[InterfaceErrorData]:
        results: list[InterfaceErrorData] = []

        # TODO: Implement parsing logic

        return results


# Register parser
parser_registry.register(GetErrorCountNxosFnaParser())