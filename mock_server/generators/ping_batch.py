"""Mock: 設備連通性 (ping_batch)。"""
from __future__ import annotations


def generate(
    device_type: str,
    fails: bool = False,
    switch_ip: str = "10.0.0.1",
    **_kw: object,
) -> str:
    unreachable = fails

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
