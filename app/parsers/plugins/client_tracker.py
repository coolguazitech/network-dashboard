"""
Client tracker parser.

追蹤網絡中的客戶端設備 (MAC/IP/VLAN/ACL/速度/雙工/Ping)。
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel

from app.parsers.base import BaseParser


class ClientData(BaseModel):
    """客戶端數據模型。"""
    mac_address: str
    ip_address: str | None = None
    hostname: str | None = None
    switch_hostname: str
    interface_name: str
    vlan_id: int | None = None
    speed: str | None = None  # 1G, 10G, etc.
    duplex: str | None = None  # full, half
    link_status: str | None = None  # up, down
    ping_reachable: bool | None = None
    ping_latency_ms: float | None = None
    acl_rules_applied: list[str] | None = None
    acl_passes: bool | None = None


class ClientTrackerParser(BaseParser):
    """客戶端追蹤 Parser。"""
    
    name = "client_tracker"
    indicator_type = "client"
    
    def parse(self, raw_output: str) -> list[ClientData]:
        """
        解析客戶端數據。
        
        預期格式：
        ```
        MAC,IP,Hostname,Switch,Interface,VLAN,Speed,Duplex,LinkStatus,PingReachable,PingLatency,ACLRules,ACLPass
        AA:BB:CC:DD:EE:01,192.168.1.10,client-01,switch-new-01,Ethernet1/1,10,1G,full,up,true,5.2,"rule1,rule2",true
        AA:BB:CC:DD:EE:02,192.168.1.20,client-02,switch-new-01,Ethernet1/2,10,1G,full,up,true,3.8,"rule1",true
        ```
        
        Args:
            raw_output: 原始 CSV 格式數據
            
        Returns:
            list[ClientData]: 解析後的客戶端數據列表
        """
        results: list[ClientData] = []
        
        lines = raw_output.strip().split('\n')
        if len(lines) < 2:
            return results
        
        # 跳過標題行
        for line in lines[1:]:
            if not line.strip():
                continue
            
            parts = line.split(',')
            if len(parts) < 5:
                continue
            
            try:
                mac = parts[0].strip()
                ip = parts[1].strip() if parts[1].strip() else None
                hostname = parts[2].strip() if parts[2].strip() else None
                switch = parts[3].strip()
                interface = parts[4].strip()
                vlan = int(parts[5].strip()) if len(parts) > 5 and parts[5].strip() else None
                speed = parts[6].strip() if len(parts) > 6 and parts[6].strip() else None
                duplex = parts[7].strip() if len(parts) > 7 and parts[7].strip() else None
                link_status = parts[8].strip() if len(parts) > 8 and parts[8].strip() else None
                ping_reachable = parts[9].strip().lower() == 'true' if len(parts) > 9 else None
                ping_latency = float(parts[10].strip()) if len(parts) > 10 and parts[10].strip() else None
                acl_rules = parts[11].strip().strip('"').split(',') if len(parts) > 11 and parts[11].strip() else None
                acl_passes = parts[12].strip().lower() == 'true' if len(parts) > 12 else None
                
                client = ClientData(
                    mac_address=mac,
                    ip_address=ip,
                    hostname=hostname,
                    switch_hostname=switch,
                    interface_name=interface,
                    vlan_id=vlan,
                    speed=speed,
                    duplex=duplex,
                    link_status=link_status,
                    ping_reachable=ping_reachable,
                    ping_latency_ms=ping_latency,
                    acl_rules_applied=acl_rules,
                    acl_passes=acl_passes,
                )
                results.append(client)
            except Exception as e:
                print(f"Error parsing client data: {e}")
                continue
        
        return results
