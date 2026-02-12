"""
Parser for 'get_version_ios_dna' API.

Auto-generated skeleton by scripts/generate_parsers.py.
Fill in the parse() method logic.

API Source: get_version_ios_dna
Endpoint: http://localhost:8001/api/v1/ios/version?hosts=10.1.1.2
Target: Mock-IOS-Switch
"""
from __future__ import annotations


from app.core.enums import DeviceType

from app.parsers.protocols import BaseParser, VersionData

from app.parsers.registry import parser_registry


class GetVersionIosDnaParser(BaseParser[VersionData]):
    """
    Parser for get_version_ios_dna API response.


    Target data model (VersionData):
    ```python
    class VersionData(ParsedData):
    
        version: str
        model: str | None = None
        serial_number: str | None = None
        uptime: str | None = None
    ```


    Raw output example from Mock-IOS-Switch:
    ```
    Cisco IOS Software, Version 15.2(7)E4
    Model number: WS-C2960X-48FPS-L
    System serial number: FCW2345G0AB
    uptime is 30 days, 12 hours, 5 minutes
    ```
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_version_ios_dna"

    def parse(self, raw_output: str) -> list[VersionData]:
        results: list[VersionData] = []

        # TODO: Implement parsing logic

        return results


# Register parser
parser_registry.register(GetVersionIosDnaParser())