"""
Parser for 'get_gbic_details_ios_fna' API.

Parses Cisco IOS/IOS-XE `show interfaces transceiver` tabular output.

Real CLI command: show interfaces transceiver
Platforms: Catalyst 2960, 3560, 3750, 3850, 9200, 9300, 9500

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
Command: show interfaces transceiver detail
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, TransceiverData
from app.parsers.protocols import TransceiverChannelData
from app.parsers.registry import parser_registry

# IOS interface abbreviation → full name mapping (for reference only)
# Gi = GigabitEthernet, Te = TenGigabitEthernet, Twe = TwentyFiveGigE,
# Fo = FortyGigabitEthernet, Hu = HundredGigE, Ap = AppGigabitEthernet


class GetGbicDetailsIosFnaParser(BaseParser[TransceiverData]):
    """
    Parser for Cisco IOS/IOS-XE `show interfaces transceiver` tabular output.

    Real output format:
    ```
                                            Optical   Optical
               Temperature  Voltage  Current  Tx Power  Rx Power
    Port       (Celsius)    (Volts)  (mA)     (dBm)     (dBm)
    ---------  -----------  -------  -------  --------  --------
    Gi1/0/1    32.7         3.28     6.1      -2.5      -3.1
    Gi1/0/2    28.1         3.30     6.0      -2.3      -3.0
    Te1/0/25   28.3         3.31     35.2     -1.2      -2.8
    Te1/0/26   N/A          N/A      N/A      N/A       N/A
    ```

    Notes:
    - One row per interface, each row = 1 channel (channel 1)
    - Values can be "N/A" when transceiver doesn't support DOM/DDM
    - Interface names are abbreviated: Gi, Te, Twe, Fo, Hu, Ap, etc.
    - Alarm indicators may appear: ++ (high alarm), + (high warn),
      - (low warn), -- (low alarm), appended to values
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_gbic_details_ios_fna"

    # Match data rows: port name followed by numeric/N/A values
    # Handles alarm indicators like "32.7++" or "-3.1--"
    ROW_PATTERN = re.compile(
        r'^\s*(?P<port>\S+)\s+'
        r'(?P<temp>-?\d+(?:\.\d+)?[+\-]*|N/?A)\s+'
        r'(?P<voltage>\d+(?:\.\d+)?[+\-]*|N/?A)\s+'
        r'(?P<current>\d+(?:\.\d+)?[+\-]*|N/?A)\s+'
        r'(?P<tx>-?\d+(?:\.\d+)?[+\-]*|N/?A)\s+'
        r'(?P<rx>-?\d+(?:\.\d+)?[+\-]*|N/?A)\s*$',
        re.MULTILINE
    )

    @staticmethod
    def _parse_value(val: str) -> float | None:
        """Parse a value string, stripping alarm indicators and handling N/A."""
        val = val.strip()
        if val.upper() in ("N/A", "N\\A", "NA", "--"):
            return None
        # Strip alarm indicators (++, +, -, --)
        cleaned = re.sub(r'[+\-]+$', '', val)
        try:
            return float(cleaned)
        except ValueError:
            return None

    def parse(self, raw_output: str) -> list[TransceiverData]:
        results: list[TransceiverData] = []

        for match in self.ROW_PATTERN.finditer(raw_output):
            port = match.group('port')

            # Skip header-like rows (e.g., "Port", "---------")
            if port.startswith('-') or port.lower() == 'port':
                continue

            temp = self._parse_value(match.group('temp'))
            voltage = self._parse_value(match.group('voltage'))
            current = self._parse_value(match.group('current'))
            tx_power = self._parse_value(match.group('tx'))
            rx_power = self._parse_value(match.group('rx'))

            # Skip interfaces with no DOM data at all
            if all(v is None for v in (temp, voltage, current, tx_power, rx_power)):
                continue

            channel = TransceiverChannelData(
                channel=1,
                tx_power=tx_power,
                rx_power=rx_power,
            )

            results.append(TransceiverData(
                interface_name=port,
                temperature=temp,
                voltage=voltage,
                channels=[channel],
            ))

        return results


# Register parser
parser_registry.register(GetGbicDetailsIosFnaParser())
