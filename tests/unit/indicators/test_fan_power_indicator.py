"""
Comprehensive unit tests for FanIndicator and PowerIndicator.

Tests cover:
- evaluate() with all fans/PSUs healthy -> all pass
- evaluate() with failed/abnormal status -> failures
- evaluate() with no collected data for a device -> failure with "尚無採集資料"
- evaluate() with empty device list -> total_count=0
- evaluate() with mixed healthy and unhealthy fans/PSUs per device
- evaluate() with records from non-active devices filtered out
- evaluate() pass capping at 10 entries
- _calc_percent edge cases
- Status case-insensitivity and whitespace trimming
- Various healthy status strings (ok, good, normal, online, active)
- Summary and pass_rates format verification
- indicator_type and maintenance_id in result
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.indicators.fan import FanIndicator
from app.indicators.power import PowerIndicator


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAINTENANCE_ID = "MAINT-TEST-001"

# Must match settings.operational_healthy_set default:
# "ok,good,normal,online,active"
HEALTHY_STATUSES = {"ok", "good", "normal", "online", "active"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fan_record(
    switch_hostname: str = "SW-01",
    fan_id: str = "Fan1",
    status: str = "ok",
    collected_at: datetime | None = None,
) -> MagicMock:
    """Create a mock FanRecord with the given attributes."""
    record = MagicMock()
    record.switch_hostname = switch_hostname
    record.fan_id = fan_id
    record.status = status
    record.collected_at = collected_at or datetime(2026, 1, 15, 12, 0, 0)
    return record


def _make_power_record(
    switch_hostname: str = "SW-01",
    ps_id: str = "PS1",
    status: str = "ok",
    collected_at: datetime | None = None,
) -> MagicMock:
    """Create a mock PowerRecord with the given attributes."""
    record = MagicMock()
    record.switch_hostname = switch_hostname
    record.ps_id = ps_id
    record.status = status
    record.collected_at = collected_at or datetime(2026, 1, 15, 12, 0, 0)
    return record


# ===================================================================
# FanIndicator Tests
# ===================================================================


class TestFanIndicatorEvaluate:
    """FanIndicator.evaluate() tests."""

    @pytest.fixture()
    def indicator(self) -> FanIndicator:
        return FanIndicator()

    @pytest.fixture()
    def mock_session(self) -> AsyncMock:
        return AsyncMock()

    # 1. All fans healthy -> all pass ----------------------------------------

    async def test_all_fans_healthy(
        self, indicator: FanIndicator, mock_session: AsyncMock,
    ) -> None:
        """All fans report healthy status -> pass_count equals total devices."""
        records = [
            _make_fan_record("SW-01", "Fan1", "ok"),
            _make_fan_record("SW-01", "Fan2", "ok"),
            _make_fan_record("SW-02", "Fan1", "good"),
            _make_fan_record("SW-02", "Fan2", "normal"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01", "SW-02"],
            ),
            patch(
                "app.indicators.fan.FanRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.indicator_type == "fan"
        assert result.maintenance_id == MAINTENANCE_ID
        assert result.total_count == 2
        assert result.pass_count == 2
        assert result.fail_count == 0
        assert result.failures is None
        assert result.passes is not None
        assert len(result.passes) == 2
        assert result.pass_rates["status_ok"] == 100.0

    # 2. Fan with failed status -> failure -----------------------------------

    async def test_fan_failed_status(
        self, indicator: FanIndicator, mock_session: AsyncMock,
    ) -> None:
        """One fan reports 'failed' -> that device fails."""
        records = [
            _make_fan_record("SW-01", "Fan1", "ok"),
            _make_fan_record("SW-01", "Fan2", "failed"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.fan.FanRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert len(result.failures) == 1
        assert result.failures[0]["device"] == "SW-01"
        assert result.failures[0]["interface"] == "Cooling System"
        assert "Fan2" in result.failures[0]["reason"]
        assert "狀態異常" in result.failures[0]["reason"]
        assert result.failures[0]["data"] is not None
        assert len(result.failures[0]["data"]) == 2

    # 3. Multiple fans failed on same device -> single failure entry ---------

    async def test_multiple_fans_failed_same_device(
        self, indicator: FanIndicator, mock_session: AsyncMock,
    ) -> None:
        """Multiple fans on one device fail -> one failure entry with pipe-separated reasons."""
        records = [
            _make_fan_record("SW-01", "Fan1", "failed"),
            _make_fan_record("SW-01", "Fan2", "absent"),
            _make_fan_record("SW-01", "Fan3", "ok"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.fan.FanRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        failure = result.failures[0]
        assert "Fan1" in failure["reason"]
        assert "Fan2" in failure["reason"]
        assert " | " in failure["reason"]
        # Fan3 is ok, so should not appear in the reason
        assert "Fan3" not in failure["reason"]

    # 4. No collected data for device -> failure -----------------------------

    async def test_no_collected_data_for_device(
        self, indicator: FanIndicator, mock_session: AsyncMock,
    ) -> None:
        """Device exists but no fan records collected -> failure with '尚無採集資料'."""
        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01", "SW-02"],
            ),
            patch(
                "app.indicators.fan.FanRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=[
                    _make_fan_record("SW-01", "Fan1", "ok"),
                ],
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 2
        assert result.pass_count == 1
        assert result.fail_count == 1
        assert result.failures is not None
        missing_failure = [f for f in result.failures if f["device"] == "SW-02"]
        assert len(missing_failure) == 1
        assert missing_failure[0]["reason"] == "尚無採集資料"
        assert missing_failure[0]["data"] is None
        assert missing_failure[0]["interface"] == "Cooling System"

    # 5. Empty device list -> zero counts ------------------------------------

    async def test_empty_device_list(
        self, indicator: FanIndicator, mock_session: AsyncMock,
    ) -> None:
        """No active devices -> total_count=0, summary '無設備資料'."""
        with patch.object(
            indicator, "_get_active_device_hostnames",
            new_callable=AsyncMock, return_value=[],
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 0
        assert result.pass_count == 0
        assert result.fail_count == 0
        assert result.pass_rates == {"status_ok": 0}
        assert result.summary == "無設備資料"
        assert result.failures is None
        assert result.passes is None

    # 6. Records from non-active devices are filtered out --------------------

    async def test_non_active_device_records_filtered(
        self, indicator: FanIndicator, mock_session: AsyncMock,
    ) -> None:
        """Records from inactive devices should not appear in results."""
        records = [
            _make_fan_record("SW-01", "Fan1", "ok"),
            _make_fan_record("SW-99", "Fan1", "failed"),  # inactive device
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.fan.FanRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 1
        assert result.fail_count == 0
        # Verify SW-99 is nowhere in passes or failures
        all_devices = set()
        if result.passes:
            all_devices.update(p["device"] for p in result.passes)
        if result.failures:
            all_devices.update(f["device"] for f in result.failures)
        assert "SW-99" not in all_devices

    # 7. Various healthy statuses accepted -----------------------------------

    @pytest.mark.parametrize("status", ["ok", "good", "normal", "online", "active"])
    async def test_various_healthy_statuses(
        self, indicator: FanIndicator, mock_session: AsyncMock, status: str,
    ) -> None:
        """All recognized healthy statuses should mark the device as passing."""
        records = [_make_fan_record("SW-01", "Fan1", status)]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.fan.FanRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.pass_count == 1
        assert result.fail_count == 0

    # 8. Status is case-insensitive and whitespace-trimmed -------------------

    @pytest.mark.parametrize("status", ["OK", "Ok", " ok ", "  Good  ", "NORMAL"])
    async def test_status_case_insensitive_and_trimmed(
        self, indicator: FanIndicator, mock_session: AsyncMock, status: str,
    ) -> None:
        """Status comparison should be case-insensitive and trim whitespace."""
        records = [_make_fan_record("SW-01", "Fan1", status)]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.fan.FanRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.pass_count == 1
        assert result.fail_count == 0

    # 9. Mixed devices: some pass, some fail ---------------------------------

    async def test_mixed_devices(
        self, indicator: FanIndicator, mock_session: AsyncMock,
    ) -> None:
        """Multiple devices with mixed results -> correct counts and rates."""
        records = [
            _make_fan_record("SW-01", "Fan1", "ok"),
            _make_fan_record("SW-01", "Fan2", "ok"),
            _make_fan_record("SW-02", "Fan1", "failed"),
            _make_fan_record("SW-03", "Fan1", "normal"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01", "SW-02", "SW-03"],
            ),
            patch(
                "app.indicators.fan.FanRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 3
        assert result.pass_count == 2
        assert result.fail_count == 1
        assert result.pass_rates["status_ok"] == pytest.approx(66.6667, abs=0.01)

    # 10. Summary format verification ----------------------------------------

    async def test_summary_format(
        self, indicator: FanIndicator, mock_session: AsyncMock,
    ) -> None:
        """Verify summary follows '風扇檢查: X/Y 設備正常' format."""
        records = [
            _make_fan_record("SW-01", "Fan1", "ok"),
            _make_fan_record("SW-02", "Fan1", "failed"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01", "SW-02"],
            ),
            patch(
                "app.indicators.fan.FanRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.summary == "風扇檢查: 1/2 設備正常"

    # 11. Passes list contents verification ----------------------------------

    async def test_passes_list_contents(
        self, indicator: FanIndicator, mock_session: AsyncMock,
    ) -> None:
        """Pass entries contain device, interface, reason, and data fields."""
        records = [
            _make_fan_record("SW-01", "Fan1", "ok"),
            _make_fan_record("SW-01", "Fan2", "good"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.fan.FanRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.passes is not None
        assert len(result.passes) == 1
        p = result.passes[0]
        assert p["device"] == "SW-01"
        assert p["interface"] == "Cooling System"
        assert "2" in p["reason"]  # "全部 2 個風扇正常"
        assert p["data"] is not None
        assert len(p["data"]) == 2
        assert p["data"][0]["fan_id"] == "Fan1"
        assert p["data"][1]["fan_id"] == "Fan2"

    # 12. Failure data contains all fan records for that device ---------------

    async def test_failure_data_contains_all_fan_records(
        self, indicator: FanIndicator, mock_session: AsyncMock,
    ) -> None:
        """Failure entry data includes all fans for that device, not just failed ones."""
        records = [
            _make_fan_record("SW-01", "Fan1", "ok"),
            _make_fan_record("SW-01", "Fan2", "failed"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.fan.FanRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.failures is not None
        data = result.failures[0]["data"]
        assert len(data) == 2
        fan_ids = {d["fan_id"] for d in data}
        assert fan_ids == {"Fan1", "Fan2"}

    # 13. Passes capped at 10 entries ----------------------------------------

    async def test_passes_capped_at_ten(
        self, indicator: FanIndicator, mock_session: AsyncMock,
    ) -> None:
        """passes list should be capped at 10 entries even with more passing devices."""
        hostnames = [f"SW-{i:02d}" for i in range(1, 16)]
        records = [
            _make_fan_record(h, "Fan1", "ok") for h in hostnames
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=hostnames,
            ),
            patch(
                "app.indicators.fan.FanRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.pass_count == 15
        assert result.fail_count == 0
        assert result.passes is not None
        assert len(result.passes) == 10

    # 14. Unhealthy statuses that should fail --------------------------------

    @pytest.mark.parametrize("status", ["failed", "absent", "error", "shutdown", "unknown", "n/a"])
    async def test_unhealthy_statuses_fail(
        self, indicator: FanIndicator, mock_session: AsyncMock, status: str,
    ) -> None:
        """Statuses not in the healthy set should cause a failure."""
        records = [_make_fan_record("SW-01", "Fan1", status)]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.fan.FanRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert f"Fan Fan1: 狀態異常 ({status})" in result.failures[0]["reason"]

    # 15. All devices missing data -> all failures ---------------------------

    async def test_all_devices_missing_data(
        self, indicator: FanIndicator, mock_session: AsyncMock,
    ) -> None:
        """All devices have no collected data -> all fail."""
        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01", "SW-02", "SW-03"],
            ),
            patch(
                "app.indicators.fan.FanRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=[],
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 3
        assert result.pass_count == 0
        assert result.fail_count == 3
        assert result.passes is None
        assert result.failures is not None
        assert len(result.failures) == 3
        for failure in result.failures:
            assert failure["reason"] == "尚無採集資料"
            assert failure["data"] is None

    # 16. pass_rate_percent property -----------------------------------------

    async def test_pass_rate_percent_property(
        self, indicator: FanIndicator, mock_session: AsyncMock,
    ) -> None:
        """IndicatorEvaluationResult.pass_rate_percent computes correctly."""
        records = [
            _make_fan_record("SW-01", "Fan1", "ok"),
            _make_fan_record("SW-02", "Fan1", "failed"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01", "SW-02"],
            ),
            patch(
                "app.indicators.fan.FanRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.pass_rate_percent == pytest.approx(50.0)


class TestFanCalcPercent:
    """Tests for FanIndicator._calc_percent() edge cases."""

    def test_normal(self) -> None:
        assert FanIndicator._calc_percent(3, 5) == pytest.approx(60.0)

    def test_all_pass(self) -> None:
        assert FanIndicator._calc_percent(10, 10) == pytest.approx(100.0)

    def test_none_pass(self) -> None:
        assert FanIndicator._calc_percent(0, 10) == pytest.approx(0.0)

    def test_zero_total(self) -> None:
        """0/0 -> 0.0, no ZeroDivisionError."""
        assert FanIndicator._calc_percent(0, 0) == 0.0

    def test_returns_float(self) -> None:
        result = FanIndicator._calc_percent(1, 3)
        assert isinstance(result, float)
        assert result == pytest.approx(33.3333, abs=0.01)


class TestFanIndicatorMetadata:
    """FanIndicator.get_metadata() verification."""

    def test_metadata_fields(self) -> None:
        indicator = FanIndicator()
        meta = indicator.get_metadata()

        assert meta.name == "fan"
        assert meta.title == "風扇狀態監控"
        assert meta.object_type == "switch"
        assert meta.data_type == "string"
        assert len(meta.observed_fields) == 1
        assert meta.observed_fields[0].name == "status_ok"
        assert meta.display_config.chart_type == "table"
        assert meta.display_config.show_raw_data_table is True


class TestFanIndicatorType:
    """Verify class-level indicator_type attribute."""

    def test_indicator_type(self) -> None:
        indicator = FanIndicator()
        assert indicator.indicator_type == "fan"


# ===================================================================
# PowerIndicator Tests
# ===================================================================


class TestPowerIndicatorEvaluate:
    """PowerIndicator.evaluate() tests."""

    @pytest.fixture()
    def indicator(self) -> PowerIndicator:
        return PowerIndicator()

    @pytest.fixture()
    def mock_session(self) -> AsyncMock:
        return AsyncMock()

    # 1. All PSUs healthy -> all pass ----------------------------------------

    async def test_all_psus_healthy(
        self, indicator: PowerIndicator, mock_session: AsyncMock,
    ) -> None:
        """All PSUs report healthy status -> pass_count equals total devices."""
        records = [
            _make_power_record("SW-01", "PS1", "ok"),
            _make_power_record("SW-01", "PS2", "ok"),
            _make_power_record("SW-02", "PS1", "good"),
            _make_power_record("SW-02", "PS2", "normal"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01", "SW-02"],
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.indicator_type == "power"
        assert result.maintenance_id == MAINTENANCE_ID
        assert result.total_count == 2
        assert result.pass_count == 2
        assert result.fail_count == 0
        assert result.failures is None
        assert result.passes is not None
        assert len(result.passes) == 2
        assert result.pass_rates["status_ok"] == 100.0

    # 2. PSU with failed status -> failure -----------------------------------

    async def test_psu_failed_status(
        self, indicator: PowerIndicator, mock_session: AsyncMock,
    ) -> None:
        """One PSU reports 'failed' -> that device fails."""
        records = [
            _make_power_record("SW-01", "PS1", "ok"),
            _make_power_record("SW-01", "PS2", "failed"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert len(result.failures) == 1
        assert result.failures[0]["device"] == "SW-01"
        assert result.failures[0]["interface"] == "Power System"
        assert "PS2" in result.failures[0]["reason"]
        assert "狀態異常" in result.failures[0]["reason"]
        assert result.failures[0]["data"] is not None
        assert len(result.failures[0]["data"]) == 2

    # 3. Multiple PSUs failed on same device -> single failure entry ----------

    async def test_multiple_psus_failed_same_device(
        self, indicator: PowerIndicator, mock_session: AsyncMock,
    ) -> None:
        """Multiple PSUs on one device fail -> one failure entry with pipe-separated reasons."""
        records = [
            _make_power_record("SW-01", "PS1", "failed"),
            _make_power_record("SW-01", "PS2", "absent"),
            _make_power_record("SW-01", "PS3", "ok"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        failure = result.failures[0]
        assert "PS1" in failure["reason"]
        assert "PS2" in failure["reason"]
        assert " | " in failure["reason"]
        # PS3 is ok, so should not appear in the reason
        assert "PS3" not in failure["reason"]

    # 4. No collected data for device -> failure -----------------------------

    async def test_no_collected_data_for_device(
        self, indicator: PowerIndicator, mock_session: AsyncMock,
    ) -> None:
        """Device exists but no power records collected -> failure with '尚無採集資料'."""
        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01", "SW-02"],
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=[
                    _make_power_record("SW-01", "PS1", "ok"),
                ],
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 2
        assert result.pass_count == 1
        assert result.fail_count == 1
        assert result.failures is not None
        missing_failure = [f for f in result.failures if f["device"] == "SW-02"]
        assert len(missing_failure) == 1
        assert missing_failure[0]["reason"] == "尚無採集資料"
        assert missing_failure[0]["data"] is None
        assert missing_failure[0]["interface"] == "Power System"

    # 5. Empty device list -> zero counts ------------------------------------

    async def test_empty_device_list(
        self, indicator: PowerIndicator, mock_session: AsyncMock,
    ) -> None:
        """No active devices -> total_count=0, summary '無設備資料'."""
        with patch.object(
            indicator, "_get_active_device_hostnames",
            new_callable=AsyncMock, return_value=[],
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 0
        assert result.pass_count == 0
        assert result.fail_count == 0
        assert result.pass_rates == {"status_ok": 0}
        assert result.summary == "無設備資料"
        assert result.failures is None
        assert result.passes is None

    # 6. Records from non-active devices are filtered out --------------------

    async def test_non_active_device_records_filtered(
        self, indicator: PowerIndicator, mock_session: AsyncMock,
    ) -> None:
        """Records from inactive devices should not appear in results."""
        records = [
            _make_power_record("SW-01", "PS1", "ok"),
            _make_power_record("SW-99", "PS1", "failed"),  # inactive device
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 1
        assert result.fail_count == 0
        all_devices = set()
        if result.passes:
            all_devices.update(p["device"] for p in result.passes)
        if result.failures:
            all_devices.update(f["device"] for f in result.failures)
        assert "SW-99" not in all_devices

    # 7. Various healthy statuses accepted -----------------------------------

    @pytest.mark.parametrize("status", ["ok", "good", "normal", "online", "active"])
    async def test_various_healthy_statuses(
        self, indicator: PowerIndicator, mock_session: AsyncMock, status: str,
    ) -> None:
        """All recognized healthy statuses should mark the device as passing."""
        records = [_make_power_record("SW-01", "PS1", status)]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.pass_count == 1
        assert result.fail_count == 0

    # 8. Status is case-insensitive and whitespace-trimmed -------------------

    @pytest.mark.parametrize("status", ["OK", "Ok", " ok ", "  Good  ", "NORMAL"])
    async def test_status_case_insensitive_and_trimmed(
        self, indicator: PowerIndicator, mock_session: AsyncMock, status: str,
    ) -> None:
        """Status comparison should be case-insensitive and trim whitespace."""
        records = [_make_power_record("SW-01", "PS1", status)]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.pass_count == 1
        assert result.fail_count == 0

    # 9. Mixed devices: some pass, some fail ---------------------------------

    async def test_mixed_devices(
        self, indicator: PowerIndicator, mock_session: AsyncMock,
    ) -> None:
        """Multiple devices with mixed results -> correct counts and rates."""
        records = [
            _make_power_record("SW-01", "PS1", "ok"),
            _make_power_record("SW-01", "PS2", "ok"),
            _make_power_record("SW-02", "PS1", "failed"),
            _make_power_record("SW-03", "PS1", "normal"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01", "SW-02", "SW-03"],
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 3
        assert result.pass_count == 2
        assert result.fail_count == 1
        assert result.pass_rates["status_ok"] == pytest.approx(66.6667, abs=0.01)

    # 10. Summary format verification ----------------------------------------

    async def test_summary_format(
        self, indicator: PowerIndicator, mock_session: AsyncMock,
    ) -> None:
        """Verify summary follows '電源檢查: X/Y 設備正常' format."""
        records = [
            _make_power_record("SW-01", "PS1", "ok"),
            _make_power_record("SW-02", "PS1", "failed"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01", "SW-02"],
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.summary == "電源檢查: 1/2 設備正常"

    # 11. Passes list contents verification ----------------------------------

    async def test_passes_list_contents(
        self, indicator: PowerIndicator, mock_session: AsyncMock,
    ) -> None:
        """Pass entries contain device, interface, reason, and data fields."""
        records = [
            _make_power_record("SW-01", "PS1", "ok"),
            _make_power_record("SW-01", "PS2", "good"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.passes is not None
        assert len(result.passes) == 1
        p = result.passes[0]
        assert p["device"] == "SW-01"
        assert p["interface"] == "Power System"
        assert "2" in p["reason"]  # "全部 2 個電源正常"
        assert p["data"] is not None
        assert len(p["data"]) == 2
        assert p["data"][0]["ps_id"] == "PS1"
        assert p["data"][1]["ps_id"] == "PS2"

    # 12. Failure data contains all PSU records for that device ---------------

    async def test_failure_data_contains_all_psu_records(
        self, indicator: PowerIndicator, mock_session: AsyncMock,
    ) -> None:
        """Failure entry data includes all PSUs for that device, not just failed ones."""
        records = [
            _make_power_record("SW-01", "PS1", "ok"),
            _make_power_record("SW-01", "PS2", "failed"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.failures is not None
        data = result.failures[0]["data"]
        assert len(data) == 2
        ps_ids = {d["ps_id"] for d in data}
        assert ps_ids == {"PS1", "PS2"}

    # 13. Passes capped at 10 entries ----------------------------------------

    async def test_passes_capped_at_ten(
        self, indicator: PowerIndicator, mock_session: AsyncMock,
    ) -> None:
        """passes list should be capped at 10 entries even with more passing devices."""
        hostnames = [f"SW-{i:02d}" for i in range(1, 16)]
        records = [
            _make_power_record(h, "PS1", "ok") for h in hostnames
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=hostnames,
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.pass_count == 15
        assert result.fail_count == 0
        assert result.passes is not None
        assert len(result.passes) == 10

    # 14. Unhealthy statuses that should fail --------------------------------

    @pytest.mark.parametrize("status", ["failed", "absent", "error", "shutdown", "unknown", "n/a"])
    async def test_unhealthy_statuses_fail(
        self, indicator: PowerIndicator, mock_session: AsyncMock, status: str,
    ) -> None:
        """Statuses not in the healthy set should cause a failure."""
        records = [_make_power_record("SW-01", "PS1", status)]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert f"PS PS1: 狀態異常 ({status})" in result.failures[0]["reason"]

    # 15. All devices missing data -> all failures ---------------------------

    async def test_all_devices_missing_data(
        self, indicator: PowerIndicator, mock_session: AsyncMock,
    ) -> None:
        """All devices have no collected data -> all fail."""
        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01", "SW-02", "SW-03"],
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=[],
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 3
        assert result.pass_count == 0
        assert result.fail_count == 3
        assert result.passes is None
        assert result.failures is not None
        assert len(result.failures) == 3
        for failure in result.failures:
            assert failure["reason"] == "尚無採集資料"
            assert failure["data"] is None

    # 16. pass_rate_percent property -----------------------------------------

    async def test_pass_rate_percent_property(
        self, indicator: PowerIndicator, mock_session: AsyncMock,
    ) -> None:
        """IndicatorEvaluationResult.pass_rate_percent computes correctly."""
        records = [
            _make_power_record("SW-01", "PS1", "ok"),
            _make_power_record("SW-02", "PS1", "failed"),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01", "SW-02"],
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.pass_rate_percent == pytest.approx(50.0)

    # 17. Single device with single healthy PSU -> pass ----------------------

    async def test_single_device_single_healthy_psu(
        self, indicator: PowerIndicator, mock_session: AsyncMock,
    ) -> None:
        """Simplest passing case: 1 device, 1 healthy PSU."""
        records = [_make_power_record("SW-01", "PS1", "ok")]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["SW-01"],
            ),
            patch(
                "app.indicators.power.PowerRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 1
        assert result.fail_count == 0
        assert result.pass_rates["status_ok"] == 100.0
        assert result.summary == "電源檢查: 1/1 設備正常"


class TestPowerCalcPercent:
    """Tests for PowerIndicator._calc_percent() edge cases."""

    def test_normal(self) -> None:
        assert PowerIndicator._calc_percent(3, 5) == pytest.approx(60.0)

    def test_all_pass(self) -> None:
        assert PowerIndicator._calc_percent(10, 10) == pytest.approx(100.0)

    def test_none_pass(self) -> None:
        assert PowerIndicator._calc_percent(0, 10) == pytest.approx(0.0)

    def test_zero_total(self) -> None:
        """0/0 -> 0.0, no ZeroDivisionError."""
        assert PowerIndicator._calc_percent(0, 0) == 0.0

    def test_returns_float(self) -> None:
        result = PowerIndicator._calc_percent(1, 3)
        assert isinstance(result, float)
        assert result == pytest.approx(33.3333, abs=0.01)


class TestPowerIndicatorMetadata:
    """PowerIndicator.get_metadata() verification."""

    def test_metadata_fields(self) -> None:
        indicator = PowerIndicator()
        meta = indicator.get_metadata()

        assert meta.name == "power"
        assert meta.title == "電源供應器狀態監控"
        assert meta.object_type == "switch"
        assert meta.data_type == "string"
        assert len(meta.observed_fields) == 1
        assert meta.observed_fields[0].name == "status_ok"
        assert meta.display_config.chart_type == "table"
        assert meta.display_config.show_raw_data_table is True


class TestPowerIndicatorType:
    """Verify class-level indicator_type attribute."""

    def test_indicator_type(self) -> None:
        indicator = PowerIndicator()
        assert indicator.indicator_type == "power"
