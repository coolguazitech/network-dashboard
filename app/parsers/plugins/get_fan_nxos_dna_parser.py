"""
Parser for 'get_fan_nxos_dna' API.

Auto-generated skeleton by scripts/generate_parsers.py.
Fill in the parse() method logic.

API Source: get_fan_nxos_dna
Endpoint: http://localhost:8001/api/v1/nxos/fan?hosts=10.1.1.3
Target: Mock-NXOS-Switch
"""
from __future__ import annotations


from app.core.enums import DeviceType

from app.parsers.protocols import BaseParser, FanStatusData

from app.parsers.registry import parser_registry


class GetFanNxosDnaParser(BaseParser[FanStatusData]):
    """
    Parser for get_fan_nxos_dna API response.


    Target data model (FanStatusData):
    ```python
    class FanStatusData(ParsedData):
    
        fan_id: str
        status: str = Field(description="正規化為 OperationalStatus 枚舉值")
        speed_rpm: int | None = Field(None, ge=0)
        speed_percent: int | None = Field(None, ge=0, le=100)
    
        @field_validator("status", mode="before")
        @classmethod
        def normalize_status(cls, v: Any) -> str:
            return _normalize_operational_status(v)
    ```


    Raw output example from Mock-NXOS-Switch:
    ```
    Fan             Model                Hw         Status
    --------------------------------------------------------------
    Chassis-1       N9K-C93180YC-FX      --         Ok
    Fan_in_PS-1     --                   --         Ok
    Fan_in_PS-2     --                   --         Ok
    ```
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_fan_nxos_dna"

    def parse(self, raw_output: str) -> list[FanStatusData]:
        results: list[FanStatusData] = []

        # TODO: Implement parsing logic

        return results


# Register parser
parser_registry.register(GetFanNxosDnaParser())