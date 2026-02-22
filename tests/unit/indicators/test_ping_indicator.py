"""
Tests for PingIndicator.evaluate().

Mock 策略：patch _get_expected_devices / _get_collected_results，
避免真實 DB 查詢，只驗證 evaluate() 內的評估邏輯。
"""
from __future__ import annotations

from datetime import datetime, UTC
from unittest.mock import AsyncMock, patch

import pytest

from app.indicators.ping import PingIndicator

MAINTENANCE_ID = "TEST-001"


# ── helpers ───────────────────────────────────────────────────────

def _make_device(hostname: str, ip: str) -> dict:
    """建立 _get_expected_devices 回傳格式的設備字典。"""
    return {"new_hostname": hostname, "new_ip_address": ip}


def _make_collected_entry(
    is_reachable: bool,
    success_rate: float = 100.0,
    last_check_at: datetime | None = None,
) -> dict:
    """建立 _get_collected_results 回傳格式的設備狀態字典。"""
    return {
        "is_reachable": is_reachable,
        "success_rate": success_rate,
        "last_check_at": last_check_at,
    }


# ── Test class ────────────────────────────────────────────────────


class TestPingIndicatorEvaluate:
    """PingIndicator.evaluate() 各種情境測試。"""

    @pytest.mark.asyncio
    async def test_all_devices_reachable(self):
        """3 台設備全部可達 → pass_count=3, fail_count=0, 無 failures。"""
        indicator = PingIndicator()
        session = AsyncMock()

        expected = [
            _make_device("SW-NEW-001", "10.1.2.1"),
            _make_device("SW-NEW-002", "10.1.2.2"),
            _make_device("SW-NEW-003", "10.1.2.3"),
        ]
        collected = {
            "SW-NEW-001": _make_collected_entry(True, 100.0),
            "SW-NEW-002": _make_collected_entry(True, 95.0),
            "SW-NEW-003": _make_collected_entry(True, 80.0),
        }

        with patch.object(indicator, "_get_expected_devices", new_callable=AsyncMock) as mock_exp, \
             patch.object(indicator, "_get_collected_results", new_callable=AsyncMock) as mock_col:
            mock_exp.return_value = expected
            mock_col.return_value = collected

            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.indicator_type == "ping"
        assert result.maintenance_id == MAINTENANCE_ID
        assert result.total_count == 3
        assert result.pass_count == 3
        assert result.fail_count == 0
        assert result.failures is None
        assert result.passes is not None
        assert len(result.passes) == 3
        assert result.summary == "連通性檢查: 3/3 新設備可達"

    @pytest.mark.asyncio
    async def test_some_devices_unreachable(self):
        """3 台設備，1 台不可達 → pass_count=2, fail_count=1，檢查 failure reason。"""
        indicator = PingIndicator()
        session = AsyncMock()

        ts = datetime(2025, 6, 15, 10, 30, 0, tzinfo=UTC)

        expected = [
            _make_device("SW-NEW-001", "10.1.2.1"),
            _make_device("SW-NEW-002", "10.1.2.2"),
            _make_device("SW-NEW-003", "10.1.2.3"),
        ]
        collected = {
            "SW-NEW-001": _make_collected_entry(True, 100.0, ts),
            "SW-NEW-002": _make_collected_entry(False, 0.0, ts),
            "SW-NEW-003": _make_collected_entry(True, 90.0, ts),
        }

        with patch.object(indicator, "_get_expected_devices", new_callable=AsyncMock) as mock_exp, \
             patch.object(indicator, "_get_collected_results", new_callable=AsyncMock) as mock_col:
            mock_exp.return_value = expected
            mock_col.return_value = collected

            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 3
        assert result.pass_count == 2
        assert result.fail_count == 1

        # 驗證失敗清單
        assert result.failures is not None
        assert len(result.failures) == 1
        fail = result.failures[0]
        assert fail["device"] == "SW-NEW-002"
        assert fail["reason"] == "Ping 不可達"
        assert fail["data"]["is_reachable"] is False
        assert fail["data"]["success_rate"] == 0.0
        assert fail["data"]["last_check_at"] == str(ts)

    @pytest.mark.asyncio
    async def test_no_devices_in_list(self):
        """期望設備數為 0 → total_count=0, summary 包含 "無新設備資料"。"""
        indicator = PingIndicator()
        session = AsyncMock()

        with patch.object(indicator, "_get_expected_devices", new_callable=AsyncMock) as mock_exp:
            mock_exp.return_value = []

            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 0
        assert result.pass_count == 0
        assert result.fail_count == 0
        assert result.pass_rates == {"reachable": 0.0}
        assert result.failures is None
        assert "無新設備資料" in result.summary

    @pytest.mark.asyncio
    async def test_no_collected_data(self):
        """3 台期望設備但 0 筆採集資料 → 全部失敗，reason = "尚無採集數據"。"""
        indicator = PingIndicator()
        session = AsyncMock()

        expected = [
            _make_device("SW-NEW-001", "10.1.2.1"),
            _make_device("SW-NEW-002", "10.1.2.2"),
            _make_device("SW-NEW-003", "10.1.2.3"),
        ]

        with patch.object(indicator, "_get_expected_devices", new_callable=AsyncMock) as mock_exp, \
             patch.object(indicator, "_get_collected_results", new_callable=AsyncMock) as mock_col:
            mock_exp.return_value = expected
            mock_col.return_value = {}  # 無任何採集數據

            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 3
        assert result.pass_count == 0
        assert result.fail_count == 3
        assert result.failures is not None
        assert len(result.failures) == 3

        # 每個 failure 的 reason 都是 "尚無採集數據"
        for fail in result.failures:
            assert fail["reason"] == "尚無採集數據"
            assert fail["data"] is None

        hostnames = {f["device"] for f in result.failures}
        assert hostnames == {"SW-NEW-001", "SW-NEW-002", "SW-NEW-003"}

    @pytest.mark.asyncio
    async def test_device_missing_from_collected(self):
        """3 台期望設備，只有 2 台有採集數據 → 缺少的那台計入 failure。"""
        indicator = PingIndicator()
        session = AsyncMock()

        expected = [
            _make_device("SW-NEW-001", "10.1.2.1"),
            _make_device("SW-NEW-002", "10.1.2.2"),
            _make_device("SW-NEW-003", "10.1.2.3"),
        ]
        collected = {
            "SW-NEW-001": _make_collected_entry(True, 100.0),
            "SW-NEW-003": _make_collected_entry(True, 100.0),
            # SW-NEW-002 缺失
        }

        with patch.object(indicator, "_get_expected_devices", new_callable=AsyncMock) as mock_exp, \
             patch.object(indicator, "_get_collected_results", new_callable=AsyncMock) as mock_col:
            mock_exp.return_value = expected
            mock_col.return_value = collected

            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 3
        assert result.pass_count == 2
        assert result.fail_count == 1
        assert result.failures is not None
        assert len(result.failures) == 1
        assert result.failures[0]["device"] == "SW-NEW-002"
        assert result.failures[0]["reason"] == "尚無採集數據"

    @pytest.mark.asyncio
    async def test_multiple_records_per_device_best_wins(self):
        """
        _get_collected_results 內部會取「最佳」結果 (reachable > not reachable)。
        此處直接 mock 回傳 collected，確認當 collected 中該設備最終為 reachable 時，
        evaluate 判定為通過。

        另外測試：若最終狀態為不可達，則判定為失敗。
        """
        indicator = PingIndicator()
        session = AsyncMock()

        expected = [
            _make_device("SW-NEW-001", "10.1.2.1"),
            _make_device("SW-NEW-002", "10.1.2.2"),
        ]
        # 模擬 _get_collected_results 已經做完「取最佳」邏輯後的結果：
        # SW-NEW-001: 最佳結果是 reachable（雖然可能有多筆 record）
        # SW-NEW-002: 最佳結果仍是 not reachable
        collected = {
            "SW-NEW-001": _make_collected_entry(True, 100.0),
            "SW-NEW-002": _make_collected_entry(False, 30.0),
        }

        with patch.object(indicator, "_get_expected_devices", new_callable=AsyncMock) as mock_exp, \
             patch.object(indicator, "_get_collected_results", new_callable=AsyncMock) as mock_col:
            mock_exp.return_value = expected
            mock_col.return_value = collected

            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.pass_count == 1
        assert result.fail_count == 1

        # SW-NEW-001 通過
        assert result.passes is not None
        assert any(p["device"] == "SW-NEW-001" for p in result.passes)

        # SW-NEW-002 失敗
        assert result.failures is not None
        assert len(result.failures) == 1
        assert result.failures[0]["device"] == "SW-NEW-002"
        assert result.failures[0]["reason"] == "Ping 不可達"

    @pytest.mark.asyncio
    async def test_pass_rate_calculation(self):
        """驗證 pass_rates["reachable"] 百分比計算正確。"""
        indicator = PingIndicator()
        session = AsyncMock()

        # 5 台設備，3 台可達 → reachable = 60.0%
        expected = [
            _make_device(f"SW-NEW-{i:03d}", f"10.1.2.{i}")
            for i in range(1, 6)
        ]
        collected = {
            "SW-NEW-001": _make_collected_entry(True, 100.0),
            "SW-NEW-002": _make_collected_entry(True, 90.0),
            "SW-NEW-003": _make_collected_entry(False, 10.0),
            "SW-NEW-004": _make_collected_entry(True, 85.0),
            "SW-NEW-005": _make_collected_entry(False, 0.0),
        }

        with patch.object(indicator, "_get_expected_devices", new_callable=AsyncMock) as mock_exp, \
             patch.object(indicator, "_get_collected_results", new_callable=AsyncMock) as mock_col:
            mock_exp.return_value = expected
            mock_col.return_value = collected

            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 5
        assert result.pass_count == 3
        assert result.fail_count == 2

        # 3 / 5 * 100 = 60.0
        assert result.pass_rates["reachable"] == pytest.approx(60.0)

        # 也驗證 IndicatorEvaluationResult 的 property
        assert result.pass_rate_percent == pytest.approx(60.0)

        assert result.summary == "連通性檢查: 3/5 新設備可達"

    @pytest.mark.asyncio
    async def test_pass_rate_zero_when_no_devices(self):
        """0 台設備時 pass_rates["reachable"] = 0.0，不會除以零。"""
        indicator = PingIndicator()
        session = AsyncMock()

        with patch.object(indicator, "_get_expected_devices", new_callable=AsyncMock) as mock_exp:
            mock_exp.return_value = []
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.pass_rates["reachable"] == 0.0
        assert result.pass_rate_percent == 0.0

    @pytest.mark.asyncio
    async def test_passes_capped_at_ten(self):
        """passes 列表最多保留 10 筆（避免回傳過大）。"""
        indicator = PingIndicator()
        session = AsyncMock()

        expected = [
            _make_device(f"SW-NEW-{i:03d}", f"10.1.2.{i}")
            for i in range(1, 16)  # 15 台設備
        ]
        collected = {
            f"SW-NEW-{i:03d}": _make_collected_entry(True, 100.0)
            for i in range(1, 16)
        }

        with patch.object(indicator, "_get_expected_devices", new_callable=AsyncMock) as mock_exp, \
             patch.object(indicator, "_get_collected_results", new_callable=AsyncMock) as mock_col:
            mock_exp.return_value = expected
            mock_col.return_value = collected

            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.pass_count == 15
        assert result.fail_count == 0
        # passes 應被截斷到 10 筆
        assert result.passes is not None
        assert len(result.passes) == 10

    @pytest.mark.asyncio
    async def test_last_check_at_none_renders_as_none_string(self):
        """last_check_at 為 None 時，failure data 中的值也為 None。"""
        indicator = PingIndicator()
        session = AsyncMock()

        expected = [_make_device("SW-NEW-001", "10.1.2.1")]
        collected = {
            "SW-NEW-001": _make_collected_entry(False, 0.0, None),
        }

        with patch.object(indicator, "_get_expected_devices", new_callable=AsyncMock) as mock_exp, \
             patch.object(indicator, "_get_collected_results", new_callable=AsyncMock) as mock_col:
            mock_exp.return_value = expected
            mock_col.return_value = collected

            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.failures is not None
        fail_data = result.failures[0]["data"]
        assert fail_data["last_check_at"] is None

    @pytest.mark.asyncio
    async def test_interface_field_always_mgmt(self):
        """所有 failures / passes 的 interface 欄位固定為 'Mgmt'。"""
        indicator = PingIndicator()
        session = AsyncMock()

        expected = [
            _make_device("SW-NEW-001", "10.1.2.1"),
            _make_device("SW-NEW-002", "10.1.2.2"),
        ]
        collected = {
            "SW-NEW-001": _make_collected_entry(True, 100.0),
            "SW-NEW-002": _make_collected_entry(False, 0.0),
        }

        with patch.object(indicator, "_get_expected_devices", new_callable=AsyncMock) as mock_exp, \
             patch.object(indicator, "_get_collected_results", new_callable=AsyncMock) as mock_col:
            mock_exp.return_value = expected
            mock_col.return_value = collected

            result = await indicator.evaluate(MAINTENANCE_ID, session)

        for p in (result.passes or []):
            assert p["interface"] == "Mgmt"
        for f in (result.failures or []):
            assert f["interface"] == "Mgmt"


class TestPingIndicatorMetadata:
    """PingIndicator.get_metadata() 基本驗證。"""

    def test_metadata_fields(self):
        indicator = PingIndicator()
        meta = indicator.get_metadata()

        assert meta.name == "ping"
        assert meta.title == "設備連通性監控"
        assert meta.object_type == "switch"
        assert meta.data_type == "boolean"
        assert len(meta.observed_fields) == 1
        assert meta.observed_fields[0].name == "reachable"
        assert meta.display_config.chart_type == "gauge"


class TestCalcPercent:
    """PingIndicator._calc_percent() 靜態方法。"""

    def test_normal(self):
        assert PingIndicator._calc_percent(3, 5) == pytest.approx(60.0)

    def test_all_pass(self):
        assert PingIndicator._calc_percent(10, 10) == pytest.approx(100.0)

    def test_none_pass(self):
        assert PingIndicator._calc_percent(0, 10) == pytest.approx(0.0)

    def test_zero_total(self):
        """分母為 0 時回傳 0.0，不 raise ZeroDivisionError。"""
        assert PingIndicator._calc_percent(0, 0) == 0.0
