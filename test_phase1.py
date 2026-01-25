#!/usr/bin/env python3
"""
快速测试 Phase 1 实现的功能。

测试内容：
1. IndicatorService.get_all_indicators() 返回8个指标
2. IndicatorService.get_indicator() 可以获取特定指标
3. TransceiverIndicator.get_metadata() 返回正确的元数据
4. PingIndicator.get_metadata() 返回正确的元数据
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径到 sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.services.indicator_service import IndicatorService


def test_indicator_service():
    """测试 IndicatorService 的新方法。"""
    print("=" * 60)
    print("测试 IndicatorService")
    print("=" * 60)

    service = IndicatorService()

    # 测试 get_all_indicators()
    print("\n1. 测试 get_all_indicators()")
    indicators = service.get_all_indicators()
    print(f"   返回指标数量: {len(indicators)}")

    if len(indicators) == 8:
        print("   ✅ PASS: 返回了8个指标")
    else:
        print(f"   ❌ FAIL: 期望8个指标，实际返回 {len(indicators)} 个")
        return False

    # 测试 get_indicator()
    print("\n2. 测试 get_indicator()")
    test_cases = [
        ("transceiver", "TransceiverIndicator"),
        ("ping", "PingIndicator"),
        ("version", "VersionIndicator"),
        ("uplink", "UplinkIndicator"),
        ("nonexistent", None),
    ]

    for name, expected_class in test_cases:
        indicator = service.get_indicator(name)
        if expected_class is None:
            if indicator is None:
                print(f"   ✅ PASS: get_indicator('{name}') 正确返回 None")
            else:
                print(f"   ❌ FAIL: get_indicator('{name}') 应该返回 None")
        else:
            if indicator and indicator.__class__.__name__ == expected_class:
                print(f"   ✅ PASS: get_indicator('{name}') 返回 {expected_class}")
            else:
                print(f"   ❌ FAIL: get_indicator('{name}') 返回错误")

    return True


def test_transceiver_metadata():
    """测试 TransceiverIndicator.get_metadata()。"""
    print("\n" + "=" * 60)
    print("测试 TransceiverIndicator.get_metadata()")
    print("=" * 60)

    service = IndicatorService()
    indicator = service.get_indicator("transceiver")

    try:
        metadata = indicator.get_metadata()
        print(f"\n   ✅ PASS: get_metadata() 成功执行")
        print(f"   - name: {metadata.name}")
        print(f"   - title: {metadata.title}")
        print(f"   - object_type: {metadata.object_type}")
        print(f"   - data_type: {metadata.data_type}")
        print(f"   - observed_fields: {len(metadata.observed_fields)} 个字段")

        for field in metadata.observed_fields:
            print(f"     - {field.name} ({field.display_name}): {field.unit}")

        print(f"   - chart_type: {metadata.display_config.chart_type}")

        # 验证必要字段
        assert metadata.name == "transceiver", "name 应该是 'transceiver'"
        assert metadata.object_type == "interface", "object_type 应该是 'interface'"
        assert len(metadata.observed_fields) == 4, "应该有4个观测字段"

        print("\n   ✅ 所有验证通过!")
        return True
    except Exception as e:
        print(f"\n   ❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ping_metadata():
    """测试 PingIndicator.get_metadata()。"""
    print("\n" + "=" * 60)
    print("测试 PingIndicator.get_metadata()")
    print("=" * 60)

    service = IndicatorService()
    indicator = service.get_indicator("ping")

    try:
        metadata = indicator.get_metadata()
        print(f"\n   ✅ PASS: get_metadata() 成功执行")
        print(f"   - name: {metadata.name}")
        print(f"   - title: {metadata.title}")
        print(f"   - object_type: {metadata.object_type}")
        print(f"   - data_type: {metadata.data_type}")
        print(f"   - chart_type: {metadata.display_config.chart_type}")

        # 验证必要字段
        assert metadata.name == "ping", "name 应该是 'ping'"
        assert metadata.object_type == "switch", "object_type 应该是 'switch'"
        assert metadata.data_type == "boolean", "data_type 应该是 'boolean'"

        print("\n   ✅ 所有验证通过!")
        return True
    except Exception as e:
        print(f"\n   ❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_time_series_and_raw_data():
    """测试 get_time_series() 和 get_latest_raw_data()。"""
    print("\n" + "=" * 60)
    print("测试 get_time_series() 和 get_latest_raw_data()")
    print("=" * 60)
    print("\n   ⚠️  注意: 这些方法需要数据库连接和测试数据")
    print("   当前仅测试方法是否存在，不测试实际执行")

    service = IndicatorService()
    transceiver = service.get_indicator("transceiver")

    # 检查方法是否存在
    has_get_time_series = hasattr(transceiver, 'get_time_series')
    has_get_latest_raw_data = hasattr(transceiver, 'get_latest_raw_data')

    if has_get_time_series:
        print("\n   ✅ PASS: get_time_series() 方法存在")
    else:
        print("\n   ❌ FAIL: get_time_series() 方法不存在")

    if has_get_latest_raw_data:
        print("   ✅ PASS: get_latest_raw_data() 方法存在")
    else:
        print("   ❌ FAIL: get_latest_raw_data() 方法不存在")

    return has_get_time_series and has_get_latest_raw_data


def main():
    """运行所有测试。"""
    print("\n" + "=" * 60)
    print("Phase 1 功能测试")
    print("=" * 60)

    results = []

    # 测试 1: IndicatorService 基本方法
    results.append(("IndicatorService 基本方法", test_indicator_service()))

    # 测试 2: TransceiverIndicator metadata
    results.append(("TransceiverIndicator.get_metadata()", test_transceiver_metadata()))

    # 测试 3: PingIndicator metadata
    results.append(("PingIndicator.get_metadata()", test_ping_metadata()))

    # 测试 4: 时间序列和原始数据方法
    results.append(("时间序列和原始数据方法", asyncio.run(test_time_series_and_raw_data())))

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
        print("\n🎉 所有测试通过! Phase 1 部分功能验证成功!")
        print("\n下一步:")
        print("  1. 继续实现剩余6个指标的方法")
        print("  2. 或者先实现 Phase 2 的 Uplink Parser")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查实现")
        return 1


if __name__ == "__main__":
    sys.exit(main())
