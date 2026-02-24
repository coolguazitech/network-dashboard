"""
Parser for 'get_gbic_details_hpe_fna' API.

Parses HPE Comware ``display transceiver diagnosis interface`` output to extract
transceiver diagnostic information (temperature, voltage, per-channel power/bias).

=== ParsedData Model (DO NOT REMOVE) ===
class TransceiverChannelData(BaseModel):
    channel: int                             # 1-4 (SFP=1, QSFP=1~4)
    tx_power: float | None = None            # dBm, range -40.0 ~ 10.0
    rx_power: float | None = None            # dBm, range -40.0 ~ 10.0

class TransceiverData(ParsedData):
    interface_name: str                      # e.g. "GigabitEthernet1/0/1"
    temperature: float | None = None         # °C, range -10.0 ~ 100.0
    voltage: float | None = None             # V, range 0 ~ 10.0
    channels: list[TransceiverChannelData]   # one per lane
=== End ParsedData Model ===

=== Real CLI Command ===
Command: display transceiver diagnosis interface
=== End Real CLI Command ===
"""
from __future__ import annotations
import re
from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, TransceiverData
from app.parsers.protocols import TransceiverChannelData
from app.parsers.registry import parser_registry


class GetGbicDetailsHpeFnaParser(BaseParser[TransceiverData]):
    """
    Parser for HPE Comware ``display transceiver diagnosis interface`` output.

    Real CLI output (ref: HPE Comware CLI Reference)::

        GigabitEthernet1/0/1 transceiver diagnostic information:
        The transceiver diagnostic information is as follows:
        Current diagnostic parameters:
          Temp.(°C) Voltage(V)  Bias(mA)  RX power(dBm)  TX power(dBm)
          36.43     3.31        6.13      -3.10           -2.50

        GigabitEthernet1/0/2 transceiver diagnostic information:
        The transceiver diagnostic information is as follows:
        Current diagnostic parameters:
          Temp.(°C) Voltage(V)  Bias(mA)  RX power(dBm)  TX power(dBm)
          35.00     3.30        6.10      -3.00           -2.30

        FortyGigE1/0/25 transceiver diagnostic information:
        The transceiver diagnostic information is as follows:
        Current diagnostic parameters:
          Temp.(°C) Voltage(V)
          34.00     3.29
          Channel   Bias(mA)  RX power(dBm)  TX power(dBm)
          1         6.50      -2.10          -1.50
          2         6.48      -2.30          -1.55
          3         6.52      -2.05          -1.48
          4         6.45      -2.20          -1.52

    Notes:
        - SFP: All values on one row (Temp, Voltage, Bias, Rx, Tx).
        - QSFP: Module-level Temp/Voltage on one row, then per-channel rows.
        - ``Temp.`` may appear with or without period.
        - Absent transceivers may show "The transceiver is absent."
    """

    device_type = DeviceType.HPE
    command = "get_gbic_details_hpe_fna"

    # Regex patterns
    INTERFACE_PATTERN = re.compile(
        r'^(?P<interface>(?:GigabitEthernet|Ten-GigabitEthernet|FortyGigE|HundredGigE|FourHundredGigE|Twenty-FiveGigE)\S+)\s+transceiver',
        re.MULTILINE | re.IGNORECASE
    )

    # Pattern for module-level data (temperature and voltage)
    # Header may end after Voltage(V) (QSFP) or continue with Bias/RX/TX (SFP)
    MODULE_PATTERN = re.compile(
        r'Temp\.?\((?:°?C|°)\)\s+Voltage\(V\).*\n\s*(?P<temp>-?\d+(?:\.\d+)?)\s+(?P<voltage>\d+\.\d+)',
        re.IGNORECASE
    )

    # Pattern for channel data lines (QSFP multi-channel)
    CHANNEL_PATTERN = re.compile(
        r'^\s*(?P<channel>\d+)\s+(?P<bias>\d+\.\d+)\s+(?P<rx>-?\d+\.\d+)\s+(?P<tx>-?\d+\.\d+)',
        re.MULTILINE
    )

    # Pattern for SFP single-row data: Temp Voltage Bias RX TX on one line
    SFP_ROW_PATTERN = re.compile(
        r'^\s*(?P<temp>-?\d+(?:\.\d+)?)\s+(?P<voltage>\d+\.\d+)\s+'
        r'(?P<bias>\d+\.\d+)\s+(?P<rx>-?\d+\.\d+)\s+(?P<tx>-?\d+\.\d+)',
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

        # Try QSFP multi-channel lines first
        for match in self.CHANNEL_PATTERN.finditer(block):
            channel_num = int(match.group('channel'))
            bias_current = float(match.group('bias'))
            rx_power = float(match.group('rx'))
            tx_power = float(match.group('tx'))

            if not (1 <= channel_num <= 4):
                continue
            if not (-40.0 <= rx_power <= 10.0) or not (-40.0 <= tx_power <= 10.0):
                continue

            channels.append(TransceiverChannelData(
                channel=channel_num,
                tx_power=tx_power,
                rx_power=rx_power,
            ))

        # Fallback: SFP single-row format (Temp Voltage Bias RX TX on one line)
        if not channels:
            sfp_match = self.SFP_ROW_PATTERN.search(block)
            if sfp_match:
                bias_current = float(sfp_match.group('bias'))
                rx_power = float(sfp_match.group('rx'))
                tx_power = float(sfp_match.group('tx'))
                if (-40.0 <= rx_power <= 10.0) and (-40.0 <= tx_power <= 10.0):
                    channels.append(TransceiverChannelData(
                        channel=1,
                        tx_power=tx_power,
                        rx_power=rx_power,
                    ))

        return channels


# Register parser
parser_registry.register(GetGbicDetailsHpeFnaParser())