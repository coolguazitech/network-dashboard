"""
Comprehensive unit tests for TransceiverIndicator.

Tests cover:
- evaluate() with various record states (all pass, field failures, None fields, etc.)
- Filtering of records from non-active devices
- Empty device list edge case
- _field_pass_rate helper
- _collect_failure_reasons pure helper
- _calc_percent edge cases
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.indicators.transceiver import TransceiverIndicator, _Thresholds


# ── Fixtures ────────────────────────────────────────────────────────

MAINTENANCE_ID = "MAINT-TEST-001"

STANDARD_THRESHOLDS = _Thresholds(
    tx_power_min=-10.0,
    tx_power_max=3.0,
    rx_power_min=-15.0,
    rx_power_max=0.0,
    temperature_min=10.0,
    temperature_max=70.0,
    voltage_min=3.0,
    voltage_max=3.6,
)


def _make_record(
    switch_hostname: str = "SW-01",
    interface_name: str = "GigabitEthernet1/0/1",
    tx_power: float | None = -2.0,
    rx_power: float | None = -5.0,
    temperature: float | None = 35.0,
    voltage: float | None = 3.3,
    collected_at: datetime | None = None,
) -> MagicMock:
    """Create a mock TransceiverRecord with the given attributes."""
    record = MagicMock()
    record.switch_hostname = switch_hostname
    record.interface_name = interface_name
    record.tx_power = tx_power
    record.rx_power = rx_power
    record.temperature = temperature
    record.voltage = voltage
    record.collected_at = collected_at or datetime(2026, 1, 15, 12, 0, 0)
    return record


@pytest.fixture
def indicator() -> TransceiverIndicator:
    return TransceiverIndicator()


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def thresholds() -> _Thresholds:
    return STANDARD_THRESHOLDS


# ── evaluate() Tests ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestEvaluateAllMetricsInRange:
    async def test_all_metrics_in_range(self, indicator, mock_session):
        """All records within thresholds -> all pass."""
        records = [
            _make_record("SW-01", "Gi1/0/1", tx_power=-2.0, rx_power=-5.0, temperature=35.0, voltage=3.3),
            _make_record("SW-01", "Gi1/0/2", tx_power=-1.0, rx_power=-3.0, temperature=25.0, voltage=3.2),
            _make_record("SW-02", "Gi1/0/1", tx_power=0.0, rx_power=-10.0, temperature=50.0, voltage=3.5),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                return_value=["SW-01", "SW-02"],
            ),
            patch.object(
                TransceiverIndicator, "_load_thresholds",
                return_value=STANDARD_THRESHOLDS,
            ),
            patch(
                "app.indicators.transceiver.TransceiverRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 3
        assert result.pass_count == 3
        assert result.fail_count == 0
        assert result.failures is None
        assert result.passes is not None
        assert len(result.passes) == 3
        assert all(p["reason"] == "光模塊正常" for p in result.passes)
        # All field pass rates should be 100%
        assert result.pass_rates["tx_power_ok"] == 100.0
        assert result.pass_rates["rx_power_ok"] == 100.0
        assert result.pass_rates["temperature_ok"] == 100.0
        assert result.pass_rates["voltage_ok"] == 100.0


@pytest.mark.asyncio
class TestEvaluateTxPowerBelowMin:
    async def test_tx_power_below_min(self, indicator, mock_session):
        """tx_power below threshold -> failure with 'Tx Power 過低' in reason."""
        records = [
            _make_record("SW-01", "Gi1/0/1", tx_power=-15.0, rx_power=-5.0, temperature=35.0, voltage=3.3),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                return_value=["SW-01"],
            ),
            patch.object(
                TransceiverIndicator, "_load_thresholds",
                return_value=STANDARD_THRESHOLDS,
            ),
            patch(
                "app.indicators.transceiver.TransceiverRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert len(result.failures) == 1
        assert "Tx Power 過低" in result.failures[0]["reason"]


@pytest.mark.asyncio
class TestEvaluateRxPowerAboveMax:
    async def test_rx_power_above_max(self, indicator, mock_session):
        """rx_power above threshold -> failure with 'Rx Power 過高' in reason."""
        records = [
            _make_record("SW-01", "Gi1/0/1", tx_power=-2.0, rx_power=5.0, temperature=35.0, voltage=3.3),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                return_value=["SW-01"],
            ),
            patch.object(
                TransceiverIndicator, "_load_thresholds",
                return_value=STANDARD_THRESHOLDS,
            ),
            patch(
                "app.indicators.transceiver.TransceiverRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert len(result.failures) == 1
        assert "Rx Power 過高" in result.failures[0]["reason"]


@pytest.mark.asyncio
class TestEvaluateTemperatureOutOfRange:
    async def test_temperature_out_of_range(self, indicator, mock_session):
        """temperature > max -> failure."""
        records = [
            _make_record("SW-01", "Gi1/0/1", tx_power=-2.0, rx_power=-5.0, temperature=85.0, voltage=3.3),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                return_value=["SW-01"],
            ),
            patch.object(
                TransceiverIndicator, "_load_thresholds",
                return_value=STANDARD_THRESHOLDS,
            ),
            patch(
                "app.indicators.transceiver.TransceiverRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert "溫度過高" in result.failures[0]["reason"]


@pytest.mark.asyncio
class TestEvaluateVoltageOutOfRange:
    async def test_voltage_out_of_range(self, indicator, mock_session):
        """voltage < min -> failure."""
        records = [
            _make_record("SW-01", "Gi1/0/1", tx_power=-2.0, rx_power=-5.0, temperature=35.0, voltage=2.5),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                return_value=["SW-01"],
            ),
            patch.object(
                TransceiverIndicator, "_load_thresholds",
                return_value=STANDARD_THRESHOLDS,
            ),
            patch(
                "app.indicators.transceiver.TransceiverRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert "電壓過低" in result.failures[0]["reason"]


@pytest.mark.asyncio
class TestEvaluatePartialNoneIsFailure:
    async def test_partial_none_is_failure(self, indicator, mock_session):
        """rx_power=None but other fields valid -> failure containing 'Rx Power 缺失'."""
        records = [
            _make_record("SW-01", "Gi1/0/1", tx_power=-2.0, rx_power=None, temperature=35.0, voltage=3.3),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                return_value=["SW-01"],
            ),
            patch.object(
                TransceiverIndicator, "_load_thresholds",
                return_value=STANDARD_THRESHOLDS,
            ),
            patch(
                "app.indicators.transceiver.TransceiverRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert "Rx Power 缺失" in result.failures[0]["reason"]


@pytest.mark.asyncio
class TestEvaluateAllFourNoneIsFailure:
    async def test_all_four_none_is_failure(self, indicator, mock_session):
        """All fields None -> failure with '光模塊缺失或無法讀取'."""
        records = [
            _make_record("SW-01", "Gi1/0/1", tx_power=None, rx_power=None, temperature=None, voltage=None),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                return_value=["SW-01"],
            ),
            patch.object(
                TransceiverIndicator, "_load_thresholds",
                return_value=STANDARD_THRESHOLDS,
            ),
            patch(
                "app.indicators.transceiver.TransceiverRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert len(result.failures) == 1
        assert result.failures[0]["reason"] == "光模塊缺失或無法讀取"


@pytest.mark.asyncio
class TestEvaluateRecordsFromNonActiveDevicesFiltered:
    async def test_records_from_non_active_devices_filtered(self, indicator, mock_session):
        """Records exist for inactive device -> not counted."""
        records = [
            _make_record("SW-01", "Gi1/0/1", tx_power=-2.0, rx_power=-5.0, temperature=35.0, voltage=3.3),
            _make_record("SW-99", "Gi1/0/1", tx_power=-2.0, rx_power=-5.0, temperature=35.0, voltage=3.3),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                return_value=["SW-01"],  # SW-99 is not active
            ),
            patch.object(
                TransceiverIndicator, "_load_thresholds",
                return_value=STANDARD_THRESHOLDS,
            ),
            patch(
                "app.indicators.transceiver.TransceiverRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        # Only SW-01 should be counted
        assert result.total_count == 1
        assert result.pass_count == 1
        assert result.fail_count == 0


@pytest.mark.asyncio
class TestEvaluateEmptyDeviceList:
    async def test_empty_device_list(self, indicator, mock_session):
        """No active devices -> total_count=0."""
        with patch.object(
            indicator, "_get_active_device_hostnames",
            return_value=[],
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 0
        assert result.pass_count == 0
        assert result.fail_count == 0
        assert result.pass_rates == {
            "tx_power_ok": 0,
            "rx_power_ok": 0,
            "temperature_ok": 0,
            "voltage_ok": 0,
        }
        assert result.summary == "無設備資料"


@pytest.mark.asyncio
class TestFieldPassRateCalculation:
    async def test_field_pass_rate_calculation(self, indicator, mock_session):
        """Verify _field_pass_rate helper via evaluate pass_rates."""
        records = [
            # tx_power in range, rx_power in range
            _make_record("SW-01", "Gi1/0/1", tx_power=-2.0, rx_power=-5.0, temperature=35.0, voltage=3.3),
            # tx_power out of range (below min), rx_power in range
            _make_record("SW-01", "Gi1/0/2", tx_power=-15.0, rx_power=-5.0, temperature=35.0, voltage=3.3),
            # tx_power in range, rx_power=None (skipped in _field_pass_rate)
            _make_record("SW-02", "Gi1/0/1", tx_power=0.0, rx_power=None, temperature=35.0, voltage=3.3),
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                return_value=["SW-01", "SW-02"],
            ),
            patch.object(
                TransceiverIndicator, "_load_thresholds",
                return_value=STANDARD_THRESHOLDS,
            ),
            patch(
                "app.indicators.transceiver.TransceiverRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        # tx_power: 3 records with values, 2 in range -> 2/3 * 100 ~ 66.67
        assert result.pass_rates["tx_power_ok"] == pytest.approx(66.6667, abs=0.01)
        # rx_power: 2 records with values (one is None), 2 in range -> 100.0
        assert result.pass_rates["rx_power_ok"] == 100.0
        # temperature: all 3 in range -> 100.0
        assert result.pass_rates["temperature_ok"] == 100.0
        # voltage: all 3 in range -> 100.0
        assert result.pass_rates["voltage_ok"] == 100.0


# ── Pure helper tests ───────────────────────────────────────────────


class TestCollectFailureReasonsAllOk:
    def test_collect_failure_reasons_all_ok(self, thresholds):
        """All fields within range -> empty list."""
        record = _make_record(tx_power=-2.0, rx_power=-5.0, temperature=35.0, voltage=3.3)
        reasons = TransceiverIndicator._collect_failure_reasons(record, thresholds)
        assert reasons == []


class TestCollectFailureReasonsMultipleFailures:
    def test_collect_failure_reasons_multiple_failures(self, thresholds):
        """Multiple fields out of range -> multiple reasons."""
        record = _make_record(
            tx_power=-15.0,   # below min (-10.0)
            rx_power=5.0,     # above max (0.0)
            temperature=85.0,  # above max (70.0)
            voltage=2.5,       # below min (3.0)
        )
        reasons = TransceiverIndicator._collect_failure_reasons(record, thresholds)
        assert len(reasons) == 4
        assert any("Tx Power 過低" in r for r in reasons)
        assert any("Rx Power 過高" in r for r in reasons)
        assert any("溫度過高" in r for r in reasons)
        assert any("電壓過低" in r for r in reasons)

    def test_collect_failure_reasons_tx_above_max(self, thresholds):
        """Tx power above max -> 'Tx Power 過高'."""
        record = _make_record(tx_power=5.0, rx_power=-5.0, temperature=35.0, voltage=3.3)
        reasons = TransceiverIndicator._collect_failure_reasons(record, thresholds)
        assert len(reasons) == 1
        assert "Tx Power 過高" in reasons[0]

    def test_collect_failure_reasons_rx_below_min(self, thresholds):
        """Rx power below min -> 'Rx Power 過低'."""
        record = _make_record(tx_power=-2.0, rx_power=-20.0, temperature=35.0, voltage=3.3)
        reasons = TransceiverIndicator._collect_failure_reasons(record, thresholds)
        assert len(reasons) == 1
        assert "Rx Power 過低" in reasons[0]

    def test_collect_failure_reasons_temperature_below_min(self, thresholds):
        """Temperature below min -> '溫度過低'."""
        record = _make_record(tx_power=-2.0, rx_power=-5.0, temperature=5.0, voltage=3.3)
        reasons = TransceiverIndicator._collect_failure_reasons(record, thresholds)
        assert len(reasons) == 1
        assert "溫度過低" in reasons[0]

    def test_collect_failure_reasons_voltage_above_max(self, thresholds):
        """Voltage above max -> '電壓過高'."""
        record = _make_record(tx_power=-2.0, rx_power=-5.0, temperature=35.0, voltage=4.0)
        reasons = TransceiverIndicator._collect_failure_reasons(record, thresholds)
        assert len(reasons) == 1
        assert "電壓過高" in reasons[0]

    def test_collect_failure_reasons_none_fields(self, thresholds):
        """None fields produce '缺失' reasons."""
        record = _make_record(tx_power=None, rx_power=None, temperature=None, voltage=None)
        reasons = TransceiverIndicator._collect_failure_reasons(record, thresholds)
        assert len(reasons) == 4
        assert "Tx Power 缺失" in reasons
        assert "Rx Power 缺失" in reasons
        assert "溫度缺失" in reasons
        assert "電壓缺失" in reasons

    def test_collect_failure_reasons_partial_none(self, thresholds):
        """Partial None fields produce only their '缺失' reasons."""
        record = _make_record(tx_power=-2.0, rx_power=None, temperature=35.0, voltage=None)
        reasons = TransceiverIndicator._collect_failure_reasons(record, thresholds)
        assert len(reasons) == 2
        assert "Rx Power 缺失" in reasons
        assert "電壓缺失" in reasons

    def test_collect_failure_reasons_boundary_values_pass(self, thresholds):
        """Values exactly at boundary (min/max) should pass."""
        record = _make_record(
            tx_power=-10.0,    # exactly at tx_power_min
            rx_power=0.0,      # exactly at rx_power_max
            temperature=10.0,  # exactly at temperature_min
            voltage=3.6,       # exactly at voltage_max
        )
        reasons = TransceiverIndicator._collect_failure_reasons(record, thresholds)
        assert reasons == []


class TestCalcPercent:
    def test_calc_percent_normal(self):
        """Normal case: 3 passed out of 4 -> 75.0%."""
        assert TransceiverIndicator._calc_percent(3, 4) == 75.0

    def test_calc_percent_all_passed(self):
        """All passed -> 100.0%."""
        assert TransceiverIndicator._calc_percent(10, 10) == 100.0

    def test_calc_percent_none_passed(self):
        """None passed -> 0.0%."""
        assert TransceiverIndicator._calc_percent(0, 5) == 0.0

    def test_calc_percent_total_zero(self):
        """Total is 0 -> 0.0% (no division by zero)."""
        assert TransceiverIndicator._calc_percent(0, 0) == 0.0

    def test_calc_percent_one_of_one(self):
        """1 out of 1 -> 100.0%."""
        assert TransceiverIndicator._calc_percent(1, 1) == 100.0

    def test_calc_percent_returns_float(self):
        """Return type is always float."""
        result = TransceiverIndicator._calc_percent(1, 3)
        assert isinstance(result, float)
        assert result == pytest.approx(33.3333, abs=0.01)


class TestFieldPassRate:
    """Direct tests for _field_pass_rate helper method."""

    def test_field_pass_rate_all_in_range(self, indicator):
        records = [
            _make_record(tx_power=-2.0),
            _make_record(tx_power=0.0),
            _make_record(tx_power=3.0),  # boundary
        ]
        rate = indicator._field_pass_rate(records, "tx_power", -10.0, 3.0)
        assert rate == 100.0

    def test_field_pass_rate_some_out_of_range(self, indicator):
        records = [
            _make_record(tx_power=-2.0),
            _make_record(tx_power=-15.0),  # below min
            _make_record(tx_power=5.0),    # above max
        ]
        rate = indicator._field_pass_rate(records, "tx_power", -10.0, 3.0)
        assert rate == pytest.approx(33.3333, abs=0.01)

    def test_field_pass_rate_none_values_skipped(self, indicator):
        """Records with None for the field are excluded from total."""
        records = [
            _make_record(tx_power=-2.0),
            _make_record(tx_power=None),
            _make_record(tx_power=0.0),
        ]
        rate = indicator._field_pass_rate(records, "tx_power", -10.0, 3.0)
        # 2 valid, both in range -> 100.0
        assert rate == 100.0

    def test_field_pass_rate_all_none(self, indicator):
        """All None -> total=0 -> 0.0%."""
        records = [
            _make_record(tx_power=None),
            _make_record(tx_power=None),
        ]
        rate = indicator._field_pass_rate(records, "tx_power", -10.0, 3.0)
        assert rate == 0.0

    def test_field_pass_rate_empty_records(self, indicator):
        """No records -> 0.0%."""
        rate = indicator._field_pass_rate([], "tx_power", -10.0, 3.0)
        assert rate == 0.0


# ── Additional edge-case tests ──────────────────────────────────────


@pytest.mark.asyncio
class TestEvaluateSummaryFormat:
    async def test_summary_format(self, indicator, mock_session):
        """Verify the summary string format."""
        records = [
            _make_record("SW-01", "Gi1/0/1"),
            _make_record("SW-01", "Gi1/0/2", tx_power=-15.0),  # fails
        ]

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                return_value=["SW-01"],
            ),
            patch.object(
                TransceiverIndicator, "_load_thresholds",
                return_value=STANDARD_THRESHOLDS,
            ),
            patch(
                "app.indicators.transceiver.TransceiverRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.summary == "光模塊驗收: 1/2 通過 (50.0%)"


@pytest.mark.asyncio
class TestEvaluateIndicatorType:
    async def test_indicator_type_in_result(self, indicator, mock_session):
        """Result should contain the correct indicator_type."""
        with patch.object(
            indicator, "_get_active_device_hostnames",
            return_value=[],
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.indicator_type == "transceiver"
        assert result.maintenance_id == MAINTENANCE_ID


class TestCheckSingleRecord:
    """Tests for _check_single_record helper."""

    def test_all_ok_returns_none(self, indicator, thresholds):
        record = _make_record(tx_power=-2.0, rx_power=-5.0, temperature=35.0, voltage=3.3)
        result = indicator._check_single_record(record, thresholds)
        assert result is None

    def test_all_none_returns_missing_message(self, indicator, thresholds):
        record = _make_record(tx_power=None, rx_power=None, temperature=None, voltage=None)
        result = indicator._check_single_record(record, thresholds)
        assert result is not None
        assert result["reason"] == "光模塊缺失或無法讀取"
        assert result["device"] == "SW-01"

    def test_failure_returns_dict_with_pipe_separator(self, indicator, thresholds):
        record = _make_record(tx_power=-15.0, rx_power=5.0, temperature=35.0, voltage=3.3)
        result = indicator._check_single_record(record, thresholds)
        assert result is not None
        assert " | " in result["reason"]
        assert "Tx Power 過低" in result["reason"]
        assert "Rx Power 過高" in result["reason"]

    def test_failure_dict_contains_data(self, indicator, thresholds):
        record = _make_record(tx_power=-15.0, rx_power=-5.0, temperature=35.0, voltage=3.3)
        result = indicator._check_single_record(record, thresholds)
        assert result is not None
        assert result["data"]["tx_power"] == -15.0
        assert result["data"]["rx_power"] == -5.0
        assert result["data"]["temperature"] == 35.0
        assert result["data"]["voltage"] == 3.3
