"""Mock: 設備連通性 (ping_batch)。"""
from __future__ import annotations

from mock_server.convergence import should_device_fail


def generate(
    device_type: str,
    is_old: bool | None,
    active_seconds: float,
    converge_time: float,
    switch_ip: str = "10.0.0.1",
    **_kw: object,
) -> str:
    unreachable = should_device_fail(is_old, active_seconds, converge_time)

    if unreachable:
        return (
            f"PING {switch_ip} ({switch_ip}): 56 data bytes\n"
            f"\n"
            f"--- {switch_ip} ping statistics ---\n"
            f"3 packets transmitted, 0 packets received, 100.0% packet loss\n"
        )

    return (
        f"PING {switch_ip} ({switch_ip}): 56 data bytes\n"
        f"64 bytes from {switch_ip}: icmp_seq=0 ttl=64 time=1.2 ms\n"
        f"64 bytes from {switch_ip}: icmp_seq=1 ttl=64 time=1.1 ms\n"
        f"64 bytes from {switch_ip}: icmp_seq=2 ttl=64 time=1.3 ms\n"
        f"\n"
        f"--- {switch_ip} ping statistics ---\n"
        f"3 packets transmitted, 3 packets received, 0.0% packet loss\n"
        f"round-trip min/avg/max = 1.1/1.2/1.3 ms\n"
    )
