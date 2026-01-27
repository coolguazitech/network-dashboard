"""
Parser plugins package.

Each module in this package is a parser plugin that will be auto-discovered.
Parsers should use the @register_parser decorator or call register_parser().
"""
from . import (
    aruba_transceiver,
    cisco_ios_transceiver,
    cisco_nxos_transceiver,
    client_tracker,
    hpe_transceiver,
    cisco_nxos_port_channel,
    hpe_port_channel,
    cisco_nxos_power,
    hpe_power,
    cisco_nxos_fan,
    hpe_fan,
    cisco_nxos_error,
    hpe_error,
    ping,
    cisco_nxos_neighbor,
    hpe_neighbor,
    hpe_version,
    cisco_ios_neighbor,
)
