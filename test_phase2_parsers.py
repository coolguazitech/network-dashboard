#!/usr/bin/env python3
"""
测试 Phase 2 实现的 Neighbor Parsers。

测试内容：
1. CiscoNxosNeighborParser 可以解析 LLDP 输出
2. HpeComwareNeighborParser 可以解析 LLDP 输出
3. CiscoIosNeighborParser 可以解析 CDP 输出
4. ParserRegistry 可以找到这些 parsers
"""
import sys
from pathlib import Path

# 添加项目路径到 sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.parsers.plugins.cisco_nxos_neighbor import CiscoNxosNeighborParser
from app.parsers.plugins.hpe_neighbor import HpeComwareNeighborParser
from app.parsers.plugins.cisco_ios_neighbor import CiscoIosNeighborParser
from app.parsers.registry import parser_registry
from app.core.enums import VendorType, PlatformType


# 测试数据
CISCO_NXOS_LLDP_OUTPUT = """
Chassis id: 0012.3456.789a
Port id: Ethernet1/1
Local Port id: Eth1/49
Port Description: not advertised
System Name: spine-01.example.com
System Description: Cisco Nexus Operating System (NX-OS) Software, Version 9.3(10)
Time remaining: 112 seconds
System Capabilities: B, R
Enabled Capabilities: B, R
Management Address: 10.0.1.1
Vlan ID: not advertised

Chassis id: 0012.3456.789b
Port id: Ethernet1/2
Local Port id: Eth1/50
Port Description: not advertised
System Name: spine-02.example.com
System Description: Cisco Nexus Operating System (NX-OS) Software, Version 9.3(10)
Time remaining: 115 seconds
"""

HPE_COMWARE_LLDP_OUTPUT = """
LLDP neighbor-information of port 1 [GigabitEthernet1/0/1]:
LLDP neighbor index       : 1
Chassis type              : MAC address
Chassis ID                : 0012-3456-789a
Port ID type              : Interface name
Port ID                   : GigabitEthernet1/0/24
Port description          : not advertised
System name               : Core-Switch-01
System description        : HPE Comware Platform Software, Version 7.1.070
System capabilities supported : Bridge, Router
System capabilities enabled   : Bridge, Router
Management address type       : IPv4
Management address            : 10.0.1.1
Expired time                  : 112s

LLDP neighbor-information of port 2 [GigabitEthernet1/0/2]:
LLDP neighbor index       : 1
Chassis type              : MAC address
Chassis ID                : 0012-3456-789c
Port ID type              : Interface name
Port ID                   : GigabitEthernet1/0/25
System name               : Core-Switch-02
System description        : HPE Comware Platform Software, Version 7.1.070
Expired time                  : 115s
"""

CISCO_IOS_CDP_OUTPUT = """
-------------------------
Device ID: Router01
Entry address(es):
  IP address: 10.1.1.1
Platform: cisco WS-C3750X-48,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/24
Holdtime : 179 sec

Version :
Cisco IOS Software, C3750 Software (C3750-IPSERVICESK9-M), Version 15.0(2)SE11

advertisement version: 2
VTP Management Domain: 'DOMAIN01'
Native VLAN: 1
Duplex: full

-------------------------
Device ID: Switch02
Entry address(es):
  IP address: 10.1.1.2
Platform: cisco WS-C2960X-24,  Capabilities: Switch IGMP
Interface: GigabitEthernet1/0/2,  Port ID (outgoing port): GigabitEthernet1/0/1
Holdtime : 165 sec
"""


