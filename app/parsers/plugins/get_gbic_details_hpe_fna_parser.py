"""
Parser for 'get_gbic_details_hpe_fna' API.
Auto-generated skeleton by scripts/generate_parsers.py.
Fill in the parse() method logic.
API Source: get_gbic_details_fna
Endpoint: http://localhost:8001/switch/network/get_gbic_details/10.1.1.1
Target: Mock-HPE-Switch
"""
from __future__ import annotations
import re
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

    # Regex patterns
    INTERFACE_PATTERN = re.compile(
        r'^(?P<interface>(?:GigabitEthernet|Ten-GigabitEthernet|FortyGigE|HundredGigE|FourHundredGigE|Twenty-FiveGigE)\S+)\s+transceiver',
        re.MULTILINE | re.IGNORECASE
    )

    # Pattern for module-level data (temperature and voltage)
    MODULE_PATTERN = re.compile(
        r'Temp\.?\((?:°?C|°)\)\s+Voltage\(V\)\s*\n\s*(?P<temp>-?\d+(?:\.\d+)?)\s+(?P<voltage>\d+\.\d+)',
        re.IGNORECASE
    )

    # Pattern for channel data lines
    CHANNEL_PATTERN = re.compile(
        r'^\s*(?P<channel>\d+)\s+(?P<bias>\d+\.\d+)\s+(?P<rx>-?\d+\.\d+)\s+(?P<tx>-?\d+\.\d+)',
        re.MULTILINE
    )

    def parse(self, raw_output: str) -> list[TransceiverData]:
        """
        Parse HPE Comware transceiver diagnostic output.

        Supports both single-channel (SFP/SFP+) and multi-channel (QSFP/QSFP28) formats.

        Args:
            raw_output: Raw command output from HPE switch

        Returns:
            List of TransceiverData objects
        """
        results: list[TransceiverData] = []

        # Split output into individual interface blocks
        interface_blocks = self._split_by_interface(raw_output)

        for interface_name, block in interface_blocks:
            transceiver_data = self._parse_interface_block(interface_name, block)
            if transceiver_data:
                results.append(transceiver_data)

        return results

    def _split_by_interface(self, output: str) -> list[tuple[str, str]]:
        """
        Split output into individual interface blocks.

        Args:
            output: Full command output

        Returns:
            List of (interface_name, block_text) tuples
        """
        blocks = []
        matches = list(self.INTERFACE_PATTERN.finditer(output))

        for i, match in enumerate(matches):
            interface = match.group('interface')
            start = match.start()

            # Find end of this block (start of next interface or end of output)
            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                end = len(output)

            block = output[start:end]
            blocks.append((interface, block))

        return blocks

    def _parse_interface_block(self, interface_name: str, block: str) -> TransceiverData | None:
        """
        Parse a single interface's diagnostic block.

        Args:
            interface_name: Interface identifier (e.g., "GigabitEthernet1/0/1")
            block: Text block for this interface

        Returns:
            TransceiverData object or None if parsing fails
        """
        # Check for error conditions
        if "absent" in block.lower():
            # Transceiver not present - skip
            return None

        if "does not support" in block.lower():
            # Non-DDM transceiver - skip
            return None

        # Parse module-level data (temperature and voltage)
        module_match = self.MODULE_PATTERN.search(block)
        if not module_match:
            # No valid module data found
            return None

        temperature = float(module_match.group('temp'))
        voltage = float(module_match.group('voltage'))

        # Parse channel data
        channels = self._parse_channels(block)

        if not channels:
            # No valid channel data found
            return None

        return TransceiverData(
            interface_name=interface_name,
            temperature=temperature,
            voltage=voltage,
            channels=channels
        )

    def _parse_channels(self, block: str) -> list[TransceiverChannelData]:
        """
        Parse channel-specific diagnostic data.

        Handles both single-channel (SFP) and multi-channel (QSFP) formats.

        Args:
            block: Text block containing channel data

        Returns:
            List of TransceiverChannelData objects
        """
        channels = []

        # Find all channel data lines
        for match in self.CHANNEL_PATTERN.finditer(block):
            channel_num = int(match.group('channel'))
            bias_current = float(match.group('bias'))
            rx_power = float(match.group('rx'))
            tx_power = float(match.group('tx'))

            # Validate channel number (1-4 for QSFP, 1 for SFP)
            if not (1 <= channel_num <= 4):
                continue

            # Validate power values are within acceptable range
            if not (-40.0 <= rx_power <= 10.0) or not (-40.0 <= tx_power <= 10.0):
                continue

            channel_data = TransceiverChannelData(
                channel=channel_num,
                tx_power=tx_power,
                rx_power=rx_power,
                bias_current_ma=bias_current
            )
            channels.append(channel_data)

        return channels


# Register parser
parser_registry.register(GetGbicDetailsHpeFnaParser())