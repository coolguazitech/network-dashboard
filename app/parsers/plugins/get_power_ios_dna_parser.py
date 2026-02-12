"""
Parser for 'get_power_ios_dna' API.

Auto-generated skeleton by scripts/generate_parsers.py.
Fill in the parse() method logic.

API Source: get_power_ios_dna
Endpoint: http://localhost:8001/api/v1/ios/power?hosts=10.1.1.2
Target: Mock-IOS-Switch
"""
from __future__ import annotations


from app.core.enums import DeviceType

from app.parsers.protocols import BaseParser, PowerData

from app.parsers.registry import parser_registry


class GetPowerIosDnaParser(BaseParser[PowerData]):
    """
    Parser for get_power_ios_dna API response.


    Target data model (PowerData):
    ```python
    class PowerData(ParsedData):
    
        ps_id: str
        status: str = Field(description="正規化為 OperationalStatus 枚舉值")
        input_status: str | None = None
        output_status: str | None = None
        capacity_watts: float | None = Field(None, ge=0.0)
        actual_output_watts: float | None = Field(None, ge=0.0)
    
        @field_validator("status", mode="before")
        @classmethod
        def normalize_status(cls, v: Any) -> str:
            return _normalize_operational_status(v)
    
        @field_validator("input_status", "output_status", mode="before")
        @classmethod
        def normalize_sub_status(cls, v: Any) -> str | None:
            if v is None:
                return None
            return _normalize_operational_status(v)
    ```


    Raw output example from Mock-IOS-Switch:
    ```
    Power Supply   Status
    PS1            OK
    PS2            OK
    ```
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_power_ios_dna"

    def parse(self, raw_output: str) -> list[PowerData]:
        results: list[PowerData] = []

        # TODO: Implement parsing logic

        return results


# Register parser
parser_registry.register(GetPowerIosDnaParser())