def test_cisco_nxos_parser():
    """测试 Cisco NXOS LLDP Parser。"""
    print("\n" + "=" * 60)
    print("测试 Cisco NXOS LLDP Parser")
    print("=" * 60)

    parser = CiscoNxosNeighborParser()
    results = parser.parse(CISCO_NXOS_LLDP_OUTPUT)

    print(f"\n解析结果: 找到 {len(results)} 个邻居")

    if len(results) != 2:
        print(f"   ❌ FAIL: 期望 2 个邻居，实际找到 {len(results)} 个")
        return False

    # 验证第一个邻居
    neighbor1 = results[0]
    print(f"\n邻居 1:")
    print(f"   本地接口: {neighbor1.local_interface}")
    print(f"   远程主机: {neighbor1.remote_hostname}")
    print(f"   远程接口: {neighbor1.remote_interface}")
    print(f"   远程平台: {neighbor1.remote_platform}")

    if (
        neighbor1.local_interface == "Ethernet1/49"
        and neighbor1.remote_hostname == "spine-01.example.com"
        and neighbor1.remote_interface == "Ethernet1/1"
    ):
        print("   ✅ PASS: 邻居 1 解析正确")
    else:
        print("   ❌ FAIL: 邻居 1 解析错误")
        return False

    # 验证第二个邻居
    neighbor2 = results[1]
    print(f"\n邻居 2:")
    print(f"   本地接口: {neighbor2.local_interface}")
    print(f"   远程主机: {neighbor2.remote_hostname}")
    print(f"   远程接口: {neighbor2.remote_interface}")

    if (
        neighbor2.local_interface == "Ethernet1/50"
        and neighbor2.remote_hostname == "spine-02.example.com"
        and neighbor2.remote_interface == "Ethernet1/2"
    ):
        print("   ✅ PASS: 邻居 2 解析正确")
        return True
    else:
        print("   ❌ FAIL: 邻居 2 解析错误")
        return False


def test_hpe_comware_parser():
    """测试 HPE Comware LLDP Parser。"""
    print("\n" + "=" * 60)
    print("测试 HPE Comware LLDP Parser")
    print("=" * 60)

    parser = HpeComwareNeighborParser()
    results = parser.parse(HPE_COMWARE_LLDP_OUTPUT)

    print(f"\n解析结果: 找到 {len(results)} 个邻居")

    if len(results) != 2:
        print(f"   ❌ FAIL: 期望 2 个邻居，实际找到 {len(results)} 个")
        return False

    # 验证第一个邻居
    neighbor1 = results[0]
    print(f"\n邻居 1:")
    print(f"   本地接口: {neighbor1.local_interface}")
    print(f"   远程主机: {neighbor1.remote_hostname}")
    print(f"   远程接口: {neighbor1.remote_interface}")
    print(f"   远程平台: {neighbor1.remote_platform}")

    if (
        neighbor1.local_interface == "GigabitEthernet1/0/1"
        and neighbor1.remote_hostname == "Core-Switch-01"
        and neighbor1.remote_interface == "GigabitEthernet1/0/24"
    ):
        print("   ✅ PASS: 邻居 1 解析正确")
    else:
        print("   ❌ FAIL: 邻居 1 解析错误")
        return False

    # 验证第二个邻居
    neighbor2 = results[1]
    print(f"\n邻居 2:")
    print(f"   本地接口: {neighbor2.local_interface}")
    print(f"   远程主机: {neighbor2.remote_hostname}")
    print(f"   远程接口: {neighbor2.remote_interface}")

    if (
        neighbor2.local_interface == "GigabitEthernet1/0/2"
        and neighbor2.remote_hostname == "Core-Switch-02"
        and neighbor2.remote_interface == "GigabitEthernet1/0/25"
    ):
        print("   ✅ PASS: 邻居 2 解析正确")
        return True
    else:
        print("   ❌ FAIL: 邻居 2 解析错误")
        return False


