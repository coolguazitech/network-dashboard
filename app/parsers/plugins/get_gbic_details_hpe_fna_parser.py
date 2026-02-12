"""
Parser for 'get_gbic_details_hpe_fna' API.

Auto-generated skeleton by scripts/generate_parsers.py.
Fill in the parse() method logic.

API Source: get_gbic_details_fna
Endpoint: http://localhost:8001/switch/network/get_gbic_details/10.1.1.1
Target: Mock-HPE-Switch
"""
from __future__ import annotations


from app.core.enums import DeviceType

from app.parsers.protocols import BaseParser, TransceiverData

from app.parsers.protocols import TransceiverChannelData

from app.parsers.registry import parser_registry


class GetGbicDetailsHpeFnaParser(BaseParser[TransceiverData]):
    """
    Parser for get_gbic_details_hpe_fna API response.


    Target data model (TransceiverData):
    ```python
    class TransceiverChannelData(BaseModel):
    
        channel: int = Field(ge=1, le=4, description="通道編號 (SFP=1, QSFP=1~4)")
        tx_power: float | None = Field(None, ge=-40.0, le=10.0, description="發射功率 (dBm)")
        rx_power: float | None = Field(None, ge=-40.0, le=10.0, description="接收功率 (dBm)")
        bias_current_ma: float | None = Field(None, ge=0.0, description="偏置電流 (mA)")

    class TransceiverData(ParsedData):
    
        interface_name: str
        temperature: float | None = Field(None, ge=-10.0, le=100.0, description="模組溫度 (°C)")
        voltage: float | None = Field(None, ge=0.0, le=10.0, description="模組電壓 (V)")
        channels: list[TransceiverChannelData] = Field(description="各通道診斷資料")
    ```


    Raw output example from Mock-HPE-Switch:
    ```
    GigabitEthernet1/0/1 transceiver diagnostic information:
    Current diagnostic parameters:
      Temp(°C)  Voltage(V)
      36        3.31
    
      Channel   Bias(mA)  RX power(dBm)  TX power(dBm)
      1         6.13      -3.10          -2.50
    
    GigabitEthernet1/0/2 transceiver diagnostic information:
    Current diagnostic parameters:
      Temp(°C)  Voltage(V)
      35        3.30
    
      Channel   Bias(mA)  RX power(dBm)  TX power(dBm)
      1         6.10      -3.00          -2.30
    
    FortyGigE1/0/25 transceiver diagnostic information:
    Current diagnostic parameters:
      Temp(°C)  Voltage(V)
      34        3.29
    
      Channel   Bias(mA)  RX power(dBm)  TX power(dBm)
      1         6.50      -2.10          -1.50
      2         6.48      -2.30          -1.55
      3         6.52      -2.05          -1.48
      4         6.45      -2.20          -1.52
    ```
    """

    device_type = DeviceType.HPE
    command = "get_gbic_details_hpe_fna"

    def parse(self, raw_output: str) -> list[TransceiverData]:
        results: list[TransceiverData] = []

        # TODO: Implement parsing logic

        return results


# Register parser
parser_registry.register(GetGbicDetailsHpeFnaParser())