def test_cisco_ios_parser():
    """测试 Cisco IOS CDP Parser。"""
    print("\n" + "=" * 60)
    print("测试 Cisco IOS CDP Parser")
    print("=" * 60)

    parser = CiscoIosNeighborParser()
    results = parser.parse(CISCO_IOS_CDP_OUTPUT)

    print(f"\n解析结果: 找到 {len(results)} 个邻居")

    if len(results) != 2:
        print(f"   ❌ FAIL: 期望 2 个邻居，实际找到 {len(results)} 个")
        return False

    # 验证第一个邻居
    neighbor1 = results[0]
    print(f"\n邻居 1:")
    print(f"   本地接口: {neighbor1.local_interface}")
    print(f"   远程主机: {neighbor1.remote_hostname}")
    print(f"   远程接口: {neighbor1.remote_interface}")
    print(f"   远程平台: {neighbor1.remote_platform}")

    if (
        neighbor1.local_interface == "GigabitEthernet1/0/1"
        and neighbor1.remote_hostname == "Router01"
        and neighbor1.remote_interface == "GigabitEthernet1/0/24"
    ):
        print("   ✅ PASS: 邻居 1 解析正确")
    else:
        print("   ❌ FAIL: 邻居 1 解析错误")
        return False

    # 验证第二个邻居
    neighbor2 = results[1]
    print(f"\n邻居 2:")
    print(f"   本地接口: {neighbor2.local_interface}")
    print(f"   远程主机: {neighbor2.remote_hostname}")
    print(f"   远程接口: {neighbor2.remote_interface}")

    if (
        neighbor2.local_interface == "GigabitEthernet1/0/2"
        and neighbor2.remote_hostname == "Switch02"
        and neighbor2.remote_interface == "GigabitEthernet1/0/1"
    ):
        print("   ✅ PASS: 邻居 2 解析正确")
        return True
    else:
        print("   ❌ FAIL: 邻居 2 解析错误")
        return False


def test_parser_registry():
    """测试 ParserRegistry 可以找到新的 parsers。"""
    print("\n" + "=" * 60)
    print("测试 ParserRegistry")
    print("=" * 60)

    test_cases = [
        (VendorType.CISCO, PlatformType.CISCO_NXOS, "uplink", "CiscoNxosNeighborParser"),
        (VendorType.HPE, PlatformType.HPE_COMWARE, "uplink", "HpeComwareNeighborParser"),
        (VendorType.CISCO, PlatformType.CISCO_IOS, "uplink", "CiscoIosNeighborParser"),
    ]

    all_passed = True

    for vendor, platform, indicator_type, expected_class in test_cases:
        parser = parser_registry.get(vendor, platform, indicator_type)
        if parser:
            actual_class = parser.__class__.__name__
            if actual_class == expected_class:
                print(f"   ✅ PASS: 找到 {vendor.value}/{platform.value}/{indicator_type} -> {actual_class}")
            else:
                print(f"   ❌ FAIL: {vendor.value}/{platform.value}/{indicator_type} 返回错误的 parser: {actual_class}")
                all_passed = False
        else:
            print(f"   ❌ FAIL: 找不到 {vendor.value}/{platform.value}/{indicator_type} parser")
            all_passed = False

    return all_passed


def main():
    """运行所有测试。"""
    print("\n" + "=" * 60)
    print("Phase 2 Neighbor Parser 功能测试")
    print("=" * 60)

    results = []

    # 测试 1: Cisco NXOS Parser
    results.append(("Cisco NXOS LLDP Parser", test_cisco_nxos_parser()))

    # 测试 2: HPE Comware Parser
    results.append(("HPE Comware LLDP Parser", test_hpe_comware_parser()))

    # 测试 3: Cisco IOS Parser
    results.append(("Cisco IOS CDP Parser", test_cisco_ios_parser()))

    # 测试 4: Parser Registry
    results.append(("Parser Registry", test_parser_registry()))

    # 打印总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n🎉 所有测试通过! Phase 2 Neighbor Parsers 实现成功!")
        print("\n已实现的 Parsers:")
        print("  1. Cisco NXOS LLDP Neighbor Parser (show lldp neighbors detail)")
        print("  2. HPE Comware LLDP Neighbor Parser (display lldp neighbor-information)")
        print("  3. Cisco IOS CDP Neighbor Parser (show cdp neighbors detail)")
        print("\n下一步:")
        print("  继续 Phase 3: 创建 Mock API Server 和测试数据")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查实现")
        return 1


if __name__ == "__main__":
    sys.exit(main